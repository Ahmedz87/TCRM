import sys, os
import db_config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
from psycopg2.extras import RealDictCursor
from bridge_mt4 import load_dll, connect, get_all_users

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

load_dll(); connect()
mt4_users = {u["login"]: u for u in get_all_users() if u["login"] > 10}

conn = psycopg2.connect(**DB, cursor_factory=RealDictCursor)
cur  = conn.cursor()

cur.execute("SELECT login,name,phone,platform,group_name,id FROM clients WHERE login = ANY(%s) ORDER BY login", (list(mt4_users.keys()),))
collisions = cur.fetchall()
print(f"\n=== LOGIN COLLISIONS: {len(collisions)} ===")
for row in collisions:
    mt4 = mt4_users[row["login"]]
    p1 = (row["phone"] or "").replace(" ","").replace("+","")
    p2 = mt4["phone"].replace(" ","").replace("+","")
    same = bool(p1 and p2 and p1==p2)
    print(f"  login={row['login']} | MT5: {row['name']!r} {row['phone']!r} | MT4: {mt4['name']!r} {mt4['phone']!r} | SAME={same}")

cur.execute("SELECT login FROM trading_accounts WHERE platform='MT4'")
imported = {r["login"] for r in cur.fetchall()}
missing = [l for l in mt4_users if l not in imported]
print(f"\n=== NOT IN TRADING_ACCOUNTS: {len(missing)} ===")
for l in missing[:30]:
    u = mt4_users[l]
    cur.execute("SELECT id,name,phone,platform FROM clients WHERE login=%s",(l,))
    ex = cur.fetchone()
    print(f"  login={l} name={u['name']!r} phone={u['phone']!r} existing={('id='+str(ex['id'])+'/'+ex['platform']) if ex else 'NONE'}")
if len(missing)>30: print(f"  ...and {len(missing)-30} more")

cur.execute("SELECT COUNT(*) as n FROM trading_accounts WHERE platform='MT4'"); ta=cur.fetchone()["n"]
cur.execute("SELECT COUNT(*) as n FROM clients WHERE platform IN ('MT4','MT4/MT5')"); cl=cur.fetchone()["n"]
print(f"\n=== COUNTS === trading_accounts MT4={ta} | clients MT4/MT4+MT5={cl} | MT4 server={len(mt4_users)} | gap={len(mt4_users)-ta}")
conn.close()
