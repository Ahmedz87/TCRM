p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Add a helper to call the bridge, and rewrite _do_cover to use it
if "BRIDGE_URL" not in s:
    # Add bridge URL constant near the top after imports
    s = s.replace(
        'MT5_SERVER, MT5_LOGIN, MT5_PASSWORD = "192.109.15.62:443", 1025, "PW_MOVED_TO_mt_secrets"',
        'MT5_SERVER, MT5_LOGIN, MT5_PASSWORD = "192.109.15.62:443", 1025, "PW_MOVED_TO_mt_secrets"\nBRIDGE_URL = "http://localhost:5000"'
    )

# Replace _do_cover entirely to call the bridge
import re
old_do_cover_start = s.find("def _do_cover(")
old_do_cover_end = s.find("\n@router", old_do_cover_start)
if old_do_cover_end < 0:
    old_do_cover_end = s.find("\ndef ", old_do_cover_start + 10)

new_do_cover = '''def _do_cover(mgr, login, agent_id=None, mode="manual"):
    """Cover one account via the BRIDGE (which owns the live MT5 connection)."""
    import urllib.request as _u, json as _j
    try:
        req = _u.Request(f"{BRIDGE_URL}/neg-cover/cover/{login}", method="POST")
        r = _j.loads(_u.urlopen(req, timeout=30).read())
    except Exception as e:
        return {"login": login, "status": "error", "error": str(e)}
    # Log if covered
    if r.get("status") == "covered":
        db = SessionLocal()
        try:
            db.execute(text("""
                INSERT INTO neg_cover_log (login, platform, deficit, cover_amount, balance_after, credit_after, status, mode, agent_id, created_at)
                VALUES (:l,'MT5',:d,:d,:ba,:ca,'covered',:m,:ag,NOW())
            """), {"l":login,"d":r.get("deficit",0),"ba":r.get("balance_after",0),"ca":r.get("credit_after",0),"m":mode,"ag":agent_id})
            db.commit()
        finally:
            db.close()
    return r

'''

s = s[:old_do_cover_start] + new_do_cover + s[old_do_cover_end+1:]
open(p, "w", encoding="utf-8").write(s)
print("Rewired _do_cover to call bridge")
print("BRIDGE_URL set:", "BRIDGE_URL" in s)
print("Calls bridge:", "/neg-cover/cover/" in s)

# verify syntax
import py_compile
try:
    py_compile.compile(p, doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
