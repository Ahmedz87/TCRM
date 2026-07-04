"""READ-ONLY: connect provision login C/3027, read one pending MT5 IB account's live group."""
import sys, psycopg2
import mt_managers as M
import MT5Manager as mt5m

import db_config
conn = db_config.connect()
cur = conn.cursor()
cur.execute("""
  WITH ib_person AS (
    SELECT i.id ib_id, i.ib_level, i.agent_id, oc.customer_no
    FROM ibs i LEFT JOIN clients oc ON oc.login=i.agent_id
    WHERE i.plugit_status='synced' AND i.ib_level IS NOT NULL
  )
  SELECT DISTINCT c.login, c.group_name, p.ib_level, i.name
  FROM ib_person p
  JOIN clients c ON (p.customer_no IS NOT NULL AND c.customer_no=p.customer_no) OR c.login=p.agent_id
  JOIN ibs i ON i.id=p.ib_id
  WHERE c.group_name ILIKE '%IB-%' AND COALESCE(c.platform,'MT5') NOT ILIKE 'MT4%'
""")
pick = None
for login, grp, lvl, ibname in cur.fetchall():
    tgt = f"IB\IB-{lvl}"
    if (grp or '') != tgt:
        pick = (login, grp, tgt, ibname); break
cur.close(); conn.close()
if not pick:
    print("no pending MT5 account found"); sys.exit(0)
login, cur_grp, target, ibname = pick
print(f"TEST login={login} ({ibname}) DB group={cur_grp!r} -> target={target!r}")

login_c, pw_c = M.MT5["C"]
print(f"connecting MT5 {M.MT5_SERVER} as provision login {login_c} ...", flush=True)
mgr = mt5m.ManagerAPI()
ok = mgr.Connect(M.MT5_SERVER, login_c, pw_c)
print("Connect ->", ok, flush=True)
if not ok:
    try: print("LastError:", mt5m.LastError())
    except Exception: pass
    sys.exit(1)
u = None
for meth in ("UserRequest","UserGet"):
    if hasattr(mgr, meth):
        try:
            u = getattr(mgr, meth)(int(login))
            if u: break
        except Exception as e: print(meth,"err",e)
print("MT5 LIVE group:", getattr(u,"Group",None) if u else "USER NOT FOUND", flush=True)
try: mgr.Disconnect()
except Exception: pass
