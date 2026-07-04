"""
lead_rules_router.py — admin API for the Leads Settings page (lead assignment rules).

Mounted in main.py. Prefix /settings/leads. Staff auth (get_current_user).
The routing logic itself lives in lead_routing.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user
import lead_routing

router = APIRouter(prefix="/settings/leads", tags=["leads-settings"])

# common ad sources to offer in the rule builder (data today is fb/ig; others are future-proof)
SOURCE_OPTIONS = ["facebook", "instagram", "tiktok", "google", "snapchat",
                  "twitter", "youtube", "linkedin", "whatsapp", "referral",
                  "organic", "registration", "website"]


def _clean_criteria(c):
    c = c or {}
    out = {}
    for k in ("countries", "cities", "campaigns", "sources"):
        v = c.get(k)
        if v:
            out[k] = [str(x) for x in (v if isinstance(v, list) else [v]) if str(x).strip()]
    if c.get("ib_ids"):
        try:
            out["ib_ids"] = [int(x) for x in c["ib_ids"]]
        except Exception:
            pass
    t = c.get("timing") or {}
    timing = {}
    if t.get("days"):
        timing["days"] = [int(d) for d in t["days"] if str(d).strip() != ""]
    if t.get("from"):
        timing["from"] = str(t["from"])
    if t.get("to"):
        timing["to"] = str(t["to"])
    if timing:
        out["timing"] = timing
    return out


def _rule_out(r):
    return {"id": r[0], "name": r[1], "priority": r[2], "is_active": bool(r[3]),
            "criteria": r[4] or {}, "agent_ids": list(r[5] or []),
            "created_at": str(r[6])[:16] if r[6] else None,
            "updated_at": str(r[7])[:16] if r[7] else None}


# ───────────────────────── rules CRUD ─────────────────────────
@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user=Depends(get_current_user)):
    lead_routing.ensure_schema(db)
    rows = db.execute(text("""
        SELECT id, name, priority, is_active, criteria, agent_ids, created_at, updated_at
        FROM lead_assignment_rules
        ORDER BY priority DESC, id ASC
    """)).fetchall()
    rules = [_rule_out(r) for r in rows]
    # attach agent display names
    ids = sorted({a for r in rules for a in r["agent_ids"]})
    names = {}
    if ids:
        for uid, nm in db.execute(text("SELECT id, COALESCE(full_name,email) FROM users WHERE id = ANY(:ids)"),
                                  {"ids": ids}).fetchall():
            names[uid] = nm
    for r in rules:
        r["agents"] = [{"id": a, "name": names.get(a, f"#{a}")} for a in r["agent_ids"]]
    return {"rules": rules}


@router.post("/rules")
def create_rule(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Rule needs a name")
    agent_ids = [int(a) for a in (payload.get("agent_ids") or []) if a]
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Pick at least one sales agent to assign to")
    lead_routing.ensure_schema(db)
    import json
    rid = db.execute(text("""
        INSERT INTO lead_assignment_rules (name, priority, is_active, criteria, agent_ids, created_by)
        VALUES (:n, :p, :a, CAST(:c AS JSONB), :ag, :cb) RETURNING id
    """), {"n": name, "p": int(payload.get("priority", 100)),
           "a": bool(payload.get("is_active", True)),
           "c": json.dumps(_clean_criteria(payload.get("criteria"))),
           "ag": agent_ids, "cb": user.id}).scalar()
    db.commit()
    return {"ok": True, "id": rid}


@router.patch("/rules/{rid}")
def update_rule(rid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    lead_routing.ensure_schema(db)
    row = db.execute(text("SELECT id FROM lead_assignment_rules WHERE id=:i"), {"i": rid}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    sets, params = [], {"i": rid}
    if "name" in payload:
        nm = (payload.get("name") or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Rule needs a name")
        sets.append("name=:n"); params["n"] = nm
    if "priority" in payload:
        sets.append("priority=:p"); params["p"] = int(payload["priority"])
    if "is_active" in payload:
        sets.append("is_active=:ac"); params["ac"] = bool(payload["is_active"])
    if "criteria" in payload:
        import json
        sets.append("criteria=CAST(:c AS JSONB)"); params["c"] = json.dumps(_clean_criteria(payload["criteria"]))
    if "agent_ids" in payload:
        agent_ids = [int(a) for a in (payload.get("agent_ids") or []) if a]
        if not agent_ids:
            raise HTTPException(status_code=400, detail="Pick at least one sales agent")
        sets.append("agent_ids=:ag"); params["ag"] = agent_ids
        sets.append("rr_pointer=0")          # reset round-robin when the agent set changes
    if not sets:
        return {"ok": True}
    sets.append("updated_at=NOW()")
    db.execute(text(f"UPDATE lead_assignment_rules SET {', '.join(sets)} WHERE id=:i"), params)
    db.commit()
    return {"ok": True}


@router.delete("/rules/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    db.execute(text("DELETE FROM lead_assignment_rules WHERE id=:i"), {"i": rid})
    db.commit()
    return {"ok": True}


@router.post("/rules/{rid}/preview")
def preview_existing(rid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.execute(text("SELECT criteria FROM lead_assignment_rules WHERE id=:i"), {"i": rid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Rule not found")
    return lead_routing.preview_rule(db, r[0] or {})


@router.post("/preview")
def preview_criteria(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Preview match count for unsaved criteria (rule builder live count)."""
    return lead_routing.preview_rule(db, _clean_criteria(payload.get("criteria")))


