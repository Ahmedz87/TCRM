"""
wati_router.py — WhatsApp (Wati) AI conversations. Webhook + simulator + admin.

PUBLIC:  POST /wati/webhook        inbound WhatsApp from Wati -> queued -> AI reply (+ gated send)
STAFF :  POST /wati/simulate       dry-run one message (identity + AI reply + would-be actions), no send/no persist
         GET  /wati/conversations  recent threads
         GET  /wati/conversations/{phone}/messages
         GET/POST /wati/config      LIVE switch, auto-reply, AI-ownership, current offer, endpoint/token
         GET  /wati/status         config + counts + ai status

Burst handling: the webhook ACKs immediately and hands the message to a bounded worker pool
(capped concurrency) so a 1,000-lead spike is processed quickly without overloading the AI API.
In-process pool is fine for this box; swap for an external queue if volumes get very large.
"""
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, SessionLocal
from auth import get_current_user
import whatsapp_ai
import wati_service

router = APIRouter(prefix="/wati", tags=["wati"])

# bounded concurrency — handles bursts without hammering the AI/Wati rate limits
_POOL = ThreadPoolExecutor(max_workers=12)


def _process_inbound(phone, message, name=None):
    """Runs in a worker thread: AI reply + gated send. Own DB session."""
    db = SessionLocal()
    try:
        cfg = whatsapp_ai.get_config(db)
        # FULL STOP: when the bot is OFF (LIVE-send off AND auto-reply off) it must not run the AI
        # or reply at all. Just keep the inbound message so nothing is lost, then return.
        if not cfg.get("enabled") and not cfg.get("auto_reply"):
            try:
                whatsapp_ai.ensure_schema(db)
                whatsapp_ai._log(db, phone, "in", message, is_ai=False)
            except Exception:
                db.rollback()
            return
        # seed a name for brand-new contacts (Wati gives the WhatsApp profile name)
        res = whatsapp_ai.generate_reply(db, phone, message, history=_recent_history(db, phone), dry_run=False)
        if cfg.get("auto_reply", True):
            raw = db.execute(text("SELECT api_endpoint, api_token, enabled FROM wati_config WHERE id=1")).fetchone()
            send_cfg = {"enabled": bool(raw[2]), "api_endpoint": raw[0] or "", "_api_token": raw[1] or ""}
            wati_service.send_message(send_cfg, phone, res.get("reply", ""))
        return res
    except Exception:
        db.rollback()
    finally:
        db.close()


def _recent_history(db, phone, limit=10):
    rows = db.execute(text("""
        SELECT direction, body FROM wa_messages WHERE phone=:p ORDER BY id DESC LIMIT :l
    """), {"p": phone, "l": limit}).fetchall()
    hist = [{"role": "assistant" if r[0] == "out" else "user", "content": r[1]} for r in reversed(rows)]
    return hist


def _extract_inbound(payload):
    """Pull (phone, text, name) from a Wati webhook payload (tolerant of shape variants)."""
    phone = (payload.get("waId") or payload.get("phone") or payload.get("from")
             or (payload.get("contact") or {}).get("waId") or "")
    text_ = (payload.get("text") or payload.get("messageText") or payload.get("body") or "")
    if isinstance(payload.get("message"), dict):
        text_ = text_ or payload["message"].get("text", "")
    name = payload.get("senderName") or payload.get("name") or (payload.get("contact") or {}).get("name")
    return str(phone), str(text_), name


