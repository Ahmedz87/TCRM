"""
score_rules_router.py — CRUD for the admin scoring rules + recompute. Mounted in main.py.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import score_engine as SE

router = APIRouter(prefix="/score-rules", tags=["score-rules"])


def _ensure(db):
    SE.ensure_schema(db)


FIELD_LABELS = {
    "country": "Country", "city": "City", "source": "Source", "campaign": "Campaign",
    "status": "Status", "language": "Language", "match_badge": "Match badge",
    "meta_quality": "Meta quality", "verified": "Verified (KYC)", "has_phone": "Has phone",
    "no_phone": "No phone", "platform": "Platform", "sales_agent": "Sales agent",
    "deposit_method": "Payment method", "depositor": "Has deposited",
    "no_deposit_ever": "Never deposited", "no_deposit_days": "No deposit for (days)",
    "has_ib": "Has IB", "archived": "Archived",
}


def _col_vals(db, sql):
    try:
        return [r[0] for r in db.execute(text(sql)).fetchall() if r[0]]
    except Exception:
        db.rollback(); return []


@router.get("/options")
def options(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Per-field metadata (label, type, option list) for BOTH scopes so the UI can render a generic
    multi-select. type: 'multi' (pick many), 'int' (a number), 'none' (boolean condition, no value)."""
    sources    = _col_vals(db, "SELECT DISTINCT source FROM leads WHERE source<>'' ORDER BY 1")
    countries  = _col_vals(db, "SELECT country FROM clients WHERE COALESCE(country,'')<>'' GROUP BY country ORDER BY COUNT(*) DESC LIMIT 300")
    cities     = _col_vals(db, "SELECT city FROM clients WHERE COALESCE(city,'')<>'' GROUP BY city ORDER BY COUNT(*) DESC LIMIT 250")
    methods    = _col_vals(db, "SELECT method FROM transactions WHERE tx_type='deposit' AND method ~ '^[A-Za-z]' GROUP BY method HAVING COUNT(*) > 50 ORDER BY COUNT(*) DESC LIMIT 40")
    campaigns  = _col_vals(db, "SELECT campaign_name FROM leads WHERE COALESCE(campaign_name,'')<>'' GROUP BY campaign_name ORDER BY COUNT(*) DESC LIMIT 120")
    languages  = _col_vals(db, "SELECT DISTINCT language FROM leads WHERE COALESCE(language,'')<>'' ORDER BY 1")
    metaquals  = _col_vals(db, "SELECT DISTINCT meta_quality FROM leads WHERE COALESCE(meta_quality,'')<>'' ORDER BY 1")
    agents     = _col_vals(db, "SELECT full_name FROM users WHERE COALESCE(full_name,'')<>'' AND role IN ('sales_agent','sales_manager','retention','director','team_leader','customer_care') ORDER BY 1")
    OPTS = {
        "country": countries, "city": cities, "source": sources, "campaign": campaigns,
        "status": ["new", "contacted", "callback", "converted", "dead"],
        "language": languages or ["ar", "en"],
        "match_badge": ["recapture", "registered_no_deposit", "converted", "reactivated", "recapture_archive"],
        "meta_quality": metaquals or ["high", "medium", "low"],
        "platform": ["MT4", "MT5"], "sales_agent": agents, "deposit_method": methods,
    }

    def meta_for(scope):
        out = {}
        for f, (pred, needs, multi) in SE.FIELDS[scope].items():
            t = "none" if not needs else ("multi" if multi else "int")
            out[f] = {"label": FIELD_LABELS.get(f, f), "type": t,
                      "options": OPTS.get(f, []) if t == "multi" else []}
        return out

    return {
        "fields": {s: list(SE.FIELDS[s].keys()) for s in SE.FIELDS},
        "field_meta": {"lead": meta_for("lead"), "client": meta_for("client")},
        # legacy keys (kept so older UI builds don't break)
        "needs_value": {f: meta[1] for scope in SE.FIELDS for f, meta in SE.FIELDS[scope].items()},
        "sources": sources, "countries": countries, "methods": methods,
        "match_badges": OPTS["match_badge"],
    }


@router.get("")
def list_rules(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    rows = db.execute(text("""
        SELECT id, scope, field, value, points, active, label, expires_at, created_at
        FROM score_rules ORDER BY scope, id
    """)).fetchall()
    return {"rules": [{
        "id": r[0], "scope": r[1], "field": r[2], "value": r[3] or "", "points": r[4],
        "active": bool(r[5]), "label": r[6] or "", "expires_at": str(r[7]) if r[7] else "",
        "created_at": str(r[8])[:10] if r[8] else "",
    } for r in rows]}


@router.post("")
def create_rule(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    scope = payload.get("scope")
    field = payload.get("field")
    if scope not in SE.FIELDS or field not in SE.FIELDS[scope]:
        raise HTTPException(400, "Invalid scope/field.")
    needs_value = SE.FIELDS[scope][field][1]
    value = (payload.get("value") or "").strip()
    if needs_value and not value:
        raise HTTPException(400, "This rule needs a value.")
    rid = db.execute(text("""
        INSERT INTO score_rules (scope, field, value, points, active, label, expires_at)
        VALUES (:s,:f,:v,:p,:a,:l, NULLIF(:e,'')::date) RETURNING id
    """), {"s": scope, "f": field, "v": value, "p": int(payload.get("points") or 0),
           "a": bool(payload.get("active", True)), "l": payload.get("label") or "",
           "e": payload.get("expires_at") or ""}).scalar()
    db.commit()
    return {"ok": True, "id": rid}


@router.patch("/{rid}")
def update_rule(rid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    sets, params = [], {"id": rid}
    for k in ("points", "active", "label", "value"):
        if k in payload:
            sets.append(f"{k} = :{k}")
            params[k] = int(payload[k]) if k == "points" else (bool(payload[k]) if k == "active" else payload[k])
    if "expires_at" in payload:
        sets.append("expires_at = NULLIF(:e,'')::date"); params["e"] = payload["expires_at"] or ""
    if not sets:
        return {"ok": True}
    db.execute(text(f"UPDATE score_rules SET {', '.join(sets)} WHERE id=:id"), params)
    db.commit()
    return {"ok": True}


@router.delete("/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    db.execute(text("DELETE FROM score_rules WHERE id=:id"), {"id": rid})
    db.commit()
    return {"ok": True}


@router.post("/apply")
def apply_now(bg: BackgroundTasks, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Recompute lead + client scores from base + active rules. Runs in the BACKGROUND (it rewrites
    ~343k rows and can wait on the live auto_match writer), so the request returns immediately."""
    _ensure(db)
    from database import SessionLocal

    def _run():
        s = SessionLocal()
        try:
            SE.apply_rules(s)
        except Exception as e:
            print(f"[score apply] failed: {e}", flush=True)
        finally:
            s.close()
    bg.add_task(_run)
    return {"ok": True, "message": "Scores are recalculating in the background — refresh in a moment."}