# ───────────────────────── config ─────────────────────────
@router.get("/config")
def get_config(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return lead_routing.get_config(db)


@router.post("/config")
def set_config(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return lead_routing.save_config(db, payload)


# ───────────────────────── apply (backfill) ─────────────────────────
@router.post("/apply")
def apply_rules(payload: dict = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    payload = payload or {}
    only_unassigned = payload.get("only_unassigned", True)
    dry_run = bool(payload.get("dry_run", False))
    return lead_routing.apply_all(db, only_unassigned=only_unassigned, dry_run=dry_run)


# ───────────────────────── options for the builder ─────────────────────────
@router.get("/options")
def options(db: Session = Depends(get_db), user=Depends(get_current_user)):
    countries = [r[0] for r in db.execute(text(
        "SELECT DISTINCT country FROM leads WHERE country IS NOT NULL AND country<>'' ORDER BY 1")).fetchall()]
    cities = [r[0] for r in db.execute(text(
        "SELECT DISTINCT city FROM leads WHERE city IS NOT NULL AND city<>'' ORDER BY 1")).fetchall()]
    campaigns = [r[0] for r in db.execute(text(
        "SELECT DISTINCT campaign_name FROM leads WHERE campaign_name IS NOT NULL AND campaign_name<>'' "
        "ORDER BY 1")).fetchall()]
    present_sources = [r[0] for r in db.execute(text(
        "SELECT DISTINCT lower(source) FROM leads WHERE source IS NOT NULL AND source<>''")).fetchall()]
    sources = SOURCE_OPTIONS + [s for s in present_sources if s not in SOURCE_OPTIONS]
    ibs = [{"id": r[0], "name": r[1] or f"IB #{r[0]}"} for r in db.execute(text(
        "SELECT id, name FROM ibs ORDER BY name NULLS LAST LIMIT 2000")).fetchall()]
    agents = [{"id": r[0], "name": r[1] or r[2], "role": r[3]} for r in db.execute(text("""
        SELECT id, full_name, email, role FROM users
        WHERE (role IN ('sales_agent','sales_manager') OR title ILIKE '%team leader%')
          AND COALESCE(is_active, TRUE) = TRUE AND full_name NOT ILIKE '%narmeen%'
        ORDER BY full_name
    """)).fetchall()]
    return {"countries": countries, "cities": cities, "campaigns": campaigns,
            "sources": sources, "ibs": ibs, "agents": agents}
