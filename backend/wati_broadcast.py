"""
wati_broadcast.py — send WhatsApp TEMPLATE broadcasts through Wati to a CRM smart-segment.

WHY templates: WhatsApp only allows messaging a contact OUTSIDE the 24h service window with a
pre-APPROVED template — so a broadcast = an approved template sent to a list. Free text can't be
broadcast. Recipients come from the same Marketing segments used everywhere else.

SAFETY:
  • A single-number TEST send is always available first (send to yourself, verify, then broadcast).
  • The full send requires an explicit confirm=true (the UI shows the recipient count first).
  • Every broadcast is logged to wati_broadcasts (who/what/when/sent/failed).
  • Wati creds come from wati_config (already connected). The AI auto-reply LIVE switch is separate
    and NOT required for broadcasts (a broadcast is a deliberate staff action, not the bot).

Endpoints (prefix /wati, staff auth):
  GET  /wati/templates            approved templates (name, category, language, body, media?, #params)
  POST /wati/broadcast/preview    {segment_key} -> reachable count + masked sample numbers
  POST /wati/broadcast/test       {template_name, test_number, params[]} -> send to ONE number
  POST /wati/broadcast/send       {segment_key, template_name, params[], confirm} -> send to all (gated by confirm)
  GET  /wati/broadcasts           recent broadcast log
"""
import re
import time
import requests
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user
from marketing_router import SEG_BY_KEY, _base
import wati_attributes as WA

router = APIRouter(prefix="/wati", tags=["wati-broadcast"])

WATI_TIMEOUT = 30
BATCH = 200


def _creds(db):
    r = db.execute(text("SELECT api_endpoint, api_token FROM wati_config WHERE id=1")).fetchone()
    if not r or not r[0] or not r[1]:
        return None, None
    ep = r[0].rstrip("/")
    tok = r[1] if r[1].lower().startswith("bearer") else f"Bearer {r[1]}"
    return ep, tok


def _headers(tok):
    return {"Authorization": tok, "Content-Type": "application/json"}


