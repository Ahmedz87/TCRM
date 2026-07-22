"""
Backfill account_identifiers from the two sources that never fed it (it only had live MT5 bridge data):

  1. trading_accounts.mqid / last_ip / cid    — the MT4 sync stores device+ip HERE but never copied
                                                them into account_identifiers, so every MT4 account
                                                showed network 0/10 even with a shared device.
  2. tradesoft_old.fx_users_view              — registration_ip / last_ip ('ip') + device_id ('cid')
                                                for ~156k legacy users, mapped to their accounts.

SAFETY CAP: an identifier value linked to more than 20 DISTINCT users is skipped (ISP CG-NAT or an
office device would otherwise weld hundreds of strangers into one fake network).
Idempotent (unique login+type+value, ON CONFLICT DO NOTHING). Feeds the IB-profile network score,
the Network page and the abuse engine alike.
"""
import sys
import db_config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

con = db_config.connect(); cur = con.cursor()

def run(label, sql):
    cur.execute(sql)
    print(f"  {label}: +{cur.rowcount} rows")
    con.commit()

# ── 1. from trading_accounts (covers MT4) ─────────────────────────────────────
run("trading_accounts mqid", """
    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
    SELECT login, 'mqid', TRIM(mqid), NOW(), NOW(), 1
    FROM trading_accounts
    WHERE COALESCE(TRIM(mqid),'') NOT IN ('','0')
    ON CONFLICT (login, identifier_type, identifier_value) DO NOTHING""")
run("trading_accounts last_ip", """
    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
    SELECT login, 'ip', TRIM(last_ip), NOW(), NOW(), 1
    FROM trading_accounts
    WHERE COALESCE(TRIM(last_ip),'') NOT IN ('','0','0.0.0.0','127.0.0.1')
    ON CONFLICT (login, identifier_type, identifier_value) DO NOTHING""")
run("trading_accounts cid", """
    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
    SELECT login, 'cid', TRIM(cid), NOW(), NOW(), 1
    FROM trading_accounts
    WHERE COALESCE(TRIM(cid),'') NOT IN ('','0')
      AND TRIM(cid) !~ '^C1000'          -- fake sequential placeholders from the old seed
    ON CONFLICT (login, identifier_type, identifier_value) DO NOTHING""")

# ── 2. from TradeSoft (registration/last ip + device), capped at 20 users/value ─
run("tradesoft ips + devices", """
    WITH u AS (
        SELECT id AS user_id,
               NULLIF(TRIM(registration_ip),'') AS rip,
               NULLIF(TRIM(last_ip),'')         AS lip,
               NULLIF(TRIM(device_id),'')       AS dev
        FROM tradesoft_old.fx_users_view
    ),
    vals AS (
        SELECT user_id, 'ip'::text  AS t, rip AS v FROM u WHERE rip IS NOT NULL AND rip NOT IN ('0','0.0.0.0','127.0.0.1')
        UNION
        SELECT user_id, 'ip',  lip FROM u WHERE lip IS NOT NULL AND lip NOT IN ('0','0.0.0.0','127.0.0.1')
        UNION
        SELECT user_id, 'cid', dev FROM u WHERE dev IS NOT NULL AND dev <> '0'
    ),
    ok AS (   -- anti-NAT cap: value must belong to <= 20 distinct users
        SELECT t, v FROM vals GROUP BY t, v HAVING COUNT(DISTINCT user_id) <= 20
    ),
    acc AS (
        SELECT DISTINCT account_number::bigint AS login, user_id
        FROM tradesoft_old.fx_accounts_view
        WHERE account_number ~ '^[0-9]+$'
    )
    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
    SELECT a.login, x.t, x.v, NOW(), NOW(), 1
    FROM vals x JOIN ok o ON o.t = x.t AND o.v = x.v
    JOIN acc a ON a.user_id = x.user_id
    ON CONFLICT (login, identifier_type, identifier_value) DO NOTHING""")

cur.execute("SELECT identifier_type, COUNT(*) FROM account_identifiers GROUP BY 1 ORDER BY 2 DESC")
print("account_identifiers now:", cur.fetchall())
con.close()
