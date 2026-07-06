"""
Meta Conversions API for CRM — sends lead stage updates back to Meta
so Meta can optimize audience quality.

Sales picks a status → this fires the event to Meta.
Status mapping (Meta standard CRM lead stages):
  qualified      → "qualified"
  converted      → "converted"
  not_qualified  → "disqualified"
  lost           → "lost"

NOTE: Requires DATASET_ID + the events configured in Meta Events Manager.
Until then, SEND_TO_META=False just records the stage locally.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import urllib.request, json, ssl, hashlib, time

import models
from database import get_db
from auth import get_current_user
import meta_config

router = APIRouter(prefix="/meta", tags=["meta"])

# ── CONFIG ───────────────────────────────────────────────────────────────────
ACCESS_TOKEN = meta_config.META_ACCESS_TOKEN
DATASET_ID   = meta_config.META_DATASET_ID          # <-- fill in from Meta Events Manager when ready
SEND_TO_META = True       # <-- set True after DATASET_ID is configured
GRAPH        = "https://graph.facebook.com/v21.0"

ctx = ssl.create_default_context()   # verify TLS: graph.facebook.com has a valid public cert

# Map CRM status → Meta standard lead stage event name
STAGE_MAP = {
    "qualified":     "qualified",
    "converted":     "converted",
    "not_qualified": "disqualified",
    "lost":          "lost",
}

def sha256(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()

def send_to_meta(meta_lead_id: str, event_name: str, lead: dict) -> dict:
    """Send a CRM lead-stage event to Meta Conversions API."""
    if not SEND_TO_META or not DATASET_ID:
        return {"sent": False, "reason": "Meta CAPI not configured (DATASET_ID empty or SEND_TO_META False)"}

    url = f"{GRAPH}/{DATASET_ID}/events?access_token={ACCESS_TOKEN}"
    payload = {
        "data": [{
            "event_name": event_name,
            "event_time": int(time.time()),
            "action_source": "system_generated",
            "lead_event_source": "Broker CRM",
            "user_data": {
                "lead_id": int(meta_lead_id) if str(meta_lead_id).isdigit() else meta_lead_id,
                # hashed PII (optional but improves match)
                "em": [sha256(lead.get("email", ""))] if lead.get("email") else [],
                "ph": [sha256(lead.get("phone", ""))] if lead.get("phone") else [],
            },
        }]
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla"},
        method="POST")
    try:
        r = urllib.request.urlopen(req, context=ctx, timeout=15)
        return {"sent": True, "response": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {"sent": False, "error": e.read().decode()[:300]}
    except Exception as e:
        return {"sent": False, "error": str(e)}

def send_purchase(meta_lead_id, value, currency, email, phone) -> dict:
    """Send a DEPOSIT as a value-based 'Purchase' conversion so Meta optimizes for DEPOSITORS,
    not just form-fillers. Ties to the original ad-click via lead_id + hashed PII."""
    if not SEND_TO_META or not DATASET_ID:
        return {"sent": False, "reason": "Meta CAPI not configured"}
    url = f"{GRAPH}/{DATASET_ID}/events?access_token={ACCESS_TOKEN}"
    payload = {"data": [{
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "action_source": "system_generated",
        "lead_event_source": "Broker CRM",
        "user_data": {
            "lead_id": int(meta_lead_id) if str(meta_lead_id).isdigit() else meta_lead_id,
            "em": [sha256(email)] if email else [],
            "ph": [sha256(phone)] if phone else [],
        },
        "custom_data": {"value": round(float(value or 0), 2), "currency": currency or "USD"},
    }]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla"}, method="POST")
    try:
        r = urllib.request.urlopen(req, context=ctx, timeout=15)
        return {"sent": True, "response": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {"sent": False, "error": e.read().decode()[:300]}
    except Exception as e:
        return {"sent": False, "error": str(e)}


def _ensure_dep_cols(db):
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_deposit_sent_at TIMESTAMP"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_deposit_value DOUBLE PRECISION"))
    db.commit()


@router.get("/deposits/stats")
def deposit_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """How many Meta leads have deposited (eligible to send as value conversions) vs already sent."""
    _ensure_dep_cols(db)
    r = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE elig) AS eligible,
          COALESCE(SUM(amt) FILTER (WHERE elig),0) AS eligible_value,
          COUNT(*) FILTER (WHERE elig AND sent_at IS NOT NULL) AS already_sent
        FROM (
          SELECT l.id, l.meta_deposit_sent_at AS sent_at,
                 (l.meta_lead_id IS NOT NULL AND l.matched_login IS NOT NULL AND dep.amt > 0) AS elig,
                 dep.amt
          FROM leads l
          LEFT JOIN LATERAL (SELECT COALESCE(SUM(t.amount),0) amt FROM transactions t
                             WHERE t.login=l.matched_login AND t.tx_type='deposit') dep ON TRUE
        ) q
    """)).fetchone()
    return {"configured": bool(SEND_TO_META and DATASET_ID), "dataset_id": DATASET_ID,
            "eligible": int(r[0] or 0), "eligible_value": round(float(r[1] or 0), 2),
            "already_sent": int(r[2] or 0)}


