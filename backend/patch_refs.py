p = r"C:\broker-crm\backend\loyalty_router.py"
s = open(p, encoding="utf-8").read()
old = '''    referrer = payload.get("referrer_client_id")
    referred_login = payload.get("referred_login")
    bonus = float(payload.get("bonus_points", 50))
    db.execute(text("""INSERT INTO loyalty_referrals (referrer_client_id, referred_login, bonus_points, status)
                       VALUES (:r,:l,:b,'pending')"""),
               {"r": referrer, "l": referred_login, "b": bonus})
    db.commit()
    return {"ok": True, "message": "Referral recorded", "bonus_points": bonus}'''
new = '''    referrer = payload.get("referrer_client_id")
    referred_login = payload.get("referred_login")
    bonus = float(payload.get("bonus_points", 100))
    name = payload.get("referred_name", "")
    phone = payload.get("referred_phone", "")
    try:
        db.execute(text("ALTER TABLE loyalty_referrals ADD COLUMN IF NOT EXISTS referred_name VARCHAR(120)"))
        db.execute(text("ALTER TABLE loyalty_referrals ADD COLUMN IF NOT EXISTS referred_phone VARCHAR(40)"))
        db.commit()
    except Exception:
        db.rollback()
    db.execute(text("""INSERT INTO loyalty_referrals
                       (referrer_client_id, referred_login, referred_name, referred_phone, bonus_points, status)
                       VALUES (:r,:l,:n,:p,:b,'invited')"""),
               {"r": referrer, "l": referred_login or 0, "n": name, "p": phone, "b": bonus})
    db.commit()
    return {"ok": True, "message": "Invite recorded", "bonus_points": bonus}


@router.get("/referrals/{client_id}")
def referrals(client_id: int, db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT id, referred_name, referred_phone, referred_login, bonus_points, status, created_at
        FROM loyalty_referrals WHERE referrer_client_id=:id ORDER BY id DESC LIMIT 50
    """), {"id": client_id}).fetchall()
    won = sum(1 for r in rows if r[5] == "won")
    pend = ("invited","pending","pending_admin_review","registered","verified","funded")
    pending = sum(1 for r in rows if r[5] in pend)
    return {"client_id": client_id,
        "summary": {"total": len(rows), "won": won, "pending": pending,
                    "points_earned": sum(float(r[4] or 0) for r in rows if r[5]=="won")},
        "invites": [{"id": r[0], "name": r[1] or chr(8212), "phone": r[2] or "", "login": r[3],
                     "bonus": float(r[4] or 0), "status": r[5],
                     "date": str(r[6])[:10] if r[6] else None} for r in rows]}'''
if old in s:
    s = s.replace(old, new); open(p,"w",encoding="utf-8").write(s)
    print("router: invite + referrals list added")
else:
    print("OLD PATTERN NOT FOUND - referral endpoint may differ; paste lines around @router.post referral")
import py_compile; py_compile.compile(p, doraise=True); print("compiles OK")
