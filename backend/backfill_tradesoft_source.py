"""
backfill_tradesoft_source.py — attribute broker_crm.clients to their REAL acquisition channel
using the TradeSoft mirror (tradesoft_old). TradeSoft (my.tnfx.co) is where customers register
and stores the ad source in fx_users_view.lead_source (e.g. 'IQ-Google-LandingPage').

Chain:  clients.login = fx_accounts_view.account_number → .user_id = fx_users_view.id → lead_source
Sets clients.source (normalized) + utm_source (raw) + utm_campaign. Idempotent / re-runnable.

The live `clients` table is constantly written by the MT bridge, so a single big UPDATE blocks on
locks. We compute the mapping once (read-only on TradeSoft), then UPDATE in SMALL batches with a
short lock_timeout + retry, so each lock is brief and slips between the bridge's writes.
"""
import sys, time, psycopg2
import db_config
from psycopg2.extras import execute_values
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
NORM = """CASE
    WHEN u.lead_source ILIKE '%google%' THEN 'google'
    WHEN u.lead_source ILIKE '%meta%' OR u.lead_source ILIKE '%facebook%' OR lower(u.lead_source)='fb' THEN 'facebook'
    WHEN lower(u.lead_source)='ig' OR u.lead_source ILIKE '%instagram%' THEN 'instagram'
    WHEN u.lead_source ~ '^[0-9]+$' THEN 'affiliate'
    WHEN u.lead_source ILIKE '%direct%' THEN 'direct'
    ELSE lower(u.lead_source) END"""


def main():
    c = psycopg2.connect(**DB); c.autocommit = True; cur = c.cursor()
    cur.execute("SET idle_in_transaction_session_timeout = 0")
    # 1) compute the mapping (read-only on TradeSoft) — one source per MT login
    cur.execute(f"""
        SELECT DISTINCT ON (a.account_number::text)
               a.account_number::text AS login, {NORM} AS norm, u.lead_source, NULLIF(u.utm_campaign,'')
        FROM tradesoft_old.fx_accounts_view a
        JOIN tradesoft_old.fx_users_view u ON u.id = a.user_id
        WHERE COALESCE(u.lead_source,'') <> ''
        ORDER BY a.account_number::text, a.updated_at DESC NULLS LAST
    """)
    rows = cur.fetchall()
    print(f"TradeSoft sourced logins: {len(rows)}")
    # 2) batch-update clients
    BATCH = 300
    updated = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        for attempt in range(5):
            try:
                cur.execute("SET lock_timeout = '5s'")
                execute_values(cur, """
                    UPDATE clients c SET source = v.src, utm_source = v.raw,
                        utm_campaign = COALESCE(v.camp, c.utm_campaign), updated_at = NOW()
                    FROM (VALUES %s) AS v(login, src, raw, camp)
                    WHERE c.login::text = v.login
                      AND (c.source IS DISTINCT FROM v.src OR c.utm_source IS DISTINCT FROM v.raw)
                """, batch, template="(%s,%s,%s,%s)")
                updated += cur.rowcount
                break
            except psycopg2.errors.LockNotAvailable:
                time.sleep(1.5)            # bridge held the lock; back off and retry this batch
            except Exception as e:
                print("batch error:", str(e)[:120]); break
        if (i // BATCH) % 10 == 0:
            print(f"  ...{i+len(batch)}/{len(rows)} processed, {updated} updated")
    print("clients updated:", updated)
    cur.execute("SELECT source, COUNT(*) FROM clients WHERE COALESCE(source,'')<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 15")
    print("\nclients.source distribution now:")
    for r in cur.fetchall():
        print(f"  {str(r[0]):28} {r[1]:>6}")
    c.close()


if __name__ == "__main__":
    main()
