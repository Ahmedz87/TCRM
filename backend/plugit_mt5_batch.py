"""LIVE MT5 batch: fix IB-account groups to the Excel level via provision login C/3027.
Scope = accounts whose group ILIKE '%IB-%' (real IB accts), platform not MT4, group != target.
Logs every change to ib_mt_group_log (rollback) and updates clients.group_name."""
import psycopg2
import mt_managers as M
import MT5Manager as mt5m

import db_config
conn = db_config.connect()
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS ib_mt_group_log(
  login BIGINT, platform VARCHAR, old_group VARCHAR, new_group VARCHAR,
  ok BOOLEAN, err VARCHAR, ts TIMESTAMPTZ DEFAULT NOW())""")
conn.commit()
cur.execute("""
  WITH ib_person AS (
    SELECT i.id ib_id, i.ib_level, i.agent_id, oc.customer_no
    FROM ibs i LEFT JOIN clients oc ON oc.login=i.agent_id
    WHERE i.plugit_status='synced' AND i.ib_level IS NOT NULL
  )
  SELECT DISTINCT c.login, c.group_name, p.ib_level
  FROM ib_person p
  JOIN clients c ON (p.customer_no IS NOT NULL AND c.customer_no=p.customer_no) OR c.login=p.agent_id
  WHERE c.group_name ILIKE '%IB-%' AND COALESCE(c.platform,'MT5') NOT ILIKE 'MT4%'
""")
pending = []
for login, grp, lvl in cur.fetchall():
    tgt = f"IB\IB-{lvl}"
    if (grp or '') != tgt:
        pending.append((login, grp, tgt))
print(f"MT5 pending: {len(pending)}", flush=True)

login_c, pw_c = M.MT5["C"]
mgr = mt5m.ManagerAPI()
if not mgr.Connect(M.MT5_SERVER, login_c, pw_c):
    print("connect failed"); raise SystemExit(1)

def get(login):
    for meth in ("UserRequest","UserGet"):
        if hasattr(mgr, meth):
            try:
                u = getattr(mgr, meth)(int(login))
                if u: return u
            except Exception: pass
    return None

ok=fail=0
for login, oldg, tgt in pending:
    err=None; success=False
    try:
        u = get(login)
        if not u: err="user not found"
        else:
            u.Group = tgt
            success = bool(mgr.UserUpdate(u))
            if not success: err="UserUpdate returned False"
    except Exception as e:
        err=str(e)
    cur.execute("INSERT INTO ib_mt_group_log(login,platform,old_group,new_group,ok,err) VALUES(%s,'MT5',%s,%s,%s,%s)",
                (login, oldg, tgt, success, err))
    if success:
        ok+=1
        cur.execute("UPDATE clients SET group_name=%s WHERE login=%s", (tgt, login))
    else:
        fail+=1; print("FAIL", login, err, flush=True)
    if (ok+fail)%50==0: conn.commit(); print(f"  {ok+fail}/{len(pending)}...", flush=True)
conn.commit()
try: mgr.Disconnect()
except Exception: pass
print(f"MT5 DONE: ok={ok} fail={fail}")
cur.close(); conn.close()
