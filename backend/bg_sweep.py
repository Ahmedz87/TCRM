p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Find and replace the cover-all endpoint to run in background
i = s.find('@router.post("/cover-all")')
j = s.find("@router", i+10)
old_block = s[i:j]

new_block = '''@router.post("/cover-all")
def cover_all(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Sweep: cover all eligible in the BACKGROUND. Returns immediately."""
    rows = db.execute(text("SELECT login FROM clients WHERE balance < 0 AND platform='MT5' AND COALESCE(no_auto_cover,FALSE)=FALSE")).fetchall()
    logins = [r[0] for r in rows]
    agent_id = current_user.id
    def _sweep():
        for login in logins:
            try:
                _do_cover(None, login, agent_id=agent_id, mode="sweep")
            except Exception as e:
                print(f"sweep cover error #{login}: {e}")
    t = threading.Thread(target=_sweep, daemon=True)
    t.start()
    return {"started": True, "queued": len(logins), "message": f"Sweeping {len(logins)} accounts in background"}

'''

s = s.replace(old_block, new_block)
open(p, "w", encoding="utf-8").write(s)
print("Sweep now runs in background, returns immediately")
print("Queued count returned:", "queued" in s)

import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
