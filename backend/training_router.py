"""
training_router.py — Training department module.

Flow: a sales/retention agent flags a lead (or client) as needing training from inside the lead.
It lands on the Training page, where the Training team (role='training') + admins move it through
the stages and manage training materials.

RBAC:
  • create / view-own  — any staff (sales, retention, …); they see ONLY their own submissions.
  • view-all / change stage / manage materials — role in {training, admin, super_admin, director}.
Tables (created by scratchpad/create_training_schema.py): training_requests, training_materials.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/training", tags=["Training"])

STAGES = ["requested", "under_training", "training_done", "first_patch_done", "too_beginner", "trader_loses_alot"]
STAGE_LABELS = {
    "requested": "Requested", "under_training": "Under training", "training_done": "Training done",
    "first_patch_done": "First patch done", "too_beginner": "Too beginner",
    "trader_loses_alot": "Trader (loses a lot)",
}
MANAGE_ROLES = {"training", "admin", "super_admin", "director"}


def _role(u) -> str:
    return (getattr(u, "role", "") or "").lower()


def _can_manage(u) -> bool:
    return _role(u) in MANAGE_ROLES


def _name(u) -> str:
    return getattr(u, "full_name", None) or getattr(u, "email", None) or "Staff"


@router.get("/meta")
def meta(current_user=Depends(get_current_user)):
    """Stage list + whether this user may manage (change stages / materials)."""
    return {"stages": [{"key": k, "label": STAGE_LABELS[k]} for k in STAGES], "can_manage": _can_manage(current_user)}


@router.post("")
def create_request(data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    lead_id = data.get("lead_id")
    client_login = data.get("client_login")
    note = (data.get("note") or "").strip()
    if not lead_id and not client_login:
        raise HTTPException(400, "lead_id or client_login required")

    name = phone = country = customer_no = None
    source = "lead" if lead_id else "client"
    if lead_id:
        r = db.execute(text("SELECT full_name, phone, country, customer_no FROM leads WHERE id=:i"), {"i": lead_id}).fetchone()
        if not r:
            raise HTTPException(404, "Lead not found")
        name, phone, country, customer_no = r[0], r[1], r[2], r[3]
    else:
        r = db.execute(text("SELECT name, phone, country, customer_no FROM clients WHERE login=:l"), {"l": client_login}).fetchone()
        if not r:
            raise HTTPException(404, "Client not found")
        name, phone, country, customer_no = r[0], r[1], r[2], r[3]

    # one active row per lead — re-sending updates the note + bumps it back onto the board
    row = db.execute(text("""
        INSERT INTO training_requests (lead_id, client_login, customer_no, subject_name, phone, country,
                                       source, stage, note, requested_by, requested_by_name)
        VALUES (:lid, :cl, :cn, :nm, :ph, :co, :src, 'requested', :note, :by, :byn)
        ON CONFLICT (lead_id) WHERE lead_id IS NOT NULL
        DO UPDATE SET note = COALESCE(NULLIF(EXCLUDED.note,''), training_requests.note),
                      updated_at = NOW(), updated_by_name = EXCLUDED.requested_by_name
        RETURNING id, stage"""),
        {"lid": lead_id, "cl": client_login, "cn": customer_no, "nm": name, "ph": phone, "co": country,
         "src": source, "note": note, "by": current_user.id, "byn": _name(current_user)}).fetchone()
    db.commit()
    return {"id": row[0], "stage": row[1], "message": "Sent to training"}


@router.get("")
def list_requests(stage: str = Query(""), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    where, params = [], {}
    if stage:
        where.append("stage = :stage"); params["stage"] = stage
    if not _can_manage(current_user):
        where.append("requested_by = :me"); params["me"] = current_user.id
    wc = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(text(f"""
        SELECT id, lead_id, client_login, subject_name, phone, country, source, stage, note,
               requested_by_name, requested_at, trainer_name, updated_at, updated_by_name, customer_no, level
        FROM training_requests {wc}
        ORDER BY (stage='requested') DESC, updated_at DESC NULLS LAST LIMIT 1000"""), params).fetchall()
    counts = {k: 0 for k in STAGES}
    cwc = ""
    cparams = {}
    if not _can_manage(current_user):
        cwc = " WHERE requested_by = :me"; cparams["me"] = current_user.id
    for k, n in db.execute(text(f"SELECT stage, COUNT(*) FROM training_requests{cwc} GROUP BY stage"), cparams).fetchall():
        if k in counts: counts[k] = n
    return {
        "requests": [{
            "id": r[0], "lead_id": r[1], "client_login": r[2], "name": r[3] or "—", "phone": r[4] or "",
            "country": r[5] or "", "source": r[6], "stage": r[7], "stage_label": STAGE_LABELS.get(r[7], r[7]),
            "note": r[8] or "", "requested_by": r[9] or "", "requested_at": str(r[10]) if r[10] else "",
            "trainer": r[11] or "", "updated_at": str(r[12]) if r[12] else "", "updated_by": r[13] or "",
            "customer_no": r[14] or "", "level": r[15] or "",
        } for r in rows],
        "counts": counts, "can_manage": _can_manage(current_user),
    }


@router.patch("/{req_id}")
def update_request(req_id: int, data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _can_manage(current_user):
        raise HTTPException(403, "Only the training team may change training status")
    sets, params = [], {"id": req_id, "by": _name(current_user)}
    if "stage" in data:
        if data["stage"] not in STAGES:
            raise HTTPException(400, "Invalid stage")
        sets.append("stage = :stage"); params["stage"] = data["stage"]
    if "note" in data:
        sets.append("note = :note"); params["note"] = (data.get("note") or "").strip()
    if data.get("claim"):   # trainer claims the case
        sets.append("trainer_id = :tid"); sets.append("trainer_name = :tn")
        params["tid"] = current_user.id; params["tn"] = _name(current_user)
    if not sets:
        raise HTTPException(400, "Nothing to update")
    sets.append("updated_at = NOW()"); sets.append("updated_by_name = :by")
    db.execute(text(f"UPDATE training_requests SET {', '.join(sets)} WHERE id=:id"), params)
    db.commit()
    return {"message": "Updated"}


@router.delete("/{req_id}")
def delete_request(req_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _can_manage(current_user):
        raise HTTPException(403, "Not authorized")
    db.execute(text("DELETE FROM training_requests WHERE id=:id"), {"id": req_id})
    db.commit()
    return {"message": "Deleted"}


# ---- Training materials -----------------------------------------------------
@router.get("/materials")
def list_materials(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.execute(text("SELECT id, title, description, url, category, created_by_name, created_at "
                           "FROM training_materials ORDER BY created_at DESC")).fetchall()
    return {"materials": [{"id": r[0], "title": r[1] or "", "description": r[2] or "", "url": r[3] or "",
                           "category": r[4] or "", "created_by": r[5] or "", "created_at": str(r[6]) if r[6] else ""}
                          for r in rows], "can_manage": _can_manage(current_user)}


@router.post("/materials")
def add_material(data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _can_manage(current_user):
        raise HTTPException(403, "Only the training team may add materials")
    if not (data.get("title") or "").strip():
        raise HTTPException(400, "Title required")
    row = db.execute(text("""INSERT INTO training_materials (title, description, url, category, created_by_name)
        VALUES (:t,:d,:u,:c,:by) RETURNING id"""),
        {"t": data.get("title", "").strip(), "d": (data.get("description") or "").strip(),
         "u": (data.get("url") or "").strip(), "c": (data.get("category") or "").strip(), "by": _name(current_user)}).fetchone()
    db.commit()
    return {"id": row[0], "message": "Material added"}


@router.delete("/materials/{mid}")
def del_material(mid: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not _can_manage(current_user):
        raise HTTPException(403, "Not authorized")
    db.execute(text("DELETE FROM training_materials WHERE id=:i"), {"i": mid})
    db.commit()
    return {"message": "Deleted"}
