"""
Bonus system API — two routers:
  • portal_bonus  (prefix /portal/bonus, client auth)  → status / claim / preview
  • admin_bonus   (prefix /admin/bonus, staff auth)    → config / offers CRUD / grants / stats
Logic lives in bonus_engine.py.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from portal_router import get_current_client, block_impersonation
from auth import get_current_user
import bonus_engine as BE
import birthday_engine as BD

portal_bonus = APIRouter(prefix="/portal/bonus", tags=["portal-bonus"])
admin_bonus = APIRouter(prefix="/admin/bonus", tags=["admin-bonus"])


# ═════════════════════════ PORTAL (client) ═════════════════════════
@portal_bonus.get("/status")
def status(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    return BE.bonus_status(db, client_id)


@portal_bonus.post("/welcome/claim")
def claim_welcome(background: BackgroundTasks, client_id: int = Depends(get_current_client),
                  _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    res = BE.claim_welcome(db, client_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "Not eligible"))
    # push the real MT credit + email in the BACKGROUND so the button returns instantly and the KPI
    # rolls straight to the next bonus (50% deposit).
    background.add_task(BE.push_welcome_credit, client_id)
    return res


@portal_bonus.post("/birthday/claim")
def claim_birthday(background: BackgroundTasks, client_id: int = Depends(get_current_client),
                   _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    res = BD.claim_birthday(db, client_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "Not eligible"))
    # push the real MT credit + email in the BACKGROUND so the button returns instantly.
    background.add_task(BD.push_birthday_credit, client_id)
    return res


@portal_bonus.post("/preview-deposit")
def preview_deposit(payload: dict, client_id: int = Depends(get_current_client),
                    db: Session = Depends(get_db)):
    amount = float(payload.get("amount") or 0)
    login = payload.get("login")
    return BE.preview_deposit_bonus(db, client_id, amount, login)


@portal_bonus.post("/withdraw-check")
def withdraw_check(payload: dict, client_id: int = Depends(get_current_client),
                   db: Session = Depends(get_db)):
    amount = float(payload.get("amount") or 0)
    return BE.withdraw_check(db, client_id, amount)


# ═════════════════════════ ADMIN (staff) ═════════════════════════
@admin_bonus.get("/config")
def get_config(db: Session = Depends(get_db), _=Depends(get_current_user)):
    cfg = BE.get_config(db)
    return {"config": cfg, "defaults": BE.DEFAULTS}


@admin_bonus.put("/config")
def put_config(payload: dict, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cfg = BE.save_config(db, payload or {})
    return {"ok": True, "config": cfg}


@admin_bonus.get("/offers")
def list_offers(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT id,name,percent,cap,min_deposit,countries,starts_at,ends_at,active,created_at
        FROM bonus_offers ORDER BY active DESC, ends_at NULLS LAST, id DESC
    """)).fetchall()
    return {"offers": [{
        "id": r[0], "name": r[1], "percent": float(r[2] or 0), "cap": float(r[3] or 0),
        "min_deposit": float(r[4] or 0), "countries": r[5] or [],
        "starts_at": str(r[6]) if r[6] else None, "ends_at": str(r[7]) if r[7] else None,
        "active": bool(r[8]), "created_at": str(r[9]) if r[9] else None,
    } for r in rows]}


@admin_bonus.post("/offers")
def create_offer(payload: dict, db: Session = Depends(get_db), _=Depends(get_current_user)):
    import json as _json
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Offer name is required")
    db.execute(text("""
        INSERT INTO bonus_offers (name, percent, cap, min_deposit, countries, starts_at, ends_at, active)
        VALUES (:n,:p,:cap,:md,CAST(:cc AS JSONB),
                NULLIF(:sa,'')::timestamp, NULLIF(:ea,'')::timestamp, :act)
    """), {"n": name, "p": float(payload.get("percent") or 0), "cap": float(payload.get("cap") or 0),
           "md": float(payload.get("min_deposit") or 0),
           "cc": _json.dumps(payload.get("countries") or []),
           "sa": payload.get("starts_at") or "", "ea": payload.get("ends_at") or "",
           "act": bool(payload.get("active", True))})
    db.commit()
    return {"ok": True}


