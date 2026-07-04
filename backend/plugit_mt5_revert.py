"""UNDO: revert the MT5 IB-account groups I changed last night back to their ORIGINAL groups."""
import psycopg2, mt_managers as M, MT5Manager as mt5m
import db_config
conn=db_config.connect();cur=conn.cursor()
cur.execute("SELECT login, MAX(CASE WHEN old_group NOT LIKE '(%%' THEN old_group END) FROM ib_mt_group_log GROUP BY login")
revert={l:g for l,g in cur.fetchall() if g}
revert[335000009] = "IB\IB-7"   # the one-account test, not in the log
print("accounts to revert:", len(revert))
mgr=mt5m.ManagerAPI()
if not mgr.Connect(M.MT5_SERVER, *M.MT5["C"]): print("connect failed"); raise SystemExit(1)
def get(login):
    for m in ("UserRequest","UserGet"):
        if hasattr(mgr,m):
            try:
                u=getattr(mgr,m)(int(login))
                if u: return u
            except Exception: pass
    return None
ok=fail=0
for login,orig in revert.items():
    try:
        u=get(login)
        if u:
            u.Group=orig
            if mgr.UserUpdate(u):
                ok+=1; cur.execute("UPDATE clients SET group_name=%s WHERE login=%s",(orig,login))
            else: fail+=1; print("FAIL",login,"->",orig)
        else: fail+=1; print("not found",login)
    except Exception as e: fail+=1; print("ERR",login,e)
    if (ok+fail)%50==0: conn.commit()
conn.commit()
try: mgr.Disconnect()
except Exception: pass
# clear the log so a fresh feed starts clean
cur.execute("DROP TABLE IF EXISTS ib_mt_group_log"); conn.commit()
print(f"MT5 REVERT DONE: ok={ok} fail={fail} (log table dropped)")
cur.close();conn.close()
