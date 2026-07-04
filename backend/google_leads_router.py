"""
google_leads_router.py — receive Google Ads Lead Form submissions via WEBHOOK.

No Google Ads API / OAuth2 needed: when a user submits your Google lead form, Google POSTs the
lead to our URL in real time. You set two things in the lead form's "Lead delivery" options:
  Webhook URL : https://my1.tnfx.co/api/google/lead-webhook
  Key         : (the key shown by GET /google/lead-config — Google echoes it back as google_key)

Leads land in `leads` with source='google', de-duped on google_lead_id, and are auto-routed
through the lead-assignment rules (same as Meta leads).
"""
import secrets
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, SessionLocal
from auth import get_current_user

router = APIRouter(prefix="/google", tags=["google-leads"])

WEBHOOK_URL = "https://my1.tnfx.co/api/google/lead-webhook"


def _ensure(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS google_lead_config (
            id INT PRIMARY KEY DEFAULT 1, webhook_key TEXT, enabled BOOLEAN DEFAULT TRUE,
            received INT DEFAULT 0, updated_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("INSERT INTO google_lead_config (id, webhook_key) VALUES (1, :k) ON CONFLICT (id) DO NOTHING"),
               {"k": secrets.token_urlsafe(18)})
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS leads_google_lead_id_uq ON leads(google_lead_id) WHERE google_lead_id IS NOT NULL"))
    db.commit()


def _config(db):
    _ensure(db)
    r = db.execute(text("SELECT webhook_key, enabled, received FROM google_lead_config WHERE id=1")).fetchone()
    return {"webhook_key": r[0], "enabled": bool(r[1]), "received": int(r[2] or 0)}


def _parse_fields(payload):
    """Map Google's user_column_data[] -> (full_name, email, phone). Column ids vary, so match
    by keyword, robust to FULL_NAME / FIRST_NAME+LAST_NAME / custom labels."""
    first = last = name = email = phone = ""
    for f in payload.get("user_column_data", []) or []:
        cid = (f.get("column_id") or f.get("column_name") or "").upper()
        val = (f.get("string_value") or "").strip()
        if not val:
            continue
        if cid in ("FULL_NAME", "NAME"):
            name = val
        elif cid == "FIRST_NAME":
            first = val
        elif cid == "LAST_NAME":
            last = val
        elif "EMAIL" in cid:
            email = val
        elif "PHONE" in cid:
            phone = val
    if not name:
        name = (first + " " + last).strip()
    return name, email, phone


@router.post("/lead-webhook")
async def google_lead_webhook(request: Request):
    """PUBLIC. Google POSTs lead form submissions here."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}
    db = SessionLocal()
    try:
        cfg = _config(db)
        # verify the shared key Google echoes back (when set on the form)
        if cfg["webhook_key"] and payload.get("google_key") and payload["google_key"] != cfg["webhook_key"]:
            return {"ok": False, "error": "bad key"}
        if payload.get("is_test"):
            return {"ok": True, "test": True}      # Google's "Send test data" button
        name, email, phone = _parse_fields(payload)
        if not (name or email or phone):
            return {"ok": True}
        gid = str(payload.get("lead_id") or "") or None
        camp = str(payload.get("campaign_id") or payload.get("form_id") or "Google Lead Form")
        # de-dup on google_lead_id
        if gid:
            ex = db.execute(text("SELECT id FROM leads WHERE google_lead_id=:g"), {"g": gid}).fetchone()
            if ex:
                return {"ok": True, "duplicate": True}
        lid = db.execute(text("""
            INSERT INTO leads (full_name, email, phone, status, source, campaign_name,
                               google_lead_id, score, created_at, updated_at)
            VALUES (:n,:e,:p,'new','google',:c,:g,40,NOW(),NOW()) RETURNING id
        """), {"n": name or None, "e": email or None, "p": phone or None, "c": camp, "g": gid}).scalar()
        db.execute(text("UPDATE google_lead_config SET received=received+1 WHERE id=1"))
        db.commit()
        # auto-route through the lead-assignment rules (guarded — never break intake)
        try:
            import lead_routing
            if lead_routing.get_config(db).get("auto_assign_enabled"):
                lead_routing.assign_lead(db, lid, commit=True)
        except Exception:
            db.rollback()
        return {"ok": True, "lead_id": lid}
    except Exception:
        db.rollback()
        return {"ok": True}        # never error back to Google (it would retry/disable the hook)
    finally:
        db.close()


@router.get("/lead-config")
def lead_config(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Staff: the webhook URL + key to paste into the Google lead form, and how many received."""
    cfg = _config(db)
    cnt = db.execute(text("SELECT COUNT(*) FROM leads WHERE source='google'")).scalar()
    return {"webhook_url": WEBHOOK_URL, "webhook_key": cfg["webhook_key"],
            "enabled": cfg["enabled"], "received": cfg["received"], "google_leads_in_crm": int(cnt or 0)}


@router.post("/lead-config/rotate-key")
def rotate_key(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    k = secrets.token_urlsafe(18)
    db.execute(text("UPDATE google_lead_config SET webhook_key=:k, updated_at=NOW() WHERE id=1"), {"k": k})
    db.commit()
    return {"webhook_key": k}
