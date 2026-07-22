"""client_email_router.py — staff sends an email (with optional IMAGE attachments) to a client or
lead from inside the CRM (ticket #185). Server-side SMTP send, because a mailto: link can never
carry attachments.

SAFETY (the "perfect safe way"):
  * staff auth required (get_current_user);
  * From = the TNFX SMTP address with the staff member's display name; Reply-To = the staff's email
    so the client's reply reaches the real person (never exposes SMTP creds);
  * attachments are strictly IMAGES only (PNG / JPEG / GIF), ≤5 MB each, ≤12 MB and ≤5 files total,
    base64 decoded defensively (validate=True), filenames sanitized;
  * NO DDL in the request path (audit table is pre-created; the INSERT is best-effort).
"""
import base64
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import email_send

router = APIRouter(prefix="/client-email", tags=["client-email"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ALLOWED = {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg", "image/gif": "gif"}
MAX_FILES = 5
MAX_FILE_BYTES = 5 * 1024 * 1024      # 5 MB per image
MAX_TOTAL_BYTES = 12 * 1024 * 1024    # 12 MB across all images
MAX_SUBJECT = 300
MAX_BODY = 20000


@router.post("/send")
def send_client_email(payload: dict, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    to = (payload.get("to") or "").strip()
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    from_name = (payload.get("from_name") or "").strip()[:120]

    if not _EMAIL_RE.match(to):
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required.")
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required.")
    if len(subject) > MAX_SUBJECT or len(body) > MAX_BODY:
        raise HTTPException(status_code=400, detail="Subject or message is too long.")
    if not email_send.configured():
        raise HTTPException(status_code=503, detail="Email sending is not configured on the server.")

    raw_atts = payload.get("attachments") or []
    if not isinstance(raw_atts, list) or len(raw_atts) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FILES} image attachments are allowed.")
    attachments, total = [], 0
    for a in raw_atts:
        mt = (a.get("media_type") or "").lower().strip()
        sub = _ALLOWED.get(mt)
        if not sub:
            raise HTTPException(status_code=400, detail="Only image attachments (PNG, JPEG, GIF) are allowed.")
        data_b64 = a.get("data") or ""
        if data_b64.strip().startswith("data:") and "," in data_b64:
            data_b64 = data_b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(data_b64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="An attachment could not be read.")
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="Each image must be under 5 MB.")
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=400, detail="Total attachment size must be under 12 MB.")
        fname = re.sub(r"[^A-Za-z0-9._-]", "_", (a.get("name") or f"image.{sub}"))[:80]
        attachments.append({"filename": fname, "data": raw, "maintype": "image", "subtype": sub})

    reply_to = getattr(current_user, "email", None) or None
    disp = from_name or getattr(current_user, "full_name", None) or "TNFX"
    ok = email_send.send(to, subject, body, attachments=attachments, reply_to=reply_to, from_name=disp)
    if not ok:
        raise HTTPException(status_code=502, detail="The email could not be sent. Please try again.")

    # best-effort audit (table pre-created out-of-band; never DDL in the request path)
    try:
        db.execute(text("""INSERT INTO client_email_log (staff_id, staff_name, to_addr, subject, n_attach, created_at)
                           VALUES (:s,:sn,:t,:sub,:n,NOW())"""),
                   {"s": current_user.id, "sn": getattr(current_user, "full_name", "") or "",
                    "t": to, "sub": subject[:300], "n": len(attachments)})
        db.commit()
    except Exception:
        db.rollback()

    return {"ok": True, "sent": True, "attachments": len(attachments)}
