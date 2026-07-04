"""
leads_router.py — Full leads management
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import rbac
from datetime import datetime, date, timedelta

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("")
def get_leads(
    page:      int   = Query(1, ge=1),
    page_size: int   = Query(20, ge=1, le=100000),
    search:    str   = Query(""),
    status:    str   = Query(""),
    source:    str   = Query(""),
    country:   str   = Query(""),
    city:      str   = Query(""),
    agent:     str   = Query(""),
    ib:        str   = Query(""),
    platform:  str   = Query(""),
    verified:  str   = Query(""),
    kyc:       str   = Query(""),    # 'verified' = KYC-verified leads only (#6)
    sort:      str   = Query("created_at"),
    badge:     str   = Query(""),
    period:    str   = Query("all_time"),
    archived:  str   = Query(""),    # ''/'active' = active only, 'archived' = archived, 'all' = both (#57)
    date_from: str   = Query(""),    # created_at >= (YYYY-MM-DD) (#62)
    date_to:   str   = Query(""),    # created_at <= (YYYY-MM-DD) (#62)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where = ["1=1"]
    params: dict = {}

    # Archive filter (#57) — default view = active (is_archived=false)
    if archived == "archived":
        where.append("COALESCE(l.is_archived, FALSE) = TRUE")
    elif archived == "all":
        pass
    else:
        where.append("COALESCE(l.is_archived, FALSE) = FALSE")

    # Date-range on created_at (#62). Index-friendly: compare the RAW column to date
    # strings (no ::date cast). 'to' stays day-INCLUSIVE via a < (date_to + 1 day) bound.
    if date_from:
        where.append("l.created_at >= :date_from")
        params["date_from"] = date_from[:10]
    if date_to:
        where.append("l.created_at < :date_to_next")
        params["date_to_next"] = (
            datetime.strptime(date_to[:10], "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()

    if search:
        where.append("(l.full_name ILIKE :s OR l.phone ILIKE :s OR l.email ILIKE :s OR l.country ILIKE :s OR l.city ILIKE :s OR l.campaign_name ILIKE :s)")
        params["s"] = f"%{search}%"
    if status:
        where.append("l.status = :status")
        params["status"] = status
    if source:
        where.append("l.source ILIKE :source")
        params["source"] = f"%{source}%"
    if country:
        where.append("l.country = :country")
        params["country"] = country
    if city:
        where.append("l.city ILIKE :city")
        params["city"] = f"%{city}%"
    if badge:
        where.append("l.match_badge = :badge")
        params["badge"] = badge
    if platform:
        where.append("l.platform = :platform")
        params["platform"] = platform
    # Verification filter
    if verified == 'verified':       where.append("l.is_verified=TRUE")
    elif verified == 'phone_only':   where.append("l.phone_verified=TRUE AND l.email_verified=FALSE")
    elif verified == 'email_only':   where.append("l.email_verified=TRUE AND l.phone_verified=FALSE")
    elif verified == 'unverified':   where.append("l.is_verified=FALSE AND l.phone_verified=FALSE")
    elif verified == 'repeated_ip':  where.append("l.ip_count > 1")
    elif verified == 'repeated_cid': where.append("l.cid_count > 0")
    elif verified == 'kyc_id':       where.append("l.kyc_id_uploaded=TRUE")
    elif verified == 'kyc_address':  where.append("l.kyc_address_uploaded=TRUE")
    if kyc == 'verified':            where.append("l.kyc_status = 'verified'")
    if agent:
        au = db.execute(text("SELECT id FROM users WHERE full_name ILIKE :a LIMIT 1"), {"a": f"%{agent}%"}).fetchone()
        if au:
            where.append("l.assigned_agent_id = :aid")
            params["aid"] = au[0]
    if ib:
        # a lead's IB = the IB of the client it matched to (matched_login -> clients.agent -> ibs)
        where.append("""l.matched_login IN (
            SELECT c.login FROM clients c JOIN ibs ibx ON ibx.agent_id = c.agent
            WHERE ibx.name ILIKE :ib)""")
        params["ib"] = f"%{ib}%"

    # Verification filter
    if verified == 'verified':
        where.append("l.is_verified=TRUE")
    elif verified == 'phone_only':
        where.append("l.phone_verified=TRUE AND l.email_verified=FALSE")
    elif verified == 'email_only':
        where.append("l.email_verified=TRUE AND l.phone_verified=FALSE")
    elif verified == 'unverified':
        where.append("l.is_verified=FALSE AND l.phone_verified=FALSE")
    elif verified == 'repeated_ip':
        where.append("l.ip_count > 1")
    elif verified == 'repeated_cid':
        where.append("l.cid_count > 0")

    # Period filter
    if period != 'all_time':
        period_sql = {
            'today':      "l.created_at >= CURRENT_DATE AND l.created_at < CURRENT_DATE + 1",
            'this_week':  "l.created_at >= date_trunc('week', NOW())",
            'last_week':  "l.created_at >= date_trunc('week', NOW()) - interval '1 week' AND l.created_at < date_trunc('week', NOW())",
            'this_month': "l.created_at >= date_trunc('month', NOW())",
            'last_month': "l.created_at >= date_trunc('month', NOW()) - interval '1 month' AND l.created_at < date_trunc('month', NOW())",
            'this_year':  "l.created_at >= date_trunc('year', NOW())",
            'last_year':  "l.created_at >= date_trunc('year', NOW()) - interval '1 year' AND l.created_at < date_trunc('year', NOW())",
        }
        if period in period_sql:
            where.append(period_sql[period])

    # Role-based visibility: agent -> own leads; manager -> own + team; director/admin -> all
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where.append("l.assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where.append("FALSE")

    wc = " AND ".join(where)
    sort_map = {
        'created_at': 'l.created_at DESC',
        'name':       'l.full_name ASC',
        'status':     'l.status ASC',
        'country':    'l.country ASC',
    }
    sort_map['score'] = 'l.score DESC NULLS LAST'
    sort_map['network'] = '(COALESCE(l.ip_count,0)*35 + COALESCE(l.cid_count,0)*50) DESC, l.created_at DESC'
    order = sort_map.get(sort, 'l.created_at DESC')
    # No pinning - pure sort. Recaptures rise on Priority via their +50 score.

    total = db.execute(text(f"SELECT COUNT(*) FROM leads l WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT l.id, l.full_name, l.phone, l.email, l.country, l.city,
               l.language, l.source, l.platform, l.campaign_name, l.ad_set_name, l.ad_name,
               l.status, l.assigned_agent_id, u.full_name as agent_name,
               l.kyc_status, l.notes, l.call_attempts, l.last_call_at,
               l.converted_login, l.converted_at,
               l.utm_source, l.utm_medium, l.utm_campaign,
               l.created_at, l.updated_at,
               l.meta_lead_id, l.google_lead_id, l.meta_stage, l.meta_platform, l.meta_quality,
               l.match_badge, l.matched_login, l.score,
               l.phone_verified, l.email_verified, l.is_verified,
               l.ip_address, l.ip_count, l.cid, l.cid_count,
               l.bonus_eligible, l.bonus_claimed, l.bonus_blocked_reason,
               l.kyc_id_uploaded, l.kyc_id_verified,
               l.kyc_address_uploaded, l.kyc_address_verified, l.kyc_notes,
               ibx.name AS ib_name, l.meta_created, l.last_call_outcome,
               COALESCE(l.is_archived, FALSE) AS is_archived,
               (l.password_hash IS NOT NULL) AS has_password,
               l.date_of_birth, l.customer_no, l.legacy_sales_agent
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_agent_id
        LEFT JOIN clients mc ON mc.login = l.matched_login
        LEFT JOIN ibs ibx ON ibx.agent_id = mc.agent
        WHERE {wc}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    # KPIs
    kpis = db.execute(text(f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status='new') as new_leads,
            COUNT(*) FILTER (WHERE status='contacted') as contacted,
            COUNT(*) FILTER (WHERE status='callback') as callback,
            COUNT(*) FILTER (WHERE status='converted') as converted,
            COUNT(*) FILTER (WHERE status='dead') as dead,
            COUNT(*) FILTER (WHERE source IN ('facebook','Facebook')) as from_facebook,
            COUNT(*) FILTER (WHERE source IN ('instagram','Instagram')) as from_instagram,
            COUNT(*) FILTER (WHERE source IN ('messenger','audience_network')) as from_meta_other,
            COUNT(*) FILTER (WHERE source='Google') as from_google
        FROM leads l WHERE {wc}
    """), params).fetchone()

    return {
        "leads": [{
            "id": r[0], "full_name": r[1] or "", "phone": r[2] or "",
            "email": r[3] or "", "country": r[4] or "", "city": r[5] or "",
            "language": r[6] or "", "source": r[7] or "manual",
            "platform": r[8] or "manual",
            "campaign_name": r[9] or "", "ad_set_name": r[10] or "",
            "ad_name": r[11] or "", "status": r[12] or "new",
            "assigned_agent_id": r[13], "agent_name": r[14] or "",
            "kyc_status": r[15] or "pending", "notes": r[16] or "",
            "call_attempts": r[17] or 0,
            "last_call_at": str(r[18]) if r[18] else "",
            "last_call_outcome": (r[-5] or ""),
            "converted_login": r[19],
            "converted_at": str(r[20]) if r[20] else "",
            "utm_source": r[21] or "", "utm_medium": r[22] or "",
            "utm_campaign": r[23] or "",
            "created_at": str(r[24]) if r[24] else "",
            "updated_at": str(r[25]) if r[25] else "",
            "meta_lead_id": r[26] or "", "google_lead_id": r[27] or "",
            "meta_stage": r[28] or "", "meta_platform": r[29] or "",
            "meta_stage_status": r[30] or "", "meta_quality": r[30] or "",
            "match_badge": r[31] or "", "matched_login": r[32], "score": r[33] or 0,
            "network_score": min(100, (r[38] or 0)*35 + (r[40] or 0)*50),
            "phone_verified": r[34] or False, "email_verified": r[35] or False,
            "is_verified": r[36] or False,
            "ip_address": r[37] or "", "ip_count": r[38] or 0,
            "cid": r[39] or "", "cid_count": r[40] or 0,
            "bonus_eligible": r[41], "bonus_claimed": r[42] or False,
            "bonus_blocked_reason": r[43] or "",
            "kyc_id_uploaded": r[44] or False,
            "kyc_id_verified": r[45] or False,
            "kyc_address_uploaded": r[46] or False,
            "kyc_address_verified": r[47] or False,
            "kyc_notes": r[48] or "",
            "ib_name": r[49] or "",
            "meta_created": str(r[50]) if r[50] else "",
            "is_archived": bool(r[-4]),
            "has_password": bool(r[-3]),
            "date_of_birth": str(r[-3]) if r[-3] else "",
            "customer_no": (r[-2] or ""),
            "legacy_sales_agent": (r[-1] or ""),
        } for r in rows],
        "total": total,
        "kpis": {
            "total": kpis[0], "new": kpis[1], "contacted": kpis[2],
            "callback": kpis[3], "converted": kpis[4], "dead": kpis[5],
            "from_facebook": kpis[6], "from_instagram": kpis[7],
            "from_meta_other": kpis[8], "from_google": kpis[9],
        }
    }


