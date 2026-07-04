p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

if '/verify/' not in s:
    # Add a verify endpoint that calls the bridge inspect
    endpoint = '''
@router.get("/verify/{login}")
def verify_account(login: int, current_user: models.User = Depends(get_current_user)):
    """Live-check one account via bridge: balance, credit, positions, floating PnL."""
    import urllib.request as _u, json as _j
    try:
        d = _j.loads(_u.urlopen(f"{BRIDGE_URL}/neg-cover/inspect/{login}", timeout=10).read())
    except Exception as e:
        return {"login": login, "error": str(e)}
    bal = d.get("Balance", 0)
    cred = d.get("Credit", 0)
    npos = d.get("positions", 0)
    pnl = d.get("floating_pnl", 0)
    deficit = abs(bal) if bal < 0 else 0
    # Determine status with the live data
    if bal >= 0:
        status = "not_negative_now"
    elif npos > 0 and pnl >= 10:
        status = "has_positions_positive_pnl"
    elif bal >= -200 or cred >= deficit * 0.5 or cred >= deficit:
        status = "eligible"
    else:
        status = "credit_low"
    return {"login": login, "balance": bal, "credit": cred, "deficit": deficit,
            "positions": npos, "floating_pnl": pnl, "status": status}
'''
    # insert before the auto endpoints
    anchor = '@router.post("/auto/start")'
    s = s.replace(anchor, endpoint + "\n" + anchor)
    open(p, "w", encoding="utf-8").write(s)
    print("Verify endpoint added")
else:
    print("Already present")

import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
