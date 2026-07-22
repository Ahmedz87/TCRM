"""Batched, deadlock-tolerant apply of: demo-account archiving + recent-depositor reactivation.
Small login-ordered chunks with retry so it coexists with the live bridge's client updates."""
import time
import db_config

conn = db_config.connect(); cur = conn.cursor()

def batched_update(select_sql, update_sql, label, params=()):
    cur.execute(select_sql, params)
    ids = [r[0] for r in cur.fetchall()]
    done = 0
    CH = 1000
    for i in range(0, len(ids), CH):
        batch = ids[i:i+CH]
        for attempt in range(6):
            try:
                cur.execute("SET lock_timeout='10s'")
                cur.execute(update_sql, (batch,))
                done += cur.rowcount
                conn.commit()
                break
            except Exception:
                conn.rollback()
                if attempt == 5:
                    raise
                time.sleep(1.5 * (attempt + 1))
    print(f"{label}: {done}")

# 1) demo accounts -> archive
batched_update(
    """SELECT c.login FROM clients c JOIN tradesoft_old.fx_accounts_view a
         ON a.account_number ~ '^[0-9]+$' AND c.login=a.account_number::bigint
       WHERE a.account_type='Demo' AND NOT COALESCE(c.is_archived,false) ORDER BY c.login""",
    """UPDATE clients c SET is_archived=TRUE,
         archive_reason=COALESCE(c.archive_reason,'demo account (TradeSoft)')
       WHERE c.login = ANY(%s)""",
    "demo clients archived")

# 2) stamp trading_accounts
batched_update(
    """SELECT ta.login FROM trading_accounts ta JOIN tradesoft_old.fx_accounts_view a
         ON a.account_number ~ '^[0-9]+$' AND ta.login=a.account_number::bigint
       WHERE a.account_type='Demo' AND COALESCE(ta.account_type,'')<>'Demo' ORDER BY ta.login""",
    "UPDATE trading_accounts SET account_type='Demo' WHERE login = ANY(%s)",
    "trading_accounts stamped Demo")

# 3) reactivate accounts with a real deposit in the last 30 days (never demo)
batched_update(
    """SELECT c.login FROM clients c
       WHERE COALESCE(c.is_archived,false)
         AND EXISTS (SELECT 1 FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit'
                     AND left(t.tx_date,10) >= to_char(now()-interval '30 days','YYYY-MM-DD'))
         AND NOT EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a
                         WHERE a.account_number=c.login::text AND a.account_type='Demo')
       ORDER BY c.login""",
    "UPDATE clients SET is_archived=FALSE, archive_reason=NULL, is_active=TRUE WHERE login = ANY(%s)",
    "recent-depositor accounts reactivated")

cur.execute("SELECT login,is_active,is_archived,archive_reason,balance FROM clients WHERE email ILIKE '%%cooter8%%' ORDER BY login")
print("scooter8exo accounts now:")
for r in cur.fetchall():
    print("  ", r)
conn.close()
