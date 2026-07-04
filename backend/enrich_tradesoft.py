"""
enrich_tradesoft.py — fill the RICH TradeSoft fields the thin hourly insert misses, incrementally.
Called by tradesoft_sync each run (and runnable standalone). Idempotent + batched (coexists w/ live sync).

  LEADS  (source='tradesoft', not yet enriched): real created_at, city, source/stage ids,
         sales agent (sales_rep->name), IB (referrer->name), campaign, notes(message).
  CLIENTS: legacy_sales_agent (fx_clients_view.owner->name), IB agent (fx_accounts_view.agent),
           notes (fx_clients_view.notes).  Only rows still missing the field.
"""
import sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from sqlalchemy import text
from database import SessionLocal
L = "tradesoft_old"
NAME = f"(SELECT DISTINCT ON (id) id, NULLIF(trim(COALESCE(name,'')||' '||COALESCE(surname,'')),'') nm FROM {L}.fx_users_view ORDER BY id)"


def _batched(db, sql, ids, label, chunk=3000):
    done = 0
    for i in range(0, len(ids), chunk):
        b = ids[i:i+chunk]
        for a in range(8):
            try:
                db.execute(text("SET lock_timeout='4s'"))
                done += db.execute(text(sql), {"ids": b}).rowcount
                db.commit(); break
            except Exception:
                db.rollback()
                if a == 7: raise
                time.sleep(1.3*(a+1))
    print(f"  {label}: {done:,}")