@router.post("")
def create_lead(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    result = db.execute(text("""
        INSERT INTO leads (full_name, phone, email, country, city, language,
                           source, platform, campaign_name, status, assigned_agent_id, notes, created_at, updated_at)
        VALUES (:name, :phone, :email, :country, :city, :lang,
                :source, :platform, :campaign, :status, :agent, :notes, NOW(), NOW())
        RETURNING id
    """), {
        "name": data.get("full_name",""), "phone": data.get("phone",""),
        "email": data.get("email",""), "country": data.get("country",""),
        "city": data.get("city",""), "lang": data.get("language","ar"),
        "source": data.get("source","manual"), "platform": data.get("platform","manual"),
        "campaign": data.get("campaign_name",""), "status": data.get("status","new"),
        "agent": data.get("assigned_agent_id"), "notes": data.get("notes",""),
    })
    db.commit()
    return {"id": result.fetchone()[0], "message": "Lead created"}


@router.patch("/{lead_id}")
def update_lead(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    allowed = ["full_name","phone","email","country","city","status","assigned_agent_id","notes","kyc_status","call_attempts"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return {"message": "Nothing to update"}
    set_clause = ", ".join([f"{k}=:{k}" for k in updates])
    updates["id"] = lead_id
    updates["updated_at"] = datetime.utcnow()
    db.execute(text(f"UPDATE leads SET {set_clause}, updated_at=:updated_at WHERE id=:id"), updates)
    db.commit()
    return {"message": "Updated"}


import re as _re

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.patch("/{lead_id}/contact")
def update_lead_contact(lead_id: int, data: dict, db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    """Edit a lead's contact details — email, phone, date of birth and (optionally) portal password (#90, Nuha).

    Body: {email?, phone?, date_of_birth?, password?}. All optional but at least one required.
    - email validated against a basic pattern (blank allowed to clear).
    - phone normalised to '+'/digits only; must be >=6 digits if provided.
    - date_of_birth: 'YYYY-MM-DD' string -> leads.date_of_birth (blank/"" clears it).
    - password (if a non-empty string) is bcrypt-hashed into leads.password_hash
      (column added additively this session). Min length 6.
    """
    updates: dict = {}

    # Date of birth — accept YYYY-MM-DD (blank clears). Validate the format/range.
    if "date_of_birth" in data:
        dob = (data.get("date_of_birth") or "").strip()
        if dob:
            if not _re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
                return {"error": "Date of birth must be YYYY-MM-DD"}
            try:
                _y, _m, _d = (int(x) for x in dob.split("-"))
                datetime(_y, _m, _d)  # validates real calendar date
                if _y < 1900 or _y > datetime.utcnow().year:
                    return {"error": "Date of birth year is out of range"}
            except ValueError:
                return {"error": "Date of birth is not a valid date"}
            updates["date_of_birth"] = dob
        else:
            updates["date_of_birth"] = None

    # Email — allow clearing with "" ; validate when non-empty
    if "email" in data:
        email = (data.get("email") or "").strip()
        if email and not _EMAIL_RE.match(email):
            return {"error": "Invalid email address"}
        updates["email"] = email or None

    # Phone — keep leading + and digits only
    if "phone" in data:
        raw = (data.get("phone") or "").strip()
        if raw:
            cleaned = _re.sub(r"[^\d+]", "", raw)
            digits = _re.sub(r"\D", "", cleaned)
            if len(digits) < 6:
                return {"error": "Phone number looks too short"}
            updates["phone"] = cleaned
        else:
            updates["phone"] = None

    # Password — bcrypt-hash into leads.password_hash (only if a value is supplied)
    if data.get("password"):
        pw = str(data.get("password"))
        if len(pw) < 6:
            return {"error": "Password must be at least 6 characters"}
        from auth import get_password_hash
        updates["password_hash"] = get_password_hash(pw)

    if not updates:
        return {"message": "Nothing to update"}

    set_clause = ", ".join([f"{k}=:{k}" for k in updates])
    updates["id"] = lead_id
    db.execute(text(f"UPDATE leads SET {set_clause}, updated_at=NOW() WHERE id=:id"), updates)
    db.commit()
    changed = [k for k in updates if k != "id"]
    return {"message": "Contact updated", "updated": changed,
            "has_password": "password_hash" in changed}


@router.post("/{lead_id}/call")
def log_call(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    note = data.get("note","Called")
    # Format comment with agent name, timestamp, action
    from datetime import datetime
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    formatted_note = f"[{timestamp}] {current_user.full_name}: {note}"
    
    db.execute(text("""
        UPDATE leads SET
            call_attempts = call_attempts + 1,
            last_call_at = NOW(),
            last_call_by = :uid,
            notes = CASE 
                WHEN notes IS NULL OR notes = '' THEN :note
                ELSE notes || E'\n' || :note
            END,
            updated_at = NOW()
        WHERE id = :id
    """), {"uid": current_user.id, "note": formatted_note, "id": lead_id})
    db.commit()
    # the desk working an archived lead = re-engagement -> bring it back to the active list
    try:
        import reactivation
        reactivation.reactivate_lead(db, lead_id, via="action")
    except Exception:
        db.rollback()
    return {"message": "Call logged", "note": formatted_note}


@router.post("/{lead_id}/convert")
def convert_lead(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    login = data.get("login")
    db.execute(text("""
        UPDATE leads SET status='converted', converted_login=:login,
        converted_at=NOW(), updated_at=NOW() WHERE id=:id
    """), {"login": login, "id": lead_id})
    db.commit()
    return {"message": "Lead converted"}


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("DELETE FROM leads WHERE id=:id"), {"id": lead_id})
    db.commit()
    return {"message": "Deleted"}


@router.post("/archive")
def archive_leads(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Bulk archive / unarchive leads (#57). Body: {ids:[...], archived:bool}."""
    ids = data.get("ids") or []
    archived = bool(data.get("archived", True))
    if not ids:
        return {"message": "Nothing to update", "count": 0}
    db.execute(text("UPDATE leads SET is_archived=:a, updated_at=NOW() WHERE id = ANY(:ids)"),
               {"a": archived, "ids": ids})
    db.commit()
    return {"message": "archived" if archived else "unarchived", "archived": archived, "count": len(ids)}


@router.post("/{lead_id}/archive")
def archive_lead(lead_id: int, data: dict | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Archive / unarchive a single lead (#57). Body: {archived:bool} (defaults True)."""
    archived = True if data is None else bool(data.get("archived", True))
    db.execute(text("UPDATE leads SET is_archived=:a, updated_at=NOW() WHERE id=:id"),
               {"a": archived, "id": lead_id})
    db.commit()
    return {"message": "archived" if archived else "unarchived", "archived": archived}


@router.post("/{lead_id}/unarchive")
def unarchive_lead(lead_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Convenience inverse of /{lead_id}/archive (#57) — moves a lead back to the active list."""
    return archive_lead(lead_id, {"archived": False}, db, current_user)


# Lead statuses that count as "not interested" for the bulk-archive convenience (#63).
# The Leads UI maps the 'Not Interested' call outcome to status='dead'.
_NOT_INTERESTED_STATUSES = ("dead", "not_interested", "lost")


@router.post("/archive-not-interested")
def archive_not_interested(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """#63 — bulk-archive every still-active lead marked 'not interested' (status dead/
    not_interested/lost) so the main Leads list stays clean. Respects role visibility:
    agents/managers only archive leads in their own scope. Returns how many moved."""
    where = ["COALESCE(is_archived, FALSE) = FALSE", "status = ANY(:st)"]
    params: dict = {"st": list(_NOT_INTERESTED_STATUSES)}
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where.append("assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where.append("FALSE")
    wc = " AND ".join(where)
    res = db.execute(text(
        f"UPDATE leads SET is_archived=TRUE, updated_at=NOW() WHERE {wc}"), params)
    db.commit()
    return {"message": "archived not-interested leads", "count": res.rowcount or 0}


# Meta webhook
@router.get("/webhook/meta")
def meta_webhook_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
):
    if hub_verify_token == "tnfx_leads_2025" and hub_mode == "subscribe":
        return int(hub_challenge)
    return {"error": "Invalid token"}


@router.post("/webhook/meta")
def meta_webhook_receive(data: dict, db: Session = Depends(get_db)):
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "leadgen":
                    value = change.get("value", {})
                    lead_id = value.get("leadgen_id")
                    form_id = value.get("form_id")
                    # Store raw lead - full data fetched separately
                    db.execute(text("""
                        INSERT INTO leads (meta_lead_id, form_id, source, platform, status, created_at, updated_at)
                        VALUES (:lid, :fid, 'Facebook', 'meta', 'new', NOW(), NOW())
                        ON CONFLICT DO NOTHING
                    """), {"lid": str(lead_id), "fid": str(form_id)})
        db.commit()
    except Exception as e:
        print(f"Meta webhook error: {e}")
    return {"status": "ok"}


# ── Verification endpoints ─────────────────────────────────────────────────

@router.post("/{lead_id}/verify")
def verify_lead(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Mark phone/email as verified."""
    updates = {}
    if "phone_verified" in data: updates["phone_verified"] = data["phone_verified"]
    if "email_verified" in data: updates["email_verified"] = data["email_verified"]
    if "is_verified"    in data: updates["is_verified"]    = data["is_verified"]
    if "verification_notes" in data: updates["verification_notes"] = data["verification_notes"]
    
    if updates:
        # Auto-set is_verified if both phone and email verified
        set_clause = ", ".join([f"{k}=:{k}" for k in updates])
        updates["id"] = lead_id
        db.execute(text(f"UPDATE leads SET {set_clause}, updated_at=NOW() WHERE id=:id"), updates)
        db.commit()
    return {"message": "Verification updated"}


@router.post("/{lead_id}/check-ip")
def check_ip(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Check IP address - how many leads/clients use same IP."""
    ip = data.get("ip_address","")
    if not ip:
        return {"error": "No IP provided"}
    
    # Count leads with same IP
    lead_count = db.execute(text(
        "SELECT COUNT(*) FROM leads WHERE ip_address=:ip AND id!=:id"
    ), {"ip": ip, "id": lead_id}).scalar() or 0
    
    # Count clients with same IP
    client_count = db.execute(text(
        "SELECT COUNT(*) FROM account_identifiers WHERE identifier_type='ip' AND identifier_value=:ip"
    ), {"ip": ip}).scalar() or 0
    
    total = lead_count + client_count
    
    # Update lead
    db.execute(text("""
        UPDATE leads SET ip_address=:ip, ip_count=:count, updated_at=NOW()
        WHERE id=:id
    """), {"ip": ip, "count": total, "id": lead_id})
    db.commit()
    
    return {
        "ip": ip,
        "lead_count": lead_count,
        "client_count": client_count,
        "total": total,
        "risk": "high" if total > 3 else "medium" if total > 1 else "new"
    }


@router.post("/{lead_id}/check-cid")
def check_cid(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Check CID - how many accounts use same device."""
    cid = data.get("cid","")
    if not cid:
        return {"error": "No CID provided"}
    
    # Count accounts with same CID
    cid_count = db.execute(text("""
        SELECT COUNT(DISTINCT login) FROM account_identifiers
        WHERE identifier_type='cid' AND identifier_value=:cid
    """), {"cid": cid}).scalar() or 0
    
    # Count leads with same CID
    lead_cid_count = db.execute(text(
        "SELECT COUNT(*) FROM leads WHERE cid=:cid AND id!=:id"
    ), {"cid": cid, "id": lead_id}).scalar() or 0
    
    total = cid_count + lead_cid_count
    
    db.execute(text("""
        UPDATE leads SET cid=:cid, cid_count=:count, updated_at=NOW()
        WHERE id=:id
    """), {"cid": cid, "count": total, "id": lead_id})
    db.commit()
    
    return {
        "cid": cid,
        "existing_accounts": cid_count,
        "other_leads": lead_cid_count,
        "total": total,
        "risk": "high" if total > 0 else "new"
    }


# ── Client Dashboard endpoints ─────────────────────────────────────────────

from fastapi import APIRouter as _AR
client_router = _AR(prefix="/client-dashboard", tags=["Client Dashboard"])


@client_router.get("/kpis/{login}")
def get_client_kpis(login: int, db: Session = Depends(get_db)):
    """Client-facing KPIs for their own dashboard."""
    client = db.execute(text("""
        SELECT login, name, balance, equity, total_deposits, total_withdrawals,
               credit, margin_level, group_name, reg_date
        FROM clients WHERE login=:l
    """), {"l": login}).fetchone()
    
    if not client:
        return {"error": "Not found"}
    
    # Open positions count
    open_pos = db.execute(text("""
        SELECT COUNT(*) FROM deals 
        WHERE login=:l AND deal_type='trade' AND entry=0
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
    """), {"l": login}).scalar() or 0
    
    # Recent trades
    recent_trades = db.execute(text("""
        SELECT COUNT(*), COALESCE(SUM(profit),0)
        FROM deals WHERE login=:l AND deal_type='trade' AND entry=1
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
    """), {"l": login}).fetchone()
    
    return {
        "login": login,
        "name": client[1],
        "balance": float(client[2] or 0),
        "equity": float(client[3] or client[2] or 0),
        "total_deposits": float(client[4] or 0),
        "total_withdrawals": float(client[5] or 0),
        "credit": float(client[6] or 0),
        "margin_level": float(client[7] or 0),
        "group": client[8] or "",
        "open_positions": open_pos,
        "monthly_trades": recent_trades[0] or 0,
        "monthly_pnl": float(recent_trades[1] or 0),
        "reg_date": str(client[9] or ""),
    }


@client_router.post("/bonus-check/{login}")
def check_welcome_bonus(login: int, data: dict, db: Session = Depends(get_db)):
    """Check if client is eligible for welcome bonus."""
    cid = data.get("cid","")
    ip  = data.get("ip","")
    
    # Get bonus rule
    rule = db.execute(text(
        "SELECT bonus_amount, max_per_cid, max_per_ip FROM welcome_bonus_rules WHERE active=TRUE LIMIT 1"
    )).fetchone()
    if not rule:
        return {"eligible": False, "reason": "No bonus program active"}
    
    bonus_amount, max_per_cid, max_per_ip = rule
    
    # Check if already claimed
    already = db.execute(text(
        "SELECT COUNT(*) FROM transactions WHERE login=:l AND tx_type='bonus_deposit'"
    ), {"l": login}).scalar() or 0
    if already > 0:
        return {"eligible": False, "reason": "Welcome bonus already claimed", "bonus_amount": 0}
    
    # Check CID uniqueness
    if cid:
        cid_count = db.execute(text("""
            SELECT COUNT(DISTINCT login) FROM account_identifiers
            WHERE identifier_type='cid' AND identifier_value=:cid AND login!=:l
        """), {"cid": cid, "l": login}).scalar() or 0
        if cid_count >= max_per_cid:
            return {
                "eligible": False,
                "reason": "This device has already been used to claim a welcome bonus. You can enjoy our deposit bonus instead!",
                "bonus_amount": 0,
                "show_deposit_bonus": True
            }
    
    # Check IP
    if ip:
        ip_count = db.execute(text("""
            SELECT COUNT(DISTINCT login) FROM account_identifiers
            WHERE identifier_type='ip' AND identifier_value=:ip AND login!=:l
        """), {"ip": ip, "l": login}).scalar() or 0
        if ip_count >= max_per_ip:
            return {
                "eligible": False,
                "reason": "Too many accounts from your network have claimed this bonus. You can enjoy our deposit bonus!",
                "bonus_amount": 0,
                "show_deposit_bonus": True
            }
    
    # Eligible!
    return {
        "eligible": True,
        "bonus_amount": bonus_amount,
        "reason": "You are eligible for the welcome bonus!",
        "next_step": "Login to your trading account to activate your bonus",
        "show_deposit_bonus": False
    }

@router.get("/verified")
def get_verified_accounts(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100000),
    search:    str = Query(""),
    country:   str = Query(""),
    sort:      str = Query("date"),  # date | name | country | login
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Verified Accounts — KYC-approved accounts that have a trading-account number (#95, Nuha).

    Replaces the old "Approved & funded" tab. Lists trading accounts (clients) that are
    BOTH:
      (1) APPROVED / KYC-verified  ->  clients.kyc_status = 'verified'
      (2) ASSIGNED A TRADING ACCOUNT NUMBER (a login)  ->  clients.login IS NOT NULL
    REGARDLESS of whether they deposited (accounts that deposit move to the Clients list
    automatically, so a deposit filter is intentionally NOT applied). Joins back to a
    matched lead (leads.matched_login / converted_login) when one exists so the desk can
    see which lead the account came from.
    """
    where = ["c.kyc_status = 'verified'", "c.login IS NOT NULL"]
    params: dict = {}

    if search:
        where.append("(c.name ILIKE :s OR CAST(c.login AS TEXT) ILIKE :s OR c.email ILIKE :s OR c.phone ILIKE :s)")
        params["s"] = f"%{search}%"
    if country:
        where.append("c.country = :country")
        params["country"] = country

    wc = " AND ".join(where)
    sort_map = {
        "date":    "c.reg_date DESC NULLS LAST",
        "name":    "c.name ASC",
        "country": "c.country ASC, c.reg_date DESC",
        "login":   "c.login ASC",
    }
    order = sort_map.get(sort, "c.reg_date DESC NULLS LAST")

    total = db.execute(text(f"SELECT COUNT(*) FROM clients c WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT c.login, c.name, c.country, c.platform, c.kyc_status, c.reg_date,
               l.id AS lead_id, l.full_name AS lead_name, l.match_badge, l.source,
               EXISTS (SELECT 1 FROM transactions t WHERE t.login = c.login AND t.tx_type='deposit') AS has_deposit
        FROM clients c
        LEFT JOIN leads l ON l.matched_login = c.login OR l.converted_login = c.login
        WHERE {wc}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    return {
        "accounts": [{
            "login": r[0], "name": r[1] or "", "country": r[2] or "",
            "platform": r[3] or "MT5", "kyc_status": r[4] or "",
            "reg_date": str(r[5]) if r[5] else "",
            "lead_id": r[6], "lead_name": r[7] or "",
            "match_badge": r[8] or "", "source": r[9] or "",
            "has_deposit": bool(r[10]),
        } for r in rows],
        "total": total,
        "kpis": {
            "accounts": total,
        },
    }


@router.get("/funded")
def get_funded_accounts(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100000),
    search:    str = Query(""),
    country:   str = Query(""),
    approved_only: str = Query("1"),   # '1' = require KYC-approved; '' = any deposited account
    sort:      str = Query("deposits"),  # deposits | name | country | date
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Approved & funded accounts — converted leads / funded clients (#95, Nuha).

    Lists trading accounts (clients) that have ACTUALLY DEPOSITED (a real deposit
    transaction in `transactions`, the deposit truth used across the CRM) and,
    when approved_only=1, are also KYC-APPROVED (clients.kyc_status='verified').
    Joins back to a matched lead (leads.matched_login / converted_login) when one
    exists so the desk can see which lead converted, but the row is the funded
    account itself. Aggregates the deposit total + first-deposit date per login.
    """
    where = ["EXISTS (SELECT 1 FROM transactions t WHERE t.login = c.login AND t.tx_type='deposit')"]
    params: dict = {}

    if approved_only == "1":
        where.append("c.kyc_status = 'verified'")
    if search:
        where.append("(c.name ILIKE :s OR CAST(c.login AS TEXT) ILIKE :s OR c.email ILIKE :s OR c.phone ILIKE :s)")
        params["s"] = f"%{search}%"
    if country:
        where.append("c.country = :country")
        params["country"] = country

    wc = " AND ".join(where)
    sort_map = {
        "deposits": "total_deposits DESC NULLS LAST",
        "name":     "c.name ASC",
        "country":  "c.country ASC, total_deposits DESC",
        "date":     "first_deposit DESC NULLS LAST",
    }
    order = sort_map.get(sort, "total_deposits DESC NULLS LAST")

    total = db.execute(text(f"SELECT COUNT(*) FROM clients c WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT c.login, c.name, c.country, c.platform, c.kyc_status, c.reg_date,
               dep.total_deposits, dep.first_deposit, dep.deposit_count,
               l.id AS lead_id, l.full_name AS lead_name, l.match_badge, l.source
        FROM clients c
        JOIN LATERAL (
            SELECT COALESCE(SUM(t.amount),0) AS total_deposits,
                   MIN(t.tx_date)           AS first_deposit,
                   COUNT(*)                 AS deposit_count
            FROM transactions t
            WHERE t.login = c.login AND t.tx_type='deposit'
        ) dep ON TRUE
        LEFT JOIN leads l ON l.matched_login = c.login OR l.converted_login = c.login
        WHERE {wc}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    kpi = db.execute(text(f"""
        SELECT COUNT(*) AS accts,
               COALESCE(SUM(dep.total_deposits),0) AS total_dep
        FROM clients c
        JOIN LATERAL (
            SELECT COALESCE(SUM(t.amount),0) AS total_deposits
            FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit'
        ) dep ON TRUE
        WHERE {wc}
    """), params).fetchone()

    return {
        "accounts": [{
            "login": r[0], "name": r[1] or "", "country": r[2] or "",
            "platform": r[3] or "MT5", "kyc_status": r[4] or "",
            "reg_date": str(r[5]) if r[5] else "",
            "total_deposits": float(r[6] or 0),
            "first_deposit": str(r[7]) if r[7] else "",
            "deposit_count": r[8] or 0,
            "lead_id": r[9], "lead_name": r[10] or "",
            "match_badge": r[11] or "", "source": r[12] or "",
        } for r in rows],
        "total": total,
        "kpis": {
            "accounts": kpi[0] or 0,
            "total_deposits": float(kpi[1] or 0),
        },
    }


@router.get("/logins-only")
def get_lead_logins(
    search: str = Query(""),
    sort:   str = Query("created_at"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fast endpoint — returns only lead IDs with phone for power dialer."""
    where_parts = ["l.phone IS NOT NULL", "l.phone != ''"]
    params: dict = {}
    if search:
        where_parts.append("(l.full_name ILIKE :s OR l.phone ILIKE :s OR l.email ILIKE :s)")
        params["s"] = f"%{search}%"
    # Role-based visibility: agent dials only their own leads; manager their team; admin all
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where_parts.append("l.assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where_parts.append("FALSE")
    sort_col = {"created_at":"l.created_at DESC","name":"l.full_name ASC",
                "status":"l.status ASC"}.get(sort, "l.created_at DESC")
    where = " AND ".join(where_parts)
    rows = db.execute(text(f"SELECT l.id FROM leads l WHERE {where} ORDER BY {sort_col}"), params).fetchall()
    return {"logins": [r[0] for r in rows], "total": len(rows)}

