import psycopg2
from psycopg2.extras import RealDictCursor
import db_config
conn = db_config.connect()
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== MT4 trading accounts — linking audit ===")

# 1. Total MT4 trading accounts
cur.execute("SELECT COUNT(*) as n FROM trading_accounts WHERE platform='MT4'")
print(f"Total MT4 trading accounts:          {cur.fetchone()['n']}")

# 2. MT4 accounts WITH client_id
cur.execute("SELECT COUNT(*) as n FROM trading_accounts WHERE platform='MT4' AND client_id IS NOT NULL")
print(f"MT4 accounts WITH client_id:         {cur.fetchone()['n']}")

# 3. MT4 accounts WITHOUT client_id (orphaned)
cur.execute("SELECT COUNT(*) as n FROM trading_accounts WHERE platform='MT4' AND client_id IS NULL")
print(f"MT4 accounts WITHOUT client_id:      {cur.fetchone()['n']}")

# 4. MT4 accounts where client shows only MT5 (not updated to MT4/MT5)
cur.execute("""
    SELECT COUNT(*) as n FROM trading_accounts ta
    JOIN clients c ON c.id = ta.client_id
    WHERE ta.platform='MT4' AND c.platform='MT5'
""")
print(f"MT4 accounts linked to MT5-only client: {cur.fetchone()['n']} (platform not updated)")

# 5. MT4 accounts where client shows MT4 (MT4-only clients)
cur.execute("""
    SELECT COUNT(*) as n FROM trading_accounts ta
    JOIN clients c ON c.id = ta.client_id
    WHERE ta.platform='MT4' AND c.platform='MT4'
""")
print(f"MT4 accounts linked to MT4-only client: {cur.fetchone()['n']}")

# 6. MT4 accounts where client shows MT4/MT5 (correctly updated)
cur.execute("""
    SELECT COUNT(*) as n FROM trading_accounts ta
    JOIN clients c ON c.id = ta.client_id
    WHERE ta.platform='MT4' AND c.platform='MT4/MT5'
""")
print(f"MT4 accounts linked to MT4/MT5 client:  {cur.fetchone()['n']}")

# 7. Show the ones not updated to MT4/MT5 (sample)
cur.execute("""
    SELECT ta.login as mt4_login, c.id, c.login as client_login,
           c.name, c.phone, c.platform
    FROM trading_accounts ta
    JOIN clients c ON c.id = ta.client_id
    WHERE ta.platform='MT4' AND c.platform='MT5'
    LIMIT 20
""")
rows = cur.fetchall()
if rows:
    print(f"\n=== Sample MT4 accounts still showing MT5 platform (first 20) ===")
    for r in rows: print(f"  MT4:{r['mt4_login']} -> client_id={r['id']} login={r['client_login']} {r['name']!r} {r['phone']} platform={r['platform']}")

# 8. Orphaned MT4 accounts (no client_id)
cur.execute("""
    SELECT login, name, group_name, balance
    FROM trading_accounts
    WHERE platform='MT4' AND client_id IS NULL
    LIMIT 20
""")
rows = cur.fetchall()
if rows:
    print(f"\n=== Orphaned MT4 trading accounts (no client_id) ===")
    for r in rows: print(f"  login={r['login']} {r['name']!r} {r['group_name']} bal={r['balance']}")

conn.close()