def enrich(db):
    # ---- LEADS: real fields from fx_leads_view (only un-enriched tradesoft leads) ----
    for col in ("legacy_sales_agent", "legacy_ib", "legacy_source", "legacy_stage"):
        db.execute(text(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} text"))
    db.commit()
    db.execute(text(f"""CREATE TEMP TABLE lf AS
      SELECT l.id, NULLIF(lv.city,'') city, NULLIF(lv.country,'') country,
        NULLIF(lv.created_at,'')::timestamptz reg, NULLIF(lv.source,'') src, NULLIF(lv.stage_id,'') stg,
        NULLIF(lv.utm_campaign,'') camp, sr.nm sales, ib.nm ibname, NULLIF(lv.message,'') msg
      FROM leads l
      JOIN customers cu ON cu.customer_no=l.customer_no
      JOIN (SELECT DISTINCT ON (user_id) user_id, country, city, source, stage_id, sales_rep, created_at,
             message, utm_campaign FROM {L}.fx_leads_view WHERE deleted_at IS NULL ORDER BY user_id, created_at) lv
        ON lv.user_id=cu.legacy_user_id
      LEFT JOIN {NAME} sr ON sr.id=lv.sales_rep
      LEFT JOIN (SELECT DISTINCT ON (u.id) u.id, su.nm FROM {L}.fx_users_view u
                 LEFT JOIN {NAME} su ON su.id=COALESCE(NULLIF(u.referrer_id,''),NULLIF(u.invited_by,'')) ORDER BY u.id) ib
        ON ib.id=cu.legacy_user_id
      WHERE l.source='tradesoft' AND l.legacy_sales_agent IS NULL"""))
    db.execute(text("CREATE INDEX ON lf(id)")); db.commit()
    ids = [r[0] for r in db.execute(text("SELECT id FROM lf")).fetchall()]
    print(f"  leads to enrich: {len(ids):,}")
    if ids:
        _batched(db, """UPDATE leads l SET city=f.city, country=COALESCE(f.country,l.country),
            created_at=COALESCE(f.reg,l.created_at), legacy_source=f.src, legacy_stage=f.stg,
            campaign_name=COALESCE(f.camp,l.campaign_name), legacy_sales_agent=COALESCE(f.sales,'-'),
            legacy_ib=f.ibname,
            notes=COALESCE(NULLIF(concat_ws(' | ',
              CASE WHEN f.sales IS NOT NULL THEN 'Sales: '||f.sales END,
              CASE WHEN f.ibname IS NOT NULL THEN 'IB: '||f.ibname END,
              CASE WHEN f.msg IS NOT NULL AND f.msg NOT ILIKE '%<br>%' THEN f.msg END),''), l.notes)
          FROM lf f WHERE f.id=l.id AND l.id=ANY(:ids)""", ids, "leads enriched")

    # ---- LEADS: campaign / real created-date / KYC status from fx_USERS_view (the registered-user
    # record — richer than fx_leads_view for these fields: utm_campaign 27k, lead_source 65k,
    # created_at 161k, is_kyc_verified). NOTE: KYC DOCUMENT FILES are NOT in the SQL mirror (they were
    # in SumSub + on the old server's disk) — only the verified STATUS is importable. ----
    db.execute(text(f"""UPDATE leads l SET
        utm_campaign = COALESCE(NULLIF(l.utm_campaign,''), NULLIF(u.utm_campaign,'')),
        utm_source   = COALESCE(NULLIF(l.utm_source,''),   NULLIF(u.lead_source,'')),
        created_at   = CASE WHEN (l.created_at IS NULL OR l.created_at::date > '2026-06-10')
                              AND NULLIF(u.created_at,'')::timestamp < '2026-06-10'
                            THEN NULLIF(u.created_at,'')::timestamp ELSE l.created_at END,
        is_verified  = CASE WHEN u.is_kyc_verified::text='1' THEN TRUE ELSE l.is_verified END,
        kyc_status   = CASE WHEN u.is_kyc_verified::text='1' AND COALESCE(l.kyc_status,'') IN ('','pending')
                            THEN 'verified' ELSE l.kyc_status END
      FROM customers cu
      JOIN {L}.fx_users_view u ON u.id = cu.legacy_user_id::text
      WHERE cu.customer_no = l.customer_no
        AND (COALESCE(l.utm_campaign,'')='' OR COALESCE(l.utm_source,'')=''
             OR l.created_at::date > '2026-06-10' OR (u.is_kyc_verified::text='1' AND COALESCE(l.is_verified,FALSE)=FALSE))"""))
    db.commit()
    print("  leads campaign/created/kyc filled from fx_users_view")

    # ---- CLIENTS: sales agent (owner) ----
    db.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS legacy_sales_agent text"))
    db.commit()
    db.execute(text(f"""CREATE TEMP TABLE cs AS
      SELECT c.login, su.nm sales,
             (SELECT DISTINCT ON (user_id) NULLIF(notes,'') FROM {L}.fx_clients_view
              WHERE user_id=cu.legacy_user_id AND deleted_at IS NULL ORDER BY user_id) note
      FROM clients c JOIN customers cu ON cu.customer_no=c.customer_no
      JOIN (SELECT DISTINCT ON (user_id) user_id, owner FROM {L}.fx_clients_view
            WHERE deleted_at IS NULL AND COALESCE(owner,'') NOT IN ('','0') ORDER BY user_id) o ON o.user_id=cu.legacy_user_id
      JOIN {NAME} su ON su.id=o.owner
      WHERE c.legacy_sales_agent IS NULL AND su.nm IS NOT NULL"""))
    db.execute(text("CREATE INDEX ON cs(login)")); db.commit()
    ids = [r[0] for r in db.execute(text("SELECT login FROM cs")).fetchall()]
    print(f"  clients needing sales agent: {len(ids):,}")
    if ids:
        _batched(db, "UPDATE clients c SET legacy_sales_agent=cs.sales FROM cs WHERE cs.login=c.login AND c.login=ANY(:ids)",
                 ids, "clients sales_agent")

    # ---- CLIENTS: sales agent via the RELIABLE per-LOGIN path (MT login -> account -> client.owner).
    # This catches accounts whose customer_no is mis-merged (the customer-based path above misses them).
    db.execute(text(f"""UPDATE clients c SET legacy_sales_agent = lo.owner_name
      FROM (
        SELECT DISTINCT ON (a.account_number::bigint) a.account_number::bigint login,
          CASE WHEN cl.owner ~ '^[0-9]+$'
            THEN (SELECT NULLIF(trim(COALESCE(ou.name,'')||' '||COALESCE(ou.surname,'')),'')
                  FROM {L}.fx_users_view ou WHERE ou.id = cl.owner)
            ELSE NULLIF(cl.owner,'') END AS owner_name
        FROM {L}.fx_accounts_view a
        JOIN {L}.fx_clients_view cl ON cl.user_id = a.user_id
        WHERE a.account_number ~ '^[0-9]+$' AND COALESCE(cl.owner,'') <> ''
        ORDER BY a.account_number::bigint, a.id DESC) lo
      WHERE lo.login = c.login AND COALESCE(c.legacy_sales_agent,'') = '' AND lo.owner_name IS NOT NULL"""))
    db.commit()
    print("  clients sales_agent filled via per-login owner")

    # ---- CLIENTS: equity at rest = balance (live MT5 bridge overwrites live accounts every 30s;
    # this just keeps legacy/offline accounts from showing a blank equity). margin_level stays as-is
    # (only meaningful with open positions — the bridge sets it for active accounts). ----
    db.execute(text("UPDATE clients SET equity = balance WHERE COALESCE(balance,0) > 0 AND COALESCE(equity,0) = 0"))
    db.commit()
    print("  clients equity backfilled (=balance where missing)")

    # ---- CUSTOMERS: IB from the USER-LEVEL referrer (TradeSoft referrer_id -> referrer's name).
    # This is how TradeSoft stores the IB for a client (even one with no trading account). ----
    db.execute(text(f"""UPDATE customers cu SET ib = ref.nm
      FROM (SELECT u.id uid, su.nm FROM {L}.fx_users_view u
            JOIN {NAME} su ON su.id = NULLIF(u.referrer_id,'')
            WHERE COALESCE(u.referrer_id,'') NOT IN ('','0')) ref
      WHERE cu.legacy_user_id = ref.uid AND COALESCE(cu.ib,'')='' AND ref.nm IS NOT NULL"""))
    db.commit()
    print("  customers IB-from-referrer filled")

    # ---- CLIENTS: IB agent from TradeSoft accounts (where missing) ----
    db.execute(text(f"""CREATE TEMP TABLE ib AS
      SELECT c.login, a.agent FROM clients c
      JOIN (SELECT DISTINCT ON (account_number::bigint) account_number::bigint login,
              CASE WHEN agent ~ '^[0-9]+$' THEN agent::bigint END agent
            FROM {L}.fx_accounts_view WHERE account_number ~ '^[0-9]+$' ORDER BY account_number::bigint, updated_at DESC NULLS LAST) a
        ON a.login=c.login
      WHERE c.agent IS NULL AND a.agent IS NOT NULL"""))
    db.execute(text("CREATE INDEX ON ib(login)")); db.commit()
    ids = [r[0] for r in db.execute(text("SELECT login FROM ib")).fetchall()]
    print(f"  clients needing IB: {len(ids):,}")
    if ids:
        _batched(db, "UPDATE clients c SET agent=ib.agent FROM ib WHERE ib.login=c.login AND c.login=ANY(:ids)",
                 ids, "clients IB")

    # ---- SALES AGENT: map the legacy owner NAME -> our staff users.id via the editable
    # `sales_agent_aliases` table (built by build_sales_aliases.py; the desk can add rows for
    # names that didn't auto-match). Keeps clients/leads.assigned_agent_id in step with the
    # legacy_sales_agent string so the Sales Agents page shows the right owner. ----
    db.execute(text("""CREATE TABLE IF NOT EXISTS sales_agent_aliases(
      legacy_name TEXT PRIMARY KEY, user_id INT REFERENCES users(id),
      source VARCHAR(16) DEFAULT 'auto', updated_at TIMESTAMPTZ DEFAULT NOW())"""))
    for tbl in ("clients", "leads"):
        db.execute(text(f"""UPDATE {tbl} t SET assigned_agent_id=a.user_id
          FROM sales_agent_aliases a
          WHERE t.legacy_sales_agent=a.legacy_name
            AND t.assigned_agent_id IS DISTINCT FROM a.user_id"""))
    # customers master: link via cu.sales_agent (covers people whose MT accounts aren't in the
    # clients table but the customer carries the owner name), then backfill from any linked client.
    db.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS assigned_agent_id INT REFERENCES users(id)"))
    db.execute(text("""UPDATE customers cu SET assigned_agent_id=a.user_id
      FROM sales_agent_aliases a WHERE a.legacy_name=cu.sales_agent
        AND cu.assigned_agent_id IS DISTINCT FROM a.user_id"""))
    db.execute(text("""UPDATE customers cu SET assigned_agent_id=sub.aid FROM (
        SELECT customer_no, MIN(assigned_agent_id) aid FROM clients
        WHERE assigned_agent_id IS NOT NULL GROUP BY customer_no) sub
      WHERE cu.customer_no=sub.customer_no AND cu.assigned_agent_id IS NULL"""))
    db.commit()
    print("  assigned_agent_id synced from sales_agent_aliases (clients/leads/customers)")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        enrich(db); print("enrich done")
    finally:
        db.close()
