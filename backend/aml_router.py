# -*- coding: utf-8 -*-
"""AML / sanctions compliance API (P0-16). Review queue for onboarding sanctions matches, ad-hoc
name screening, list stats/refresh, and threshold tuning. Compliance roles only.

Mounted in main.py. Screening itself lives in aml_screening.py; lists load via aml_load.py."""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, SessionLocal
from auth import get_current_user
import aml_screening as A

router = APIRouter(prefix="/aml", tags=["aml"])

COMPLIANCE_ROLES = {"super_admin", "admin", "backoffice", "validation", "director"}


def _require_compliance(user):
    if (getattr(user, "role", "") or "").lower() not in COMPLIANCE_ROLES:
        raise HTTPException(status_code=403, detail="Compliance roles only")
    return user


@router.get("/hits")
def list_hits(status: str = "pending", limit: int = 200, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    _require_compliance(user)
    A.ensure_schema(db)
    limit = max(1, min(int(limit or 200), 1000))
    rows = db.execute(text("""
        SELECT h.id, h.subject_type, h.subject_id, h.source, h.matched_name, h.entity_type,
               h.programs, h.score, h.status, h.reviewed_by, h.reviewed_at, h.note, h.created_at,
               s.name_screened, s.dob AS subj_dob,
               e.primary_name, e.dob AS entity_dob, e.nationality
        FROM aml_hits h
        LEFT JOIN aml_screenings s ON s.id = h.screening_id
        LEFT JOIN sanctions_entities e ON e.id = h.entity_id
        WHERE (:st = 'all' OR h.status = :st)
        ORDER BY (h.status='pending') DESC, h.score DESC, h.created_at DESC
        LIMIT :lim
    """), {"st": status, "lim": limit}).mappings().all()
    return {"status": status, "count": len(rows), "hits": [dict(r) for r in rows]}


@router.get("/stats")
def stats(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_compliance(user)
    A.ensure_schema(db)
    by_src = {r[0]: r[1] for r in db.execute(text(
        "SELECT source, count(*) FROM sanctions_entities GROUP BY source")).fetchall()}
    by_status = {r[0]: r[1] for r in db.execute(text(
        "SELECT status, count(*) FROM aml_hits GROUP BY status")).fetchall()}
    names = db.execute(text("SELECT count(*) FROM sanctions_names")).scalar()
    last = db.execute(text("SELECT max(updated_at) FROM sanctions_entities")).scalar()
    screened = db.execute(text("SELECT count(*) FROM aml_screenings")).scalar()
    return {"list_entities": by_src, "name_variants": names, "lists_updated": str(last) if last else None,
            "screenings_run": screened, "hits_by_status": by_status,
            "match_threshold": A.get_threshold(db), "block_threshold": A.get_block_threshold(db)}


def _resolve(db, hit_id, new_status, user, request, note):
    A.ensure_schema(db)
    h = db.execute(text("SELECT id, subject_type, subject_id, status FROM aml_hits WHERE id=:i"),
                   {"i": hit_id}).fetchone()
    if not h:
        raise HTTPException(status_code=404, detail="hit not found")
    old = h[3]
    db.execute(text("""UPDATE aml_hits SET status=:s, reviewed_by=:by, reviewed_at=NOW(), note=:n WHERE id=:i"""),
               {"s": new_status, "by": (getattr(user, "email", "") or "")[:150], "n": (note or "")[:1000], "i": hit_id})
    db.commit()
    # immutable audit trail for the compliance decision
    try:
        import audit
        audit.log(db, user, f"aml_{new_status}", "aml_hit", hit_id,
                  {"status": old}, {"status": new_status, "note": note}, request=request)
    except Exception:
        db.rollback()
    return h


@router.post("/hits/{hit_id}/clear")
def clear_hit(hit_id: int, body: dict = None, request: Request = None,
              db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Mark a match as a FALSE POSITIVE / different person. When a registration's last blocking hit
    is cleared, it can be activated (provisioned)."""
    _require_compliance(user)
    note = (body or {}).get("note", "")
    h = _resolve(db, hit_id, "cleared", user, request, note)
    still = A.has_pending_block(db, h[2], h[1]) if h[2] else False
    # lift the hold on the registration once nothing blocking remains
    if h[1] == "registration" and not still:
        db.execute(text("UPDATE registrations SET status='verified' WHERE id=:r AND status='aml_hold'"), {"r": h[2]})
        db.commit()
    return {"ok": True, "status": "cleared", "subject_still_blocked": still}


@router.post("/hits/{hit_id}/confirm")
def confirm_hit(hit_id: int, body: dict = None, request: Request = None,
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Confirm a TRUE sanctions match — the subject stays blocked; the registration is rejected."""
    _require_compliance(user)
    note = (body or {}).get("note", "")
    h = _resolve(db, hit_id, "confirmed", user, request, note)
    if h[1] == "registration" and h[2]:
        db.execute(text("UPDATE registrations SET status='rejected' WHERE id=:r"), {"r": h[2]})
        db.commit()
    return {"ok": True, "status": "confirmed", "subject": [h[1], h[2]]}


@router.post("/screen")
def screen_now(body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Ad-hoc screen an arbitrary name (manual check; does not create a review record)."""
    _require_compliance(user)
    name = (body or {}).get("name", "")
    if not name or len(name.strip()) < 3:
        raise HTTPException(status_code=400, detail="name too short")
    A.ensure_schema(db)
    hits = A.screen(db, name)
    return {"name": name, "clear": not hits, "count": len(hits), "matches": hits}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_compliance(user)
    return {"match_threshold": A.get_threshold(db), "block_threshold": A.get_block_threshold(db),
            "defaults": {"match": A.DEFAULT_THRESHOLD, "block": A.DEFAULT_BLOCK}}


@router.post("/settings")
def set_settings(body: dict, request: Request = None, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    if (getattr(user, "role", "") or "").lower() not in {"super_admin", "admin", "director"}:
        raise HTTPException(status_code=403, detail="Management only")
    for key, sk in (("match_threshold", "aml_match_threshold"), ("block_threshold", "aml_block_threshold")):
        if key in (body or {}):
            v = float(body[key])
            if not (0.5 <= v <= 1.0):
                raise HTTPException(status_code=400, detail=f"{key} must be 0.5–1.0")
            db.execute(text("""INSERT INTO crm_settings (key, val) VALUES (:k, :v)
                               ON CONFLICT (key) DO UPDATE SET val=:v"""), {"k": sk, "v": str(v)})
    db.commit()
    return {"ok": True, "match_threshold": A.get_threshold(db), "block_threshold": A.get_block_threshold(db)}


def _do_refresh():
    db = SessionLocal()
    try:
        import aml_load, tempfile
        A.ensure_schema(db)
        with tempfile.TemporaryDirectory() as wd:
            try:
                aml_load.load_ofac(db, wd)
            except Exception as e:
                db.rollback(); print(f"[aml] OFAC refresh failed: {e}", flush=True)
            try:
                aml_load.load_un(db, wd)
            except Exception as e:
                db.rollback(); print(f"[aml] UN refresh failed: {e}", flush=True)
    finally:
        db.close()


@router.post("/refresh")
def refresh_lists(background: BackgroundTasks, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    """Re-download the sanctions lists (runs in the background; ~10s)."""
    if (getattr(user, "role", "") or "").lower() not in {"super_admin", "admin", "director"}:
        raise HTTPException(status_code=403, detail="Management only")
    background.add_task(_do_refresh)
    return {"ok": True, "message": "Refreshing OFAC + UN lists in the background."}
