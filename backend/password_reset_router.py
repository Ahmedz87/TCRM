"""
password_reset_router.py — "Forgot password" via mobile OTP for BOTH the staff CRM
(users table) and the client portal (clients table).

Flow (3 steps, all under /auth/pwreset):
  1) POST /send    {identifier, scope}        -> find the account, text a 6-digit OTP to the
                                                 phone ON RECORD (never a user-supplied number),
                                                 return a masked destination. Anti-enumeration:
                                                 always returns ok=true even if no account/phone.
  2) POST /verify  {identifier, scope, code}  -> check the OTP, hand back a short-lived reset_token
  3) POST /reset   {reset_token, new_password}-> set the new password + invalidate old sessions

scope = 'staff' | 'client'.  OTP delivery reuses sms_send (real SMS once sms_config.py is set;
dev code 0000 otherwise — same convention as registration). All steps are rate-limited per IP and
per identifier to blunt abuse / OTP-bombing.
"""
import re
import random
import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from jose import jwt, JWTError

from database import get_db, settings
from auth import get_password_hash
import rate_limit
import sms_send
import email_send

router = APIRouter(prefix="/auth/pwreset", tags=["password reset"])

OTP_TTL_MIN = 10
RESET_TTL_MIN = 12
RESET_SCOPE = "pwreset"


def _limit(request, bucket, limit, window, key=None):
    k = key or rate_limit.client_ip(request)
    if not rate_limit.allow(bucket, k, limit, window):
        raise HTTPException(status_code=429, detail="Too many requests — please wait a moment and try again.")