def _norm_phone(p):
    """Wati wants the full international number, digits only, no '+' and no leading 00."""
    d = "".join(ch for ch in (p or "") if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    return d if len(d) >= 8 else None


def _param_count(body):
    """How many {{1}}, {{2}}… placeholders a template body has."""
    nums = re.findall(r"\{\{\s*(\d+)\s*\}\}", body or "")
    return max((int(n) for n in nums), default=0)


def _ensure(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wati_broadcasts (
            id SERIAL PRIMARY KEY,
            template TEXT, segment_key TEXT, broadcast_name TEXT,
            recipients INT DEFAULT 0, sent INT DEFAULT 0, failed INT DEFAULT 0,
            status TEXT, created_by TEXT, created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.commit()


# ─────────────────────────── templates ───────────────────────────
@router.get("/templates")
def templates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    ep, tok = _creds(db)
    if not ep:
        return {"error": "Wati not configured", "templates": []}
    try:
        r = requests.get(f"{ep}/api/v1/getMessageTemplates", headers=_headers(tok), timeout=WATI_TIMEOUT)
        data = r.json()
    except Exception as e:
        return {"error": str(e)[:160], "templates": []}
    items = data.get("messageTemplates") or data.get("data") or []
    out = []
    for t in items:
        if (t.get("status") or "").upper() != "APPROVED":
            continue
        body = t.get("body") or t.get("bodyOriginal") or ""
        hdr = t.get("header") or {}
        out.append({
            "name": t.get("elementName"),
            "category": t.get("category"),
            "language": (t.get("language") or {}).get("value") or "",
            "body": body,
            "footer": t.get("footer") or "",
            "has_media": (hdr.get("headerTypeString") or "").lower() in ("image", "video", "document"),
            "media_type": hdr.get("headerTypeString") or "",
            "param_count": _param_count(body),
        })
    out.sort(key=lambda x: (x["category"] != "MARKETING", x["name"] or ""))
    return {"templates": out}


# ─────────────────────────── recipients ───────────────────────────
def _recipients(db, seg, limit=None):
    frm, _alias, _em, ph = _base(seg["audience"])
    cap = f"LIMIT {int(limit)}" if limit else ""
    rows = db.execute(text(f"""
        SELECT {ph} FROM {frm}
        WHERE {seg['where']} AND {ph} IS NOT NULL AND {ph} <> ''
        {cap}
    """)).fetchall()
    seen, nums = set(), []
    for (raw,) in rows:
        n = _norm_phone(raw)
        if n and n not in seen:
            seen.add(n); nums.append(n)
    return nums


@router.post("/broadcast/preview")
def broadcast_preview(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    seg = SEG_BY_KEY.get(payload.get("segment_key"))
    if not seg:
        return {"error": "unknown segment_key"}
    nums = _recipients(db, seg)
    mask = [n[:4] + "***" + n[-2:] for n in nums[:5]]
    return {"segment": seg["label"], "reachable": len(nums), "sample": mask}


# ─────────────────────────── Wati template send ───────────────────────────
def _receivers(nums, params):
    cp = [{"name": str(i + 1), "value": v} for i, v in enumerate(params or []) if v not in (None, "")]
    return [{"whatsappNumber": n, "customParams": cp} for n in nums]


def _send_template(ep, tok, template_name, broadcast_name, nums, params):
    """POST Wati sendTemplateMessages in batches. Returns (sent, failed, last_detail)."""
    sent, failed, detail = 0, 0, ""
    for i in range(0, len(nums), BATCH):
        chunk = nums[i:i + BATCH]
        body = {"template_name": template_name, "broadcast_name": broadcast_name,
                "receivers": _receivers(chunk, params)}
        try:
            r = requests.post(f"{ep}/api/v1/sendTemplateMessages", headers=_headers(tok),
                              json=body, timeout=max(WATI_TIMEOUT, 60))
            ok = r.status_code < 300 and (r.json().get("result") is not False if r.text else True)
            if ok:
                sent += len(chunk)
            else:
                failed += len(chunk); detail = r.text[:200]
        except Exception as e:
            failed += len(chunk); detail = str(e)[:200]
    return sent, failed, detail


@router.post("/broadcast/test")
def broadcast_test(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ep, tok = _creds(db)
    if not ep:
        return {"error": "Wati not configured"}
    name = payload.get("template_name")
    num = _norm_phone(payload.get("test_number") or "")
    if not name or not num:
        return {"error": "template_name and a valid test_number are required"}
    bname = f"test_{name}_{int(time.time())}"
    sent, failed, detail = _send_template(ep, tok, name, bname, [num], payload.get("params") or [])
    return {"ok": sent == 1, "sent": sent, "failed": failed, "to": num, "detail": detail or "sent"}


@router.post("/broadcast/send")
def broadcast_send(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    ep, tok = _creds(db)
    if not ep:
        return {"error": "Wati not configured"}
    seg = SEG_BY_KEY.get(payload.get("segment_key"))
    name = payload.get("template_name")
    if not seg or not name:
        return {"error": "segment_key and template_name are required"}
    nums = _recipients(db, seg)
    if not payload.get("confirm"):
        # safety: never mass-send without an explicit confirm; return the count so the UI can ask
        return {"ok": False, "needs_confirm": True, "reachable": len(nums), "segment": seg["label"],
                "message": f"About to send template '{name}' to {len(nums):,} contacts. Re-send with confirm=true to proceed."}
    if not nums:
        return {"ok": False, "reachable": 0, "message": "No reachable numbers in this segment."}
    # optionally refresh contact attributes (ACD/agent + fill new contacts) in the background
    attrs_started = False
    if payload.get("sync_attrs") and seg["audience"] == "clients" and not WA.status().get("running"):
        WA.run_sync(seg["key"]); attrs_started = True
    bname = f"{name}_{seg['key']}_{int(time.time())}"
    sent, failed, detail = _send_template(ep, tok, name, bname, nums, payload.get("params") or [])
    who = getattr(user, "email", None) or getattr(user, "full_name", None) or "staff"
    db.execute(text("""INSERT INTO wati_broadcasts
        (template,segment_key,broadcast_name,recipients,sent,failed,status,created_by)
        VALUES (:t,:s,:b,:r,:sent,:f,:st,:who)"""),
        {"t": name, "s": seg["key"], "b": bname, "r": len(nums), "sent": sent, "f": failed,
         "st": "sent" if failed == 0 else ("partial" if sent else "failed"), "who": str(who)})
    db.commit()
    return {"ok": sent > 0, "template": name, "segment": seg["label"], "broadcast_name": bname,
            "reachable": len(nums), "sent": sent, "failed": failed, "detail": detail or "ok",
            "attrs_sync_started": attrs_started}


# ─────────────────────────── contact attributes (ACD = current agent, etc.) ───────────────────────────
@router.get("/attributes/preview")
def attributes_preview(segment_key: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    seg = SEG_BY_KEY.get(segment_key)
    if not seg:
        return {"error": "unknown segment_key"}
    if seg["audience"] != "clients":
        return {"error": "attributes apply to CLIENT segments (they carry the agent/deposits).", "sample": []}
    return {"segment": seg["label"], "sample": WA.preview_segment(db, seg)}


@router.post("/attributes/sync")
def attributes_sync(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    seg = SEG_BY_KEY.get(payload.get("segment_key"))
    if not seg:
        return {"error": "unknown segment_key"}
    if seg["audience"] != "clients":
        return {"error": "attributes apply to CLIENT segments only"}
    if WA.status().get("running"):
        return {"ok": False, "message": "A sync is already running.", "status": WA.status()}
    WA.run_sync(seg["key"])
    return {"ok": True, "message": f"Attribute sync started for '{seg['label']}' — runs in the background "
                                   "(updates ACD/agent + fills new contacts). Watch progress under status."}


@router.get("/attributes/status")
def attributes_status(user=Depends(get_current_user)):
    return WA.status()


@router.get("/broadcasts")
def list_broadcasts(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    rows = db.execute(text("""SELECT id,template,segment_key,recipients,sent,failed,status,created_by,created_at
                              FROM wati_broadcasts ORDER BY id DESC LIMIT 100""")).fetchall()
    return {"broadcasts": [dict(zip(
        ["id", "template", "segment_key", "recipients", "sent", "failed", "status", "created_by", "created_at"], r))
        for r in rows]}
