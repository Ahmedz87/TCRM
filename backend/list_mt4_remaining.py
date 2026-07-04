import sys, psycopg2
import db_config
sys.path.insert(0, r"C:\broker-crm\backend")
from psycopg2.extras import RealDictCursor
from bridge_mt4 import load_dll, connect, get_all_users

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
SKIP = {518,4008,4021,5000,100100,1994312,100100100,2100050658,
        2100051583,334161763,2100052951,2100051476}
SYSTEM_KW = ["datacenter","dc bkp","dc fra","dc uk","dc bah","dc ger",
             "dc cai","dc kl","dc tur","dc saf","report server","watchdog",
             "feeder","manual dealer","trading operations","lost & found",
             "demo feeder","do not delete","oz report","bridge dealer",
             "failover","plugit","itradesoft","stp dealing","bo stp",
             "fsa reporting","test raw","gbe","centroid","pamm","manager - "]

load_dll(); connect()
mt4 = {u["login"]: u for u in get_all_users()}
conn = psycopg2.connect(**DB, cursor_factory=RealDictCursor)
cur  = conn.cursor()
cur.execute("SELECT login FROM trading_accounts WHERE platform='MT4'")
in_ta = {r["login"] for r in cur.fetchall()}
cur.execute("SELECT id,login,name,phone,platform FROM clients ORDER BY id")
db_clients = {r["login"]: r for r in cur.fetchall()}

missing = []
for login, u in sorted(mt4.items()):
    if login in in_ta or login in SKIP or login <= 10: continue
    name = u["name"].lower()
    if any(kw in name for kw in SYSTEM_KW): continue
    if not u["phone"] and login < 200: continue
    missing.append((login, u))

print(f"Total: {len(missing)}")
print(f"{'Login':>12} | {'Name':<40} | {'Phone':<22} | in_db")
print("-"*90)
for login, u in missing:
    ex = db_clients.get(login)
    db_info = f"YES id={ex['id']}" if ex else "NO"
    print(f"{login:>12} | {u['name']:<40} | {u['phone']:<22} | {db_info}")
conn.close()
