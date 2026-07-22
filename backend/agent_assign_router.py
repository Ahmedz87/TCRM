"""Reassign a lead's / client's sales agent — restricted to users with
can_reassign_agent, and every change is written to agent_change_log."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import rbac

router = APIRouter(prefix="/assign", tags=["assign"])


def _require_perm(user):
    # ONLY admins and Rahaf may change a sales agent (rbac.may_reassign_agent).
    if not rbac.may_reassign_agent(user):
        raise HTTPException(status_code=403, detail="You are not allowed to change the sales agent")


@router.get("/agents")
def assignable_agents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Sales people a lead/client can be assigned to (sales + retention + managers + director).
    #276: retention staff carry role='sales_agent' but are tagged team_type='retention' (and a few
    legacy rows use role='retention'/'retention_agent') — key off BOTH so they always appear."""
    rows = db.execute(text("""
        SELECT id, full_name, role, COALESCE(team_type,'') FROM users
        WHERE is_active AND (
              role IN ('sales_agent','sales_manager','director','retention','retention_agent')
              OR team_type = 'retention')
        ORDER BY full_name
    """)).fetchall()
    return {"agents": [{"id": r[0], "name": r[1], "role": r[2], "team_type": r[3]} for r in rows]}


def _agent_name(db, agent_id):
    if not agent_id:
        return None
    r = db.execute(text("SELECT full_name FROM users WHERE id=:i"), {"i": agent_id}).fetchone()
    return r[0] if r else None


def _log(db, etype, ref, ename, old_id, new_id, user):
    db.execute(text("""
        INSERT INTO agent_change_log (entity_type, entity_ref, entity_name, old_agent_id,
            old_agent_name, new_agent_id, new_agent_name, changed_by, changed_by_name, created_at)
        VALUES (:t,:ref,:en,:oid,:on,:nid,:nn,:by,:byn,NOW())
    """), {"t": etype, "ref": ref, "en": ename,
           "oid": old_id, "on": _agent_name(db, old_id),
           "nid": new_id, "nn": _agent_name(db, new_id),
           "by": user.id, "byn": user.full_name})


@router.post("/lead/{lead_id}")
def assign_lead(lead_id: int, data: dict, db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    _require_perm(current_user)
    new_id = data.get("agent_id") or None
    row = db.execute(text("SELECT assigned_agent_id, full_name FROM leads WHERE id=:i"), {"i": lead_id}).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    old_id = row[0]
    db.execute(text("UPDATE leads SET assigned_agent_id=:a, updated_at=NOW() WHERE id=:i"),
               {"a": new_id, "i": lead_id})
    _log(db, "lead", lead_id, row[1], old_id, new_id, current_user)
    db.commit()
    return {"ok": True, "agent_id": new_id, "agent_name": _agent_name(db, new_id)}


@router.post("/client/{login}")
def assign_client(login: int, data: dict, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """Reassign a client. Applies to ALL of the person's accounts (same phone)."""
    _require_perm(current_user)
    new_id = data.get("agent_id") or None
    row = db.execute(text("SELECT assigned_agent_id, name, phone FROM clients WHERE login=:l"), {"l": login}).fetchone()
    if not row:
        raise HTTPException(404, "Client not found")
    old_id, name, phone = row
    if phone and phone not in ("", "0"):
        n = db.execute(text("UPDATE clients SET assigned_agent_id=:a WHERE phone=:p"),
                       {"a": new_id, "p": phone}).rowcount
    else:
        n = db.execute(text("UPDATE clients SET assigned_agent_id=:a WHERE login=:l"),
                       {"a": new_id, "l": login}).rowcount
    _log(db, "client", login, name, old_id, new_id, current_user)
    db.commit()
    return {"ok": True, "agent_id": new_id, "agent_name": _agent_name(db, new_id), "accounts_updated": n}


@router.get("/log")
def change_log(entity_type: str = "", entity_ref: int = 0, limit: int = 50,
               db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Recent agent-change history. Filter by a specific entity, or omit for the latest global log."""
    where, params = "WHERE 1=1", {"lim": limit}
    if entity_type:
        where += " AND entity_type=:t"; params["t"] = entity_type
    if entity_ref:
        where += " AND entity_ref=:r"; params["r"] = entity_ref
    rows = db.execute(text(f"""
        SELECT entity_type, entity_ref, entity_name, old_agent_name, new_agent_name,
               changed_by_name, created_at
        FROM agent_change_log {where} ORDER BY id DESC LIMIT :lim
    """), params).fetchall()
    return {"log": [{
        "entity_type": r[0], "entity_ref": r[1], "entity_name": r[2],
        "from": r[3] or "—", "to": r[4] or "—",
        "by": r[5], "at": str(r[6]),
    } for r in rows]}
