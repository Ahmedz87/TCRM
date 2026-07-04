"""Apply MT5 IB-account groups to the fed levels (eligible IBs). Provision login C/3027.
Logs to ib_mt_group_log; does NOT write clients.group_name (bridge re-syncs it -> no deadlock)."""
import psycopg2, mt_managers as M, MT5Manager as mt5m
import db_config
conn=db_config.connect();conn.autocommit=True;cur=conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS ib_mt_group_log(login BIGINT,platform VARCHAR,old_group VARCHAR,new_group VARCHAR,ok BOOLEAN,err VARCHAR,ts TIMESTAMPTZ DEFAULT NOW())""")
cur.execute("""
  WITH ib_person AS (
    SELECT i.id,i.ib_level,i.agent_id,oc.customer_no
    FROM ibs i LEFT JOIN clients oc ON oc.login=i.agent_id
    WHERE i.plugit_status IN ('synced','plugit_only') AND i.ib_level BETWEEN 5 AND 9
  )
  SELECT DISTINCT c.login,c.group_name,p.ib_level
  FROM ib_person p JOIN clients c ON (p.customer_no IS NOT NULL AND c.customer_no=p.customer_no) OR c.login=p.agent_id
  WHERE c.group_name ILIKE '%IB-%' AND COALESCE(c.platform,'MT5') NOT ILIKE 'MT4%'
""")
pend=[]
for login,grp,lvl in cur.fetchall():
    tgt=f"IB\IB-{lvl}"
    if (grp or '')!=tgt: pend.append((login,grp,tgt))
print("MT5 pending:",len(pend))
mgr=mt5m.ManagerAPI()
if not mgr.Connect(M.MT5_SERVER,*M.MT5["C"]): print("connect failed"); raise SystemExit(1)
def get(l):
    for m in ("UserRequest","UserGet"):
        if hasattr(mgr,m):
            try:
                u=getattr(mgr,m)(int(l))
                if u: return u
            except Exception: pass
    return None
ok=fail=0
for login,oldg,tgt in pend:
    err=None;success=False
    try:
        u=get(login)
        if u: u.Group=tgt; success=bool(mgr.UserUpdate(u)); err=None if success else "UserUpdate False"
        else: err="not found"
    except Exception as e: err=str(e)
    cur.execute("INSERT INTO ib_mt_group_log(login,platform,old_group,new_group,ok,err) VALUES(%s,'MT5',%s,%s,%s,%s)",(login,oldg,tgt,success,err))
    ok+=success; fail+=(0 if success else 1)
    if (ok+fail)%100==0: print(f"  {ok+fail}/{len(pend)}...")
try: mgr.Disconnect()
except Exception: pass
print(f"MT5 DONE ok={ok} fail={fail}")
cur.close();conn.close()
