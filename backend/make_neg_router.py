content = r'''
"""Negative Balance Protection router"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import models, threading, time
from database import get_db, SessionLocal
from auth import get_current_user

router = APIRouter(prefix="/neg-cover", tags=["neg-cover"])

from mt_secrets import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD

# Auto-cover background state
_auto_running = {"on": False, "thread": None}

def _get_mt5():
    import MT5Manager
    mgr = MT5Manager.ManagerAPI()
    if not mgr.Connect(MT5_SERVER, MT5_LOGIN, MT5_PASSWORD):
        return None
    return mgr

def _is_flat(mgr, login):
    pos = mgr.PositionGet(login)
    return pos is None or len(pos) == 0

def _eval_account(mgr, login):
    """Return dict with eligibility info (no money moved)."""
    acc = mgr.UserAccountGet(login)
    if not acc:
        return None
    bal, cred = float(acc.Balance), float(acc.Credit)
    if bal >= 0:
        return None
    deficit = abs(bal)
    flat = _is_flat(mgr, login)
    if not flat:
        status = "has_positions"
    elif cred < deficit:
        status = "credit_low"
    else:
        status = "eligible"
    return {"login": login, "balance": bal, "credit": cred, "deficit": deficit,
            "cover_amount": min(deficit, cred), "flat": flat, "status": status}

def _do_cover(mgr, login, agent_id=None, mode="manual"):
    """Cover one account. Returns result dict."""
    acc = mgr.UserAccountGet(login)
    if not acc:
        return {"login": login, "status": "no_data"}
    bal, cred = float(acc.Balance), float(acc.Credit)
    if bal >= 0:
        return {"login": login, "status": "not_negative"}
    deficit = abs(bal)
    if not _is_flat(mgr, login):
        return {"login": login, "status": "has_positions"}
    if cred < deficit:
        return {"login": login, "status": "credit_low"}
    # Two-step cover (broker proven pattern)
    mgr.DealerBalance(login, deficit, 5, "Negative balance payoff")
    mgr.DealerBalance(login, -deficit, 3, "Credit Out")
    acc2 = mgr.UserAccountGet(login)
    bal_a, cred_a = float(acc2.Balance), float(acc2.Credit)
    # log it
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO neg_cover_log (login, platform, deficit, cover_amount, balance_before, credit_before, balance_after, credit_after, status, mode, agent_id, created_at)
            VALUES (:l,'MT5',:d,:d,:bb,:cb,:ba,:ca,'covered',:m,:ag,NOW())
        """), {"l":login,"d":deficit,"bb":bal,"cb":cred,"ba":bal_a,"ca":cred_a,"m":mode,"ag":agent_id})
        db.commit()
    finally:
        db.close()
    return {"login": login, "status": "covered", "deficit": deficit,
            "balance_after": bal_a, "credit_after": cred_a}

@router.get("/scan")
def scan(platform: str = "MT5", db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """List all negative accounts with eligibility."""
    rows = db.execute(text("""
        SELECT login, name, balance, no_auto_cover FROM clients
        WHERE balance < 0 AND platform = :p ORDER BY balance ASC
    """), {"p": platform}).fetchall()
    mgr = _get_mt5() if platform == "MT5" else None
    out = []
    for r in rows:
        login, name, db_bal, no_cover = r[0], r[1], float(r[2] or 0), r[3]
        item = {"login": login, "name": name or "", "balance": db_bal,
                "no_auto_cover": bool(no_cover), "status": "unknown",
                "credit": 0, "deficit": abs(db_bal), "cover_amount": 0, "flat": None}
        if mgr:
            ev = _eval_account(mgr, login)
            if ev:
                item.update(ev)
                item["no_auto_cover"] = bool(no_cover)
            else:
                item["status"] = "not_negative_now"
        out.append(item)
    if mgr: mgr.Disconnect()
    return {"platform": platform, "accounts": out,
            "eligible": sum(1 for a in out if a["status"]=="eligible" and not a["no_auto_cover"])}

@router.post("/cover/{login}")
def cover_one(login: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Manually cover one account (works even if no_auto_cover)."""
    mgr = _get_mt5()
    if not mgr:
        return {"error": "MT5 connect failed"}
    r = _do_cover(mgr, login, agent_id=current_user.id, mode="manual")
    mgr.Disconnect()
    return r

@router.post("/cover-all")
def cover_all(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """One sweep: cover all eligible (flat + coverable + not excluded)."""
    rows = db.execute(text("SELECT login FROM clients WHERE balance < 0 AND platform='MT5' AND COALESCE(no_auto_cover,FALSE)=FALSE")).fetchall()
    mgr = _get_mt5()
    if not mgr:
        return {"error": "MT5 connect failed"}
    covered = []
    for (login,) in rows:
        r = _do_cover(mgr, login, agent_id=current_user.id, mode="sweep")
        if r.get("status") == "covered":
            covered.append(r)
    mgr.Disconnect()
    return {"covered_count": len(covered), "covered": covered}

@router.post("/toggle-exclude/{login}")
def toggle_exclude(login: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Toggle the 'don't auto cover' flag."""
    cur = db.execute(text("SELECT COALESCE(no_auto_cover,FALSE) FROM clients WHERE login=:l LIMIT 1"), {"l":login}).scalar()
    newval = not bool(cur)
    db.execute(text("UPDATE clients SET no_auto_cover=:v WHERE login=:l"), {"v":newval,"l":login})
    db.commit()
    return {"login": login, "no_auto_cover": newval}

def _auto_loop():
    while _auto_running["on"]:
        try:
            db = SessionLocal()
            rows = db.execute(text("SELECT login FROM clients WHERE balance < 0 AND platform='MT5' AND COALESCE(no_auto_cover,FALSE)=FALSE")).fetchall()
            db.close()
            mgr = _get_mt5()
            if mgr:
                for (login,) in rows:
                    if not _auto_running["on"]: break
                    _do_cover(mgr, login, mode="auto")
                mgr.Disconnect()
        except Exception as e:
            print(f"auto-cover error: {e}")
        for _ in range(60):
            if not _auto_running["on"]: break
            time.sleep(1)

@router.post("/auto/start")
def auto_start(current_user: models.User = Depends(get_current_user)):
    if not _auto_running["on"]:
        _auto_running["on"] = True
        t = threading.Thread(target=_auto_loop, daemon=True)
        _auto_running["thread"] = t
        t.start()
    return {"auto": True}

@router.post("/auto/stop")
def auto_stop(current_user: models.User = Depends(get_current_user)):
    _auto_running["on"] = False
    return {"auto": False}

@router.get("/auto/status")
def auto_status(current_user: models.User = Depends(get_current_user)):
    return {"auto": _auto_running["on"]}
'''
p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
open(p, "w", encoding="utf-8").write(content)
print("Created neg_cover_router.py")

# Register in main.py
mp = r"C:\broker-crm\backend\main.py"
m = open(mp, encoding="utf-8").read()
if "neg_cover_router" not in m:
    m = m.replace("from routers import auth_router, clients_router",
                  "from routers import auth_router, clients_router, neg_cover_router")
    m = m.replace("app.include_router(clients_router.router)",
                  "app.include_router(clients_router.router)\napp.include_router(neg_cover_router.router)")
    open(mp, "w", encoding="utf-8").write(m)
    print("Registered in main.py")
else:
    print("Already registered")
