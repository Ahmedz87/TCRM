p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Fix /cover/{login} - remove _get_mt5(), call _do_cover directly
old1 = '''def cover_one(login: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Manually cover one account (works even if no_auto_cover)."""
    mgr = _get_mt5()
    if not mgr:
        return {"error": "MT5 connect failed"}
    r = _do_cover(mgr, login, agent_id=current_user.id, mode="manual")
    mgr.Disconnect()
    return r'''
new1 = '''def cover_one(login: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Manually cover one account (works even if no_auto_cover). Uses bridge."""
    return _do_cover(None, login, agent_id=current_user.id, mode="manual")'''
if old1 in s:
    s = s.replace(old1, new1)
    print("Fixed /cover/{login}")

# Fix /cover-all (sweep) - remove _get_mt5()
old2 = '''    mgr = _get_mt5()
    if not mgr:
        return {"error": "MT5 connect failed"}
    covered = []
    for (login,) in rows:
        r = _do_cover(mgr, login, agent_id=current_user.id, mode="sweep")
        if r.get("status") == "covered":
            covered.append(r)
    mgr.Disconnect()'''
new2 = '''    covered = []
    for (login,) in rows:
        r = _do_cover(None, login, agent_id=current_user.id, mode="sweep")
        if r.get("status") == "covered":
            covered.append(r)'''
if old2 in s:
    s = s.replace(old2, new2)
    print("Fixed /cover-all (sweep)")

open(p, "w", encoding="utf-8").write(s)

# verify no _get_mt5 calls remain in cover paths
remaining = s.count("_get_mt5()")
print(f"Remaining _get_mt5() calls: {remaining}")
import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