@router.post("/deposits/sync")
def deposit_sync(data: dict = None, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """Send deposit value-conversions to Meta for all matched Meta leads that have deposited.
    Idempotent: skips leads already sent unless resend=true. limit caps a single run."""
    _ensure_dep_cols(db)
    data = data or {}
    resend = bool(data.get("resend"))
    limit = int(data.get("limit", 500))
    rows = db.execute(text(f"""
        SELECT l.id, l.meta_lead_id, l.email, l.phone, dep.amt
        FROM leads l
        JOIN LATERAL (SELECT COALESCE(SUM(t.amount),0) amt FROM transactions t
                      WHERE t.login=l.matched_login AND t.tx_type='deposit') dep ON TRUE
        WHERE l.meta_lead_id IS NOT NULL AND l.matched_login IS NOT NULL AND dep.amt > 0
          {"" if resend else "AND l.meta_deposit_sent_at IS NULL"}
        ORDER BY dep.amt DESC LIMIT :lim
    """), {"lim": limit}).fetchall()
    sent = failed = 0
    for r in rows:
        res = send_purchase(r[1], r[4], "USD", r[2], r[3])
        if res.get("sent"):
            sent += 1
            db.execute(text("UPDATE leads SET meta_deposit_sent_at=NOW(), meta_deposit_value=:v WHERE id=:i"),
                       {"v": float(r[4] or 0), "i": r[0]})
        else:
            failed += 1
    db.commit()
    return {"ok": True, "sent": sent, "failed": failed, "scanned": len(rows),
            "configured": bool(SEND_TO_META and DATASET_ID)}


# ── UPDATE LEAD STAGE ────────────────────────────────────────────────────────
@router.post("/lead/{lead_id}/stage")
def update_lead_stage(
    lead_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Sales picks: qualified / converted / not_qualified / lost
    Updates CRM status + sends to Meta (if configured).
    """
    status = data.get("status")  # qualified/converted/not_qualified/lost
    if status not in STAGE_MAP:
        return {"error": f"Invalid status. Use one of: {list(STAGE_MAP.keys())}"}

    # Get lead Meta info
    row = db.execute(text("""
        SELECT meta_lead_id, email, phone FROM leads WHERE id = :lid
    """), {"lid": lead_id}).fetchone()
    if not row:
        return {"error": "Lead not found"}

    meta_lead_id, email, phone = row[0], row[1], row[2]
    event_name = STAGE_MAP[status]

    # Save Meta quality rating (separate from workflow status)
    db.execute(text("""
        UPDATE leads
        SET meta_quality = :status,
            meta_stage = :event_name,
            meta_stage_sent_at = NOW(),
            updated_at = NOW()
        WHERE id = :lid
    """), {"status": status, "event_name": event_name, "lid": lead_id})

    # Log the action
    db.execute(text("""
        INSERT INTO call_actions (login, agent_id, action, note, created_at)
        VALUES (NULL, :agent, :action, :note, NOW())
    """), {
        "agent": current_user.id,
        "action": f"meta_stage_{status}",
        "note": f"Lead #{lead_id} marked {status} → Meta event '{event_name}'"
    }) if False else None  # call_actions uses login not lead_id; skip if incompatible

    db.commit()

    # Send to Meta
    meta_result = {"sent": False, "reason": "no meta_lead_id"}
    if meta_lead_id:
        meta_result = send_to_meta(meta_lead_id, event_name, {"email": email, "phone": phone})

    return {
        "ok": True,
        "lead_id": lead_id,
        "status": status,
        "meta_event": event_name,
        "meta": meta_result
    }

# ── GET LEAD META INFO ───────────────────────────────────────────────────────
@router.get("/lead/{lead_id}/details")
def get_lead_meta_details(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Full Meta details for a lead: source, campaign, custom questions."""
    row = db.execute(text("""
        SELECT meta_lead_id, meta_platform, meta_publisher_platform,
               meta_platform_position, campaign_name, ad_name, adset_name,
               custom_questions, status, meta_stage, meta_stage_sent_at, source
        FROM leads WHERE id = :lid
    """), {"lid": lead_id}).fetchone()
    if not row:
        return {"error": "Lead not found"}

    return {
        "meta_lead_id":            row[0],
        "source":                  row[11] or row[1],
        "meta_platform":           row[1],
        "meta_publisher_platform": row[2],
        "meta_platform_position":  row[3],
        "campaign_name":           row[4],
        "ad_name":                 row[5],
        "adset_name":              row[6],
        "custom_questions":        row[7] or [],
        "status":                  row[8],
        "meta_stage":              row[9],
        "meta_stage_sent_at":      str(row[10]) if row[10] else None,
    }
