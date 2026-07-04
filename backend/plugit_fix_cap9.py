"""Cap Plugit levels at 9 (real max IB group), recompute commission, retry the failed MT5 groups."""
import psycopg2, build_ibs
import mt_managers as M
import MT5Manager as mt5m
import db_config
conn=db_config.connect()
cur=conn.cursor()
# 1) cap synced IBs at level 9
cur.execute("UPDATE ibs SET ib_level=9 WHERE plugit_status='synced' AND ib_level=10")
print("capped ib_level 10->9:", cur.rowcount)
# also fix the plugit source table + client group targets stay computed from level
cur.execute("UPDATE ib_plugit SET level=9 WHERE level=10")
conn.commit()
# 2) recompute commission from new levels
print("recomputing commission..."); cur.execute(build_ibs.VOLUME_SQL); conn.commit()
# 3) retry failed MT5 (targets were IB\IB-10 -> now IB\IB-9)
cur.execute("SELECT DISTINCT login FROM ib_mt_group_log WHERE ok=false AND platform='MT5'")
retry=[r[0] for r in cur.fetchall()]
print("retrying MT5:", retry)
login_c,pw_c=M.MT5["C"]; mgr=mt5m.ManagerAPI()
if not mgr.Connect(M.MT5_SERVER,login_c,pw_c): print("connect failed"); raise SystemExit(1)
def get(login):
    for m in ("UserRequest","UserGet"):
        if hasattr(mgr,m):
            try:
                u=getattr(mgr,m)(int(login))
                if u: return u
            except Exception: pass
    return None
ok=fail=0
for login in retry:
    tgt="IB\IB-9"; err=None; success=False
    try:
        u=get(login)
        if u:
            u.Group=tgt; success=bool(mgr.UserUpdate(u))
            if not success: err="UserUpdate False"
        else: err="not found"
    except Exception as e: err=str(e)
    cur.execute("INSERT INTO ib_mt_group_log(login,platform,old_group,new_group,ok,err) VALUES(%s,'MT5','(retry)',%s,%s,%s)",(login,tgt,success,err))
    if success: ok+=1; cur.execute("UPDATE clients SET group_name=%s WHERE login=%s",(tgt,login))
    else: fail+=1; print("FAIL",login,err)
conn.commit()
try: mgr.Disconnect()
except Exception: pass
print(f"retry done ok={ok} fail={fail}")
cur.close();conn.close()