@router.post("/webhook")
async def wati_webhook(request: Request):
    """PUBLIC inbound. Acks fast, processes in the worker pool. Only acts on inbound text events."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}
    etype = (payload.get("eventType") or payload.get("type") or "").lower()
    # SAFETY: only act on INBOUND customer messages. Never react to our own outgoing messages,
    # delivery/read receipts, or call-status events (prevents the bot replying to itself).
    owner = payload.get("owner")  # Wati: true = message WE sent
    is_outbound = (owner is True) or any(k in etype for k in ("sent", "status", "ack", "delivered", "read"))
    inbound_event = ("message" in etype) or ("received" in etype) or (etype == "")
    phone, msg, name = _extract_inbound(payload)
    if phone and msg and inbound_event and not is_outbound:
        _POOL.submit(_process_inbound, phone, msg, name)
    return {"ok": True}


@router.post("/simulate")
def wati_simulate(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Dry-run: resolve identity + generate the AI reply + show would-be actions. Persists NOTHING."""
    phone = str(payload.get("phone") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not phone or not message:
        return {"error": "phone and message required"}
    history = payload.get("history") or []
    res = whatsapp_ai.generate_reply(db, phone, message, history=history, dry_run=True)
    return res


@router.get("/conversations")
def conversations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    whatsapp_ai.ensure_schema(db)
    rows = db.execute(text("""
        SELECT phone, identity_kind, identity_name, client_login, lead_id, status,
               messages_in, messages_out, last_message_at
        FROM wa_conversations ORDER BY last_message_at DESC NULLS LAST LIMIT 200
    """)).fetchall()
    return {"conversations": [{
        "phone": r[0], "kind": r[1], "name": r[2], "login": r[3], "lead_id": r[4],
        "status": r[5], "messages_in": r[6], "messages_out": r[7],
        "last_message_at": str(r[8])[:16] if r[8] else None} for r in rows]}


@router.get("/conversations/{phone}/messages")
def thread(phone: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT direction, body, is_ai, escalated, created_at FROM wa_messages
        WHERE phone=:p ORDER BY id ASC LIMIT 500
    """), {"p": phone}).fetchall()
    return {"phone": phone, "messages": [{
        "direction": r[0], "body": r[1], "is_ai": bool(r[2]), "escalated": bool(r[3]),
        "at": str(r[4])[:16] if r[4] else None} for r in rows]}


@router.get("/config")
def get_cfg(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return whatsapp_ai.get_config(db)


@router.post("/config")
def set_cfg(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return whatsapp_ai.save_config(db, payload)


@router.get("/teachings")
def get_teachings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"teachings": whatsapp_ai.list_teachings(db),
            "staff_phones": whatsapp_ai.list_staff_phones(db)}


@router.post("/teachings")
def add_teaching(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    note = (payload.get("note") or "").strip()
    if not note:
        return {"ok": False, "error": "empty"}
    return {"ok": True, "id": whatsapp_ai.add_teaching(db, note, author_phone="admin-ui")}


@router.patch("/teachings/{tid}")
def toggle_teaching(tid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    whatsapp_ai.set_teaching_active(db, tid, bool(payload.get("active", True)))
    return {"ok": True}


@router.delete("/teachings/{tid}")
def del_teaching(tid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    whatsapp_ai.delete_teaching(db, tid)
    return {"ok": True}


@router.post("/staff-phones")
def add_staff(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ok = whatsapp_ai.add_staff_phone(db, (payload.get("phone") or "").strip(), payload.get("label"))
    return {"ok": ok}


@router.delete("/staff-phones")
def del_staff(payload: dict = None, phone: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    whatsapp_ai.remove_staff_phone(db, (payload or {}).get("phone") or phone)
    return {"ok": True}


@router.get("/status")
def status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    cfg = whatsapp_ai.get_config(db)
    try:
        import ai_config
        ai_ok = ai_config.is_configured()
    except Exception:
        ai_ok = False
    counts = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM wa_conversations),
          (SELECT COUNT(*) FROM wa_conversations WHERE status='escalated'),
          (SELECT COUNT(*) FROM wa_messages WHERE direction='out' AND is_ai),
          (SELECT COUNT(*) FROM leads WHERE source='whatsapp'),
          (SELECT COUNT(*) FROM leads WHERE COALESCE(ai_managed,false))
    """)).fetchone()
    return {"config": cfg, "ai_configured": ai_ok,
            "connected": bool(cfg.get("api_endpoint") and cfg.get("api_token_set")),
            "stats": {"conversations": counts[0], "escalated": counts[1], "ai_replies": counts[2],
                      "wa_leads": counts[3], "ai_owned_leads": counts[4]}}
