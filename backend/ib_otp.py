"""
ib_otp.py — one-time codes for the partner portal (partner1.tnfx.co).

Channels:
  · email — via email_send (SMTP configured)
  · sms   — via sms_send (the EXISTING TNFX SMS OTP gateway, Infobip). If SMS isn't
            configured / fails, callers can fall back to email ("mobile dead/lost").

Purposes: activate (first login of an existing IB), reset (forgot password),
signup_email / signup_phone (the new-IB wizard). Codes: 6 digits, 10-minute expiry,
5 attempts, one active code per (target, purpose).
"""
import random
from datetime import datetime
from sqlalchemy import text

import email_send
import sms_send

OTP_TTL_MIN = 10
MAX_ATTEMPTS = 5

_READY = False


def _ensure(db):
    global _READY
    if _READY:
        return
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_otps (
            id SERIAL PRIMARY KEY,
            target VARCHAR(180) NOT NULL,      -- lower(email) or normalised phone
            channel VARCHAR(16) NOT NULL,      -- email | whatsapp
            purpose VARCHAR(24) NOT NULL,
            code VARCHAR(8) NOT NULL,
            attempts INTEGER DEFAULT 0,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    db.commit()
    _READY = True


def _norm_phone(p: str) -> str:
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    return d[-13:]


def _send_sms(phone: str, code: str) -> bool:
    """Send via the existing TNFX SMS gateway (sms_send). Returns False if unconfigured/failed."""
    try:
        return bool(sms_send.send(phone, f"Your TNFX verification code is {code}. Valid for {OTP_TTL_MIN} minutes."))
    except Exception as e:
        print(f"[ib_otp] sms send failed: {e}", flush=True)
        return False


def send(db, channel: str, target: str, purpose: str) -> dict:
    """Create + deliver a code. Returns {"sent": bool, "channel": ..., "detail": ...}."""
    _ensure(db)
    tgt = (target or "").strip().lower() if channel == "email" else _norm_phone(target)
    if not tgt:
        return {"sent": False, "detail": "no target"}
    # throttle: max 3 codes per target/purpose per 15 min
    n = db.execute(text("""SELECT COUNT(*) FROM ib_otps
        WHERE target=:t AND purpose=:p AND created_at > NOW() - INTERVAL '15 minutes'"""),
        {"t": tgt, "p": purpose}).scalar() or 0
    if n >= 3:
        return {"sent": False, "detail": "Too many codes requested — try again in a few minutes"}
    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    db.execute(text("UPDATE ib_otps SET used=TRUE WHERE target=:t AND purpose=:p AND NOT used"),
               {"t": tgt, "p": purpose})
    db.execute(text("""INSERT INTO ib_otps (target, channel, purpose, code)
                       VALUES (:t, :c, :p, :code)"""),
               {"t": tgt, "c": channel, "p": purpose, "code": code})
    db.commit()
    if channel == "sms":
        ok = _send_sms(target, code)
        return {"sent": ok, "channel": "sms",
                "detail": "" if ok else "SMS delivery unavailable — use the email option"}
    try:
        ok = email_send.send(tgt, "Your TNFX Partners verification code",
                             f"Your TNFX verification code is: {code}\nIt expires in {OTP_TTL_MIN} minutes.",
                             email_send.notice_html("Verification code",
                                                    f"Your TNFX Partners verification code is <b style='font-size:22px'>{code}</b>.",
                                                    f"The code expires in {OTP_TTL_MIN} minutes. If you didn't request it, ignore this email."))
        return {"sent": bool(ok), "channel": "email",
                "detail": "" if ok else "Email delivery failed — contact support"}
    except Exception as e:
        return {"sent": False, "channel": "email", "detail": f"Email failed: {e}"}


def verify(db, target: str, purpose: str, code: str, channel_hint: str = "") -> bool:
    _ensure(db)
    tgt = (target or "").strip().lower() if "@" in str(target) else _norm_phone(target)
    row = db.execute(text("""SELECT id, code, attempts FROM ib_otps
        WHERE target=:t AND purpose=:p AND NOT used
          AND created_at > NOW() - make_interval(mins => :ttl)
        ORDER BY created_at DESC LIMIT 1"""),
        {"t": tgt, "p": purpose, "ttl": OTP_TTL_MIN}).fetchone()
    if not row:
        return False
    oid, real, attempts = row
    if (attempts or 0) >= MAX_ATTEMPTS:
        return False
    if str(code).strip() != str(real):
        db.execute(text("UPDATE ib_otps SET attempts = attempts + 1 WHERE id=:i"), {"i": oid})
        db.commit()
        return False
    db.execute(text("UPDATE ib_otps SET used=TRUE WHERE id=:i"), {"i": oid})
    db.commit()
    return True
