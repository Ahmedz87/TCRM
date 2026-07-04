"""
backfill_lead_retention_handover.py — document the sales→retention agent handover on deposit.

When a lead (under a SALES agent) deposits and becomes a client, the desk moves them to a
RETENTION agent (same team) in the old CRM. Our reconcile imported the CURRENT (retention)
owner directly, so the client's agent is already CORRECT — but nothing on the timeline explains
the change. The OLD sales agent survives in the `leads` table (linked to the client by
customer_no). This step reconstructs the handover and writes, for each such client:
  • a call_actions comment (action='agent_change') on the client timeline, e.g.
    "Agent changed from Wael Shamaly (sales) to Ola Zuhayra (retention) — retention handover on
     deposit. Maya … was a lead under Wael Shamaly (sales); after first deposit USD 99 they
     became a client and were moved to Ola Zuhayra (retention). Source: TradeSoft / lead history."
  • a transfer_log audit row (from sales agent → to retention agent, batch 'lead-retention-handover').

It NEVER changes clients.assigned_agent_id (the current value is already right — this is
documentation only). Idempotent: skips any client that already has an agent_change comment.
Reversible via the batch_id. Only CLEAN sales→retention pairs are documented (lead agent is on a
sales team, current agent is on a retention team) so a comment is never mislabeled.

Runnable standalone:  python backfill_lead_retention_handover.py [--limit N] [--dry]
Also called each TradeSoft sync cycle from tradesoft_sync.py.
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from sqlalchemy import text
from database import SessionLocal

BATCH = "lead-retention-handover"

# One row per client: the pre-conversion SALES agent (from the matched lead) differs from the
# client's current RETENTION agent, the client actually deposited, and no handover comment exists.
_CAND_SQL = """
SELECT DISTINCT ON (c.login)
       c.login,
       COALESCE(NULLIF(trim(c.name),''), 'This client')  AS cli_name,
       l.assigned_agent_id                                AS sales_id,
       lu.full_name                                       AS sales_name,
       c.assigned_agent_id                                AS ret_id,
       cu.full_name                                       AS ret_name,
       (SELECT MIN(t.amount) FROM transactions t
          WHERE t.login=c.login AND t.tx_type='deposit' AND t.amount>0) AS first_dep
FROM clients c
JOIN leads l  ON l.customer_no = c.customer_no
JOIN users lu ON lu.id = l.assigned_agent_id AND lu.team_type='sales'
JOIN users cu ON cu.id = c.assigned_agent_id AND cu.team_type='retention'
WHERE l.assigned_agent_id IS DISTINCT FROM c.assigned_agent_id
  AND EXISTS (SELECT 1 FROM transactions t
                WHERE t.login=c.login AND t.tx_type='deposit' AND t.amount>0)
  AND NOT EXISTS (SELECT 1 FROM call_actions ca
                    WHERE ca.login=c.login AND ca.action='agent_change')
ORDER BY c.login, l.created_at NULLS LAST, l.id
{limit}
"""


def backfill(db, limit=0, dry=False):
    sql = _CAND_SQL.format(limit=(f"LIMIT {int(limit)}" if limit else ""))
    rows = db.execute(text(sql)).fetchall()
    n = 0
    for login, cli_name, sales_id, sales_name, ret_id, ret_name, first_dep in rows:
        dep = f"first deposit USD {first_dep:g}" if first_dep else "their first deposit"
        note = (f"Agent changed from {sales_name} (sales) to {ret_name} (retention) — "
                f"retention handover on deposit. {cli_name} was a lead under {sales_name} (sales); "
                f"after {dep} they became a client and were moved to {ret_name} (retention). "
                f"Source: TradeSoft / lead history.")
        if dry:
            n += 1
            continue
        db.execute(text("INSERT INTO call_actions (login, agent_id, action, note, created_at) "
                        "VALUES (:l,:a,'agent_change',:n,NOW())"),
                   {"l": login, "a": ret_id, "n": note})
        db.execute(text("""INSERT INTO transfer_log
            (record_type, record_key, from_agent_id, to_agent_id, by_user_name, reason, batch_id)
            VALUES ('client', :l, :s, :r, 'System (lead history)', :reason, :b)"""),
            {"l": str(login), "s": sales_id, "r": ret_id, "b": BATCH,
             "reason": f"{sales_name} (sales) -> {ret_name} (retention) — retention handover on deposit"})
        n += 1
        if n % 300 == 0:
            db.commit()
    if not dry:
        db.commit()
    return {"documented": n, "dry": dry}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    db = SessionLocal()
    try:
        print(backfill(db, limit=a.limit, dry=a.dry))
    finally:
        db.close()
