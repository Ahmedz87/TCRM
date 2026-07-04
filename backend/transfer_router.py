"""
transfer_router.py — endpoints for the client/lead transfer system (Phases C + D).
Mounted in main.py. All ownership moves go through transfer_engine (audit log + on-record comment).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import transfer_engine as TE

router = APIRouter(prefix="/transfer", tags=["transfer"])

MANAGER_ROLES = {"super_admin", "admin", "director", "sales_manager"}


def _can_manage(user) -> bool:
    role = (getattr(user, "role", "") or "").lower()
    title = (getattr(user, "title", "") or "").lower()
    return role in MANAGER_ROLES or "team leader" in title


def _ensure(db):
    TE.ensure_schema(db)


# ── target picker + cap awareness ──────────────────────────────────────────────
@router.get("/agents")
def transfer_agents(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    return {"agents": TE.agent_caps_overview(db)}


@router.get("/book")
def book(agent_id: int, record_type: str = "client", db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Book size + distinct countries/cities for an agent — live total + dropdown options."""
    return TE.book_meta(db, record_type, agent_id)


# ── preview (dry-run): how many match + how the split lands ─────────────────────
@router.post("/preview")
def preview(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not _can_manage(user):
        raise HTTPException(403, "Only managers / team leaders can transfer in bulk.")
    _ensure(db)
    from_agent = int(payload.get("from_agent_id") or 0)
    rtype = payload.get("record_type", "client")
    filters = payload.get("filters") or {}
    targets = payload.get("targets") or []
    matched = TE.count_book(db, rtype, from_agent, filters)
    res = {"matched": matched}
    if targets:
        res = TE.bulk_transfer(db, from_agent, rtype, filters, targets, payload.get("reason", ""), user, dry_run=True)
        res["matched"] = matched
    return res


# ── execute bulk transfer ───────────────────────────────────────────────────────
@router.post("/bulk")
def bulk(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not _can_manage(user):
        raise HTTPException(403, "Only managers / team leaders can transfer in bulk.")
    _ensure(db)
    from_agent = int(payload.get("from_agent_id") or 0)
    rtype = payload.get("record_type", "client")
    targets = payload.get("targets") or []
    if not from_agent or not targets:
        raise HTTPException(400, "from_agent_id and at least one target are required.")
    return TE.bulk_transfer(db, from_agent, rtype, payload.get("filters") or {}, targets,
                            payload.get("reason", ""), user, dry_run=False)


# ── auto-distribute (separate rule: internal / external / all-company) ───────────
@router.post("/auto-distribute")
def auto_distribute(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not _can_manage(user):
        raise HTTPException(403, "Only managers / team leaders can auto-distribute.")
    _ensure(db)
    from_agent = int(payload.get("from_agent_id") or 0)
    scope = payload.get("scope", "internal")   # internal | external | all
    if scope not in ("internal", "external", "all"):
        raise HTTPException(400, "scope must be internal|external|all")
    return TE.auto_distribute(db, from_agent, payload.get("record_type", "client"), scope,
                              payload.get("filters") or {}, payload.get("reason", ""), user,
                              dry_run=bool(payload.get("dry_run")))


# ── transfer-out of my data (agent self-service from client page / call popup) ──
@router.post("/out")
def transfer_out(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    rtype = payload.get("record_type", "client")
    key = payload.get("record_key")
    if not key:
        raise HTTPException(400, "record_key required.")
    return TE.transfer_out(db, rtype, key, user, payload.get("reason", ""))


# ── manager's pending-request queue ─────────────────────────────────────────────
@router.get("/requests")
def list_requests(status: str = "pending", db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    where = ["status = :st"]
    p = {"st": status}
    # a manager sees requests addressed to them; admins/directors see all
    if not ((getattr(user, "role", "") or "").lower() in ("super_admin", "admin", "director")):
        where.append("manager_id = :me"); p["me"] = user.id
    rows = db.execute(text(f"""
        SELECT r.id, r.record_type, r.record_key, r.from_agent_id, u.full_name, r.reason,
               r.created_at, r.status,
               CASE WHEN r.record_type='client' THEN (SELECT name FROM clients WHERE login=r.record_key)
                    ELSE (SELECT full_name FROM leads WHERE id=r.record_key) END AS record_name
        FROM transfer_requests r LEFT JOIN users u ON u.id = r.requested_by_id
        WHERE {' AND '.join(where)} ORDER BY r.created_at DESC LIMIT 300
    """), p).fetchall()
    return {"requests": [{
        "id": r[0], "record_type": r[1], "record_key": r[2], "from_agent_id": r[3],
        "requested_by": r[4] or "", "reason": r[5] or "", "at": str(r[6])[:16],
        "status": r[7], "record_name": r[8] or "",
    } for r in rows]}


@router.post("/requests/{rid}/resolve")
def resolve_request(rid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Manager resolves a transfer-out request: optionally reassign to a chosen agent, then close it."""
    if not _can_manage(user):
        raise HTTPException(403, "Only a manager can resolve transfer requests.")
    _ensure(db)
    r = db.execute(text("SELECT record_type, record_key, status FROM transfer_requests WHERE id=:i"),
                   {"i": rid}).fetchone()
    if not r:
        raise HTTPException(404, "Request not found.")
    to_agent = int(payload.get("to_agent_id") or 0)
    action = payload.get("action", "assign")   # assign | reject
    if action == "assign" and to_agent:
        TE.reassign(db, r[0], [r[1]], to_agent, user, payload.get("reason", "manager reassignment"))
    db.execute(text("UPDATE transfer_requests SET status=:s, to_agent_id=:to, resolved_at=NOW() WHERE id=:i"),
               {"s": "rejected" if action == "reject" else "done", "to": to_agent or None, "i": rid})
    db.commit()
    return {"ok": True}


# ── auto sales→retention handover (admin / scheduled) ───────────────────────────
@router.post("/auto-handover")
def auto_handover(payload: dict = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not _can_manage(user):
        raise HTTPException(403, "Managers only.")
    _ensure(db)
    return TE.auto_retention_handover(db, by_user=user, dry_run=bool((payload or {}).get("dry_run")))


# ── audit log ───────────────────────────────────────────────────────────────────
@router.get("/log")
def transfer_log(limit: int = 100, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    rows = db.execute(text("""
        SELECT l.created_at, l.record_type, l.record_key, fa.full_name, ta.full_name, l.by_user_name, l.reason
        FROM transfer_log l
        LEFT JOIN users fa ON fa.id = l.from_agent_id
        LEFT JOIN users ta ON ta.id = l.to_agent_id
        ORDER BY l.id DESC LIMIT :lim
    """), {"lim": min(limit, 500)}).fetchall()
    return {"log": [{
        "at": str(r[0])[:16], "record_type": r[1], "record_key": r[2],
        "from": r[3] or "—", "to": r[4] or "—", "by": r[5] or "", "reason": r[6] or "",
    } for r in rows]}
