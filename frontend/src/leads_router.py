"""
leads_router.py — Full leads management
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
from datetime import datetime

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("")
def get_leads(
    page:      int   = Query(1, ge=1),
    page_size: int   = Query(20, ge=1, le=500),
    search:    str   = Query(""),
    status:    str   = Query(""),
    source:    str   = Query(""),
    country:   str   = Query(""),
    city:      str   = Query(""),
    agent:     str   = Query(""),
    platform:  str   = Query(""),
    verified:  str   = Query(""),
    sort:      str   = Query("created_at"),
    period:    str   = Query("all_time"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where = ["1=1"]
    params: dict = {}

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
    if agent:
        au = db.execute(text("SELECT id FROM users WHERE full_name ILIKE :a LIMIT 1"), {"a": f"%{agent}%"}).fetchone()
        if au:
            where.append("l.assigned_agent_id = :aid")
            params["aid"] = au[0]

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
            'today':      "l.created_at::date = CURRENT_DATE",
            'this_week':  "l.created_at >= date_trunc('week', NOW())",
            'last_week':  "l.created_at >= date_trunc('week', NOW()) - interval '1 week' AND l.created_at < date_trunc('week', NOW())",
            'this_month': "l.created_at >= date_trunc('month', NOW())",
            'last_month': "l.created_at >= date_trunc('month', NOW()) - interval '1 month' AND l.created_at < date_trunc('month', NOW())",
            'this_year':  "l.created_at >= date_trunc('year', NOW())",
            'last_year':  "l.created_at >= date_trunc('year', NOW()) - interval '1 year' AND l.created_at < date_trunc('year', NOW())",
        }
        if period in period_sql:
            where.append(period_sql[period])

    wc = " AND ".join(where)
    sort_map = {
        'created_at': 'l.created_at DESC',
        'name':       'l.full_name ASC',
        'status':     'l.status ASC',
        'country':    'l.country ASC',
    }
    order = sort_map.get(sort, 'l.created_at DESC')

    total = db.execute(text(f"SELECT COUNT(*) FROM leads l WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT l.id, l.full_name, l.phone, l.email, l.country, l.city,
               l.language, l.source, l.platform, l.campaign_name, l.ad_set_name, l.ad_name,
               l.status, l.assigned_agent_id, u.full_name as agent_name,
               l.kyc_status, l.notes, l.call_attempts, l.last_call_at,
               l.converted_login, l.converted_at,
               l.utm_source, l.utm_medium, l.utm_campaign,
               l.created_at, l.updated_at,
               l.meta_lead_id, l.google_lead_id,
               l.phone_verified, l.email_verified, l.is_verified,
               l.ip_address, l.ip_count, l.cid, l.cid_count,
               l.bonus_eligible, l.bonus_claimed, l.bonus_blocked_reason,
               l.kyc_id_uploaded, l.kyc_id_verified,
               l.kyc_address_uploaded, l.kyc_address_verified, l.kyc_notes
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_agent_id
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
            COUNT(*) FILTER (WHERE source='Facebook') as from_facebook,
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
            "converted_login": r[19],
            "converted_at": str(r[20]) if r[20] else "",
            "utm_source": r[21] or "", "utm_medium": r[22] or "",
            "utm_campaign": r[23] or "",
            "created_at": str(r[24]) if r[24] else "",
            "updated_at": str(r[25]) if r[25] else "",
            "meta_lead_id": r[26] or "", "google_lead_id": r[27] or "",
            "phone_verified": r[28] or False, "email_verified": r[29] or False,
            "is_verified": r[30] or False,
            "ip_address": r[31] or "", "ip_count": r[32] or 0,
            "cid": r[33] or "", "cid_count": r[34] or 0,
            "bonus_eligible": r[35], "bonus_claimed": r[36] or False,
            "bonus_blocked_reason": r[37] or "",
            "kyc_id_uploaded": r[38] or False,
            "kyc_id_verified": r[39] or False,
            "kyc_address_uploaded": r[40] or False,
            "kyc_address_verified": r[41] or False,
            "kyc_notes": r[42] or "",
        } for r in rows],
        "total": total,
        "kpis": {
            "total": kpis[0], "new": kpis[1], "contacted": kpis[2],
            "callback": kpis[3], "converted": kpis[4], "dead": kpis[5],
            "from_facebook": kpis[6], "from_google": kpis[7],
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