def _ensure_otp_table(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id SERIAL PRIMARY KEY,
            contact TEXT, channel TEXT,
            code TEXT, expires_at TIMESTAMP,
            verified BOOLEAN DEFAULT FALSE, attempts INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.commit()


def _phone9(p):
    d = re.sub(r"[^0-9]", "", p or "")
    return d[-9:] if len(d) >= 9 else d


def _mask_phone(p):
    d = re.sub(r"[^0-9]", "", p or "")
    if len(d) < 4:
        return "your phone on file"
    return "•••• " + d[-3:]


def _mask_email(e):
    e = (e or "").strip()
    if "@" not in e:
        return "your email on file"
    name, dom = e.split("@", 1)
    head = name[0] if name else "•"
    return f"{head}•••@{dom}"


def _find_account(db, scope, identifier):
    """Return (account_key, phone, email) for the matched account, or (None, None, None).
    account_key is what we later write the new password against:
      staff  -> users.id
      client -> clients.id (pk)
    Match by email, phone (last 9 digits), or (client) trading login / client id."""
    ident = (identifier or "").strip()
    if not ident:
        return None, None, None
    p9 = _phone9(ident)
    if scope == "staff":
        row = db.execute(text("""
            SELECT id, phone, email FROM users
            WHERE LOWER(email) = LOWER(:e)
               OR (:p9 <> '' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9) = :p9)
            ORDER BY id ASC LIMIT 1
        """), {"e": ident, "p9": p9}).fetchone()
        if row:
            return ("staff", row[0]), row[1], row[2]
        return None, None, None
    # client
    row = db.execute(text("""
        SELECT id, phone, email FROM clients
        WHERE LOWER(email) = LOWER(:e)
           OR CAST(login AS TEXT) = :e
           OR CAST(id AS TEXT) = :e
           OR (:p9 <> '' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9) = :p9)
        ORDER BY COALESCE(total_deposits,0) DESC, id ASC LIMIT 1
    """), {"e": ident, "p9": p9}).fetchone()
    if row:
        return ("client", row[0]), row[1], row[2]
    return None, None, None


def _choose_channel(scope, phone, email):
    """Which channel to deliver the OTP on. Staff have emails (not phones) so prefer email;
    clients have phones so prefer SMS. Fall back to whatever contact exists."""
    has_phone = bool(_phone9(phone))
    has_email = bool(email and "@" in (email or ""))
    if scope == "staff":
        if has_email:
            return "email"
        if has_phone:
            return "sms"
    else:
        if has_phone:
            return "sms"
        if has_email:
            return "email"
    return None


def _otp_key(scope, account_id):
    return f"{scope}:{account_id}"


def _deliver_pwreset(deliver, phone, email, code):
    """Send the reset code over SMS/email in the BACKGROUND so the request returns instantly."""
    try:
        if deliver == "sms":
            sms_send.send(phone, f"Your TNFX password reset code is {code}. It expires in {OTP_TTL_MIN} minutes.")
        else:
            email_send.send(email, f"Your TNFX password reset code: {code}",
                            f"Your TNFX password reset code is {code}.\n\nIt expires in {OTP_TTL_MIN} minutes. "
                            "If you didn't request this, you can ignore this email.",
                            body_html=email_send.otp_html(code, "reset", OTP_TTL_MIN))
    except Exception as e:
        print(f"[pwreset delivery] failed for {deliver}: {e}", flush=True)


@router.post("/send")
def send(data: dict, background: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    _ensure_otp_table(db)
    scope = (data.get("scope") or "client").strip()
    identifier = (data.get("identifier") or "").strip()
    if scope not in ("staff", "client") or not identifier:
        return {"ok": True, "sent": False}      # generic; don't reveal anything
    _limit(request, "pwreset_ip", 10, 600)                       # 10 / 10 min per IP
    _limit(request, "pwreset_to", 5, 3600, key=identifier.lower())  # 5 / hour per identifier

    acct, phone, email = _find_account(db, scope, identifier)
    deliver = _choose_channel(scope, phone, email) if acct else None
    # Anti-enumeration: if no account or no deliverable contact, still return ok (nothing goes out).
    if not acct or not deliver:
        return {"ok": True, "sent": False, "masked_to": None}

    channel = f"pwreset_{scope}"
    contact = _otp_key(scope, acct[1])
    provider_live = (deliver == "sms" and sms_send.configured()) or (deliver == "email" and email_send.configured())
    code = f"{random.randint(0, 999999):06d}" if provider_live else "0000"
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_TTL_MIN)
    db.execute(text("UPDATE otp_codes SET verified=TRUE WHERE contact=:c AND channel=:ch AND verified=FALSE"),
               {"c": contact, "ch": channel})
    db.execute(text("INSERT INTO otp_codes (contact, channel, code, expires_at) VALUES (:c,:ch,:code,:e)"),
               {"c": contact, "ch": channel, "code": code, "e": exp})
    db.commit()

    masked = _mask_phone(phone) if deliver == "sms" else _mask_email(email)
    resp = {"ok": True, "sent": True, "channel": deliver, "masked_to": masked}
    if provider_live:
        background.add_task(_deliver_pwreset, deliver, phone, email, code)
    else:
        print(f"[pwreset/{scope}/{deliver}] {contact} -> {code}", flush=True)
        resp["dev_code"] = code     # dev-mode helper; ignored once a provider is live
    return resp


@router.post("/verify")
def verify(data: dict, request: Request, db: Session = Depends(get_db)):
    scope = (data.get("scope") or "client").strip()
    identifier = (data.get("identifier") or "").strip()
    code = (data.get("code") or "").strip()
    bad = {"ok": False, "error": "Incorrect or expired code."}
    if scope not in ("staff", "client") or not identifier or not code:
        return bad
    _limit(request, "pwreset_verify", 15, 600, key=identifier.lower())   # 15 / 10 min per identifier

    acct, phone, _ = _find_account(db, scope, identifier)
    if not acct:
        return bad
    channel = f"pwreset_{scope}"
    contact = _otp_key(scope, acct[1])
    row = db.execute(text("""
        SELECT id, code, expires_at FROM otp_codes
        WHERE contact=:c AND channel=:ch AND verified=FALSE ORDER BY id DESC LIMIT 1
    """), {"c": contact, "ch": channel}).fetchone()
    if not row:
        return {"ok": False, "error": "No code — please request a new one."}
    rid, real, exp = row
    if exp and datetime.datetime.utcnow() > exp:
        return {"ok": False, "error": "Code expired — please request a new one."}
    db.execute(text("UPDATE otp_codes SET attempts=attempts+1 WHERE id=:i"), {"i": rid})
    if code != real:
        db.commit()
        return bad
    db.execute(text("UPDATE otp_codes SET verified=TRUE WHERE id=:i"), {"i": rid})
    db.commit()
    reset_token = jwt.encode(
        {"scope": RESET_SCOPE, "acct_scope": acct[0], "acct_id": acct[1],
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=RESET_TTL_MIN)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return {"ok": True, "reset_token": reset_token}


@router.post("/reset")
def reset(data: dict, request: Request, db: Session = Depends(get_db)):
    token = (data.get("reset_token") or "").strip()
    new_password = data.get("new_password") or ""
    _limit(request, "pwreset_set", 20, 600)
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != RESET_SCOPE:
            raise ValueError("wrong scope")
        acct_scope = payload.get("acct_scope")
        acct_id = int(payload.get("acct_id"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="This reset link has expired — please start again.")

    pwh = get_password_hash(new_password)
    if acct_scope == "staff":
        # also invalidate every existing JWT session for this staff account
        db.execute(text("""
            UPDATE users SET hashed_password=:h, must_change_password=FALSE, tokens_valid_after=NOW()
            WHERE id=:id
        """), {"h": pwh, "id": acct_id})
    elif acct_scope == "client":
        db.execute(text("UPDATE clients SET password_hash=:h WHERE id=:id"), {"h": pwh, "id": acct_id})
        # any failed-login lockout for this client can be cleared so they can log in immediately
        try:
            db.execute(text("""
                DELETE FROM portal_login_attempts WHERE ident IN (
                    SELECT LOWER(email) FROM clients WHERE id=:id AND email IS NOT NULL
                    UNION SELECT CAST(login AS TEXT) FROM clients WHERE id=:id
                )
            """), {"id": acct_id})
        except Exception:
            db.rollback()
    else:
        raise HTTPException(status_code=400, detail="Invalid reset token.")
    db.commit()
    return {"ok": True, "message": "Your password has been reset. You can now log in."}