@admin_bonus.put("/offers/{offer_id}")
def update_offer(offer_id: int, payload: dict, db: Session = Depends(get_db),
                 _=Depends(get_current_user)):
    import json as _json
    db.execute(text("""
        UPDATE bonus_offers SET
            name=COALESCE(NULLIF(:n,''), name),
            percent=:p, cap=:cap, min_deposit=:md, countries=CAST(:cc AS JSONB),
            starts_at=NULLIF(:sa,'')::timestamp, ends_at=NULLIF(:ea,'')::timestamp, active=:act
        WHERE id=:id
    """), {"id": offer_id, "n": (payload.get("name") or "").strip(),
           "p": float(payload.get("percent") or 0), "cap": float(payload.get("cap") or 0),
           "md": float(payload.get("min_deposit") or 0),
           "cc": _json.dumps(payload.get("countries") or []),
           "sa": payload.get("starts_at") or "", "ea": payload.get("ends_at") or "",
           "act": bool(payload.get("active", True))})
    db.commit()
    return {"ok": True}


@admin_bonus.patch("/offers/{offer_id}/toggle")
def toggle_offer(offer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    db.execute(text("UPDATE bonus_offers SET active = NOT active WHERE id=:id"), {"id": offer_id})
    db.commit()
    return {"ok": True}


@admin_bonus.delete("/offers/{offer_id}")
def delete_offer(offer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    db.execute(text("DELETE FROM bonus_offers WHERE id=:id"), {"id": offer_id})
    db.commit()
    return {"ok": True}


@admin_bonus.get("/birthdays")
def list_birthdays(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Clients whose birthday falls in the claim window today, with greeted/claimed/eligible state."""
    return {"birthdays": BD.list_birthdays(db)}


@admin_bonus.get("/grants")
def list_grants(limit: int = 100, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT g.id, g.client_id, c.name, g.login, g.kind, g.deposit_amount, g.amount,
               g.clawed_back, g.status, g.created_at
        FROM bonus_grants g LEFT JOIN clients c ON c.id = g.client_id
        ORDER BY g.id DESC LIMIT :lim
    """), {"lim": min(limit, 500)}).fetchall()
    return {"grants": [{
        "id": r[0], "client_id": r[1], "client": r[2] or "", "login": r[3], "kind": r[4],
        "deposit": float(r[5] or 0), "amount": float(r[6] or 0), "clawed_back": float(r[7] or 0),
        "status": r[8], "date": str(r[9])[:16] if r[9] else None,
    } for r in rows]}


@admin_bonus.get("/stats")
def stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT
          COALESCE(SUM(CASE WHEN kind='welcome' THEN amount ELSE 0 END),0),
          COALESCE(SUM(CASE WHEN kind IN ('deposit_50','deposit_20') THEN amount ELSE 0 END),0),
          COALESCE(SUM(CASE WHEN kind='special' THEN amount ELSE 0 END),0),
          COALESCE(SUM(clawed_back),0),
          COUNT(DISTINCT client_id)
        FROM bonus_grants WHERE status<>'cancelled'
    """)).fetchone()
    return {"welcome_total": float(row[0] or 0), "deposit_total": float(row[1] or 0),
            "special_total": float(row[2] or 0), "clawed_back": float(row[3] or 0),
            "clients": int(row[4] or 0)}


# ───────────────────────── WELCOME-BONUS REVIEW QUEUE (admin) ─────────────────────────
@admin_bonus.get("/reviews")
def list_welcome_reviews(status: str = "pending", db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Welcome-bonus cases held for team review (exactly 2 of IB/City/Family/IP matched another
    account that already got the bonus). status: pending | approved | rejected | '' (all)."""
    return {"reviews": BE.list_welcome_reviews(db, status=status)}


@admin_bonus.post("/reviews/{review_id}/decision")
def decide_welcome_review(review_id: int, payload: dict, db: Session = Depends(get_db),
                          user=Depends(get_current_user)):
    """Approve (-> credits the $50 welcome bonus now) or reject (-> blocks it) a review case."""
    decision = (payload.get("decision") or "").lower()
    if decision not in ("approve", "reject"):
        return {"ok": False, "error": "decision must be 'approve' or 'reject'"}
    by = getattr(user, "email", None) or getattr(user, "full_name", None) or "staff"
    return BE.decide_welcome_review(db, review_id, decision, by=by)
