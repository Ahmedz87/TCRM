"""
sync_agent_from_tradesoft.py — mirror agent reassignments made in the OLD CRM (TradeSoft).

Policy (done manually in TradeSoft today): a lead sits under a SALES agent; the moment they deposit
they become a client and are moved to a RETENTION agent in the SAME team (e.g. Ali Raad Kadhim moved
Gada Ateah → Ayat Mehrez). TradeSoft's `fx_clients_view.owner` holds the CURRENT (updated) agent, but
`enrich_tradesoft` only fills `clients.legacy_sales_agent` when it's NULL, so those changes were never
picked up here.

This step, run each TradeSoft sync cycle (every 30–60 min): re-reads the CURRENT TradeSoft owner per
client login, maps it to our user via `sales_agent_aliases`, and where it differs from the client's
`assigned_agent_id`:
  • updates the client's agent (+ legacy_sales_agent),
  • adds a comment on the client timeline ("Agent changed from X to Y … synced from TradeSoft"),
  • writes an audit row to `transfer_log` (from → to, source = TradeSoft).

Unmapped owners (no alias row) are skipped — the desk adds an alias for the retention agent and the
next cycle picks it up. Runnable standalone:  python sync_agent_from_tradesoft.py [--limit N] [--dry]
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from sqlalchemy import text
from database import SessionLocal

L = "tradesoft_old"

# clients whose CURRENT TradeSoft owner maps (via an alias) to a DIFFERENT user than we have assigned
_CHANGED_SQL = f"""
    SELECT c.login,
           c.assigned_agent_id                AS old_id,
           ou.full_name                       AS old_name,
           lo.owner_name                      AS ts_owner,
           al.user_id                         AS new_id,
           nu.full_name                       AS new_name,
           nu.team_type                       AS new_team,
           COALESCE(c.total_deposits,0)       AS dep
    FROM clients c
    JOIN (
        SELECT DISTINCT ON (a.account_number::bigint) a.account_number::bigint AS login,
          CASE WHEN cl.owner ~ '^[0-9]+$'
            THEN (SELECT NULLIF(trim(COALESCE(u2.name,'')||' '||COALESCE(u2.surname,'')),'')
                  FROM {L}.fx_users_view u2 WHERE u2.id = cl.owner)
            ELSE NULLIF(cl.owner,'') END AS owner_name
        FROM {L}.fx_accounts_view a
        JOIN {L}.fx_clients_view cl ON cl.user_id = a.user_id
        WHERE a.account_number ~ '^[0-9]+$' AND COALESCE(cl.owner,'') <> ''
          -- SKIP ambiguous account numbers: TradeSoft has ~17.5k account numbers duplicated under
          -- MULTIPLE users with DIFFERENT owners (data glitch). We can't reliably tell which is the
          -- real one, so only sync account numbers that resolve to EXACTLY ONE owner.
          AND a.account_number IN (
              SELECT a2.account_number FROM {L}.fx_accounts_view a2
              JOIN {L}.fx_clients_view cl2 ON cl2.user_id = a2.user_id
              WHERE a2.account_number ~ '^[0-9]+$' AND COALESCE(cl2.owner,'') <> ''
              GROUP BY a2.account_number HAVING COUNT(DISTINCT cl2.owner) = 1)
        ORDER BY a.account_number::bigint, a.id DESC
    ) lo ON lo.login = c.login
    JOIN sales_agent_aliases al ON al.legacy_name = lo.owner_name AND al.user_id IS NOT NULL
    LEFT JOIN users ou ON ou.id = c.assigned_agent_id
    LEFT JOIN users nu ON nu.id = al.user_id
    WHERE c.assigned_agent_id IS DISTINCT FROM al.user_id
    {{limit}}
"""


def sync_agent_changes(db, limit=0, dry=False):
    TE = None
    try:
        import transfer_engine as TE
        TE.ensure_schema(db)          # make sure transfer_log exists
    except Exception:
        pass

    sql = _CHANGED_SQL.format(limit=(f"LIMIT {int(limit)}" if limit else ""))
    rows = db.execute(text(sql)).fetchall()
    if not rows:
        return {"changed": 0, "dry": dry}

    changed = 0
    for login, old_id, old_name, ts_owner, new_id, new_name, new_team, dep in rows:
        old_disp = old_name or "(unassigned)"
        new_disp = new_name or ts_owner
        ctx = " (retention handover on deposit)" if (new_team == "retention" and (dep or 0) > 0) else ""
        note = f"Agent changed from {old_disp} to {new_disp}{ctx} — synced from TradeSoft."
        if dry:
            changed += 1
            continue
        db.execute(text("UPDATE clients SET assigned_agent_id=:n, legacy_sales_agent=:o WHERE login=:l"),
                   {"n": new_id, "o": ts_owner, "l": login})
        # comment on the client timeline (call_actions is what the client page reads)
        db.execute(text("INSERT INTO call_actions (login, agent_id, action, note, created_at) "
                        "VALUES (:l,:a,'agent_change',:n,NOW())"),
                   {"l": login, "a": new_id, "n": note})
        # audit log — from → to, source: TradeSoft
        db.execute(text("""INSERT INTO transfer_log
            (record_type, record_key, from_agent_id, to_agent_id, by_user_name, reason, batch_id)
            VALUES ('client', :l, :o, :n, 'TradeSoft sync', :r, 'tradesoft-agent-sync')"""),
            {"l": login, "o": old_id, "n": new_id,
             "r": f"{old_disp} → {new_disp} (source: TradeSoft){ctx}"})
        changed += 1
        if changed % 300 == 0:
            db.commit()
    if not dry:
        db.commit()
    return {"changed": changed, "dry": dry}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    db = SessionLocal()
    try:
        print(sync_agent_changes(db, limit=a.limit, dry=a.dry))
    finally:
        db.close()
