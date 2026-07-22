"""
ib_portal_auth.py — auth for the SPLIT IB portal at partner1.tnfx.co (Jul 2026).

The partner site serves the same React build in "partner mode": IBs REGISTER and LOG IN here
(no staff involved). Tokens carry scope='ib' + ib_id and are only accepted by:
  • the /ib-portal/* endpoints below, and
  • the per-IB /ibs/{id}/... endpoints via the staff_or_own_ib dependency (an IB can only
    read/act on their OWN profile; staff tokens keep full access).

New IB signup creates a PENDING ibs row (no MT agent account yet) — the desk sees it in
IB Admin (status 'pending'), links the MT agent_id / level when approving.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta
from jose import jwt

from database import get_db, settings
import models
from auth import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/ib-portal", tags=["IB Portal"])

# ── Brute-force lockout (public partner1.tnfx.co). Reuses the client portal's
# `portal_login_attempts` table; IB idents are prefixed "ib:" so their counters are
# independent of the client portal's. Same thresholds/window as the client portal.
MAX_FAILS_IDENT = 5
MAX_FAILS_IP = 20
WINDOW_MIN = 15


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    xr = request.headers.get("x-real-ip")
    if xr:
        return xr.strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _ensure_attempts_table():
    """Create the shared lockout table ONCE at import (not per-login — per-request DDL is a
    lock-contention hazard). Idempotent; the client portal may have already created it."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SET lock_timeout = '4s'"))
        db.execute(text("""CREATE TABLE IF NOT EXISTS portal_login_attempts (
            id SERIAL PRIMARY KEY, ident VARCHAR(160), ip VARCHAR(64),
            ok BOOLEAN, created_at TIMESTAMP DEFAULT NOW())"""))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _is_locked(db: Session, ident: str, ip: str) -> bool:
    try:
        fails = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE ident=:i) AS by_ident,
                   COUNT(*) FILTER (WHERE ip=:p)    AS by_ip
            FROM portal_login_attempts
            WHERE ok=FALSE AND created_at > NOW() - make_interval(mins => :w)
        """), {"i": ident, "p": ip, "w": WINDOW_MIN}).fetchone()
        db.commit()
    except Exception:
        db.rollback()
        return False
    return (fails[0] or 0) >= MAX_FAILS_IDENT or (fails[1] or 0) >= MAX_FAILS_IP


def _record_attempt(db: Session, ident: str, ip: str, ok: bool):
    try:
        db.execute(text("INSERT INTO portal_login_attempts (ident, ip, ok) VALUES (:i,:p,:o)"),
                   {"i": ident[:160], "p": ip, "o": ok})
        if ok:
            db.execute(text("DELETE FROM portal_login_attempts WHERE ident=:i AND ok=FALSE"), {"i": ident})
        db.execute(text("DELETE FROM portal_login_attempts WHERE created_at < NOW() - INTERVAL '1 day'"))
        db.commit()
    except Exception:
        db.rollback()


_ensure_attempts_table()

_SCHEMA_DONE = False


def _ensure_schema(db: Session):
    """Ensure ibs.password_hash exists. IMPORTANT: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
    still queues an ACCESS EXCLUSIVE lock on ibs even when the column already exists — behind a
    single idle-in-transaction that briefly held ibs, that no-op ALTER blocks EVERY reader of ibs
    (IB list/profile/login all 500). So we check the catalog first (a cheap ACCESS SHARE read) and
    only take the exclusive lock on the one-time real migration."""
    global _SCHEMA_DONE
    if _SCHEMA_DONE:
        return
    try:
        exists = db.execute(text("""SELECT 1 FROM information_schema.columns
            WHERE table_name='ibs' AND column_name='password_hash' LIMIT 1""")).fetchone()
        if not exists:
            db.execute(text("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS password_hash TEXT"))
            db.commit()
        _SCHEMA_DONE = True
    except Exception:
        db.rollback()


def _token_payload(request: Request) -> dict:
    hdr = request.headers.get("authorization", "")
    token = hdr[7:] if hdr.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_ib(request: Request, db: Session = Depends(get_db)) -> models.IB:
    payload = _token_payload(request)
    if payload.get("scope") != "ib":
        raise HTTPException(status_code=403, detail="Not an IB portal token")
    ib = db.query(models.IB).filter(models.IB.id == int(payload.get("ib_id") or 0)).first()
    if not ib:
        raise HTTPException(status_code=401, detail="IB not found")
    return ib


def get_current_staff(request: Request, db: Session = Depends(get_db)) -> models.User:
    """Staff-ONLY gate for the partner-site admin pages (challenge settings etc.)."""
    payload = _token_payload(request)
    if payload.get("scope") == "ib":
        raise HTTPException(status_code=403, detail="Staff only")
    u = db.query(models.User).filter(models.User.email == payload.get("sub")).first()
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    return u


def staff_or_own_ib(ib_id: int, request: Request, db: Session = Depends(get_db)):
    """Dual auth for /ibs/{ib_id}/... reads used by the portal: a STAFF token passes for any id;
    an IB token passes only for its OWN id."""
    payload = _token_payload(request)
    if payload.get("scope") == "ib":
        if int(payload.get("ib_id") or 0) != int(ib_id):
            raise HTTPException(status_code=403, detail="Not your IB profile")
        return None                      # IB self-access (no staff user object)
    email = payload.get("sub")
    u = db.query(models.User).filter(models.User.email == email).first()
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    return u


@router.post("/auth/register")
def register(data: dict, db: Session = Depends(get_db)):
    _ensure_schema(db)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    if not name or not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Name and a valid email are required")
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")
    import re as _re
    if len(_re.sub(r"\D", "", phone)) < 8:   # E.164 (dial+national) — sanity floor; the client does per-country length
        raise HTTPException(status_code=400, detail="Enter a valid phone number")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    import json as _json
    from ib_portal_extras import ensure_tables as _ext_tables, notify as _notify
    _ext_tables(db)
    dup = db.execute(text("SELECT id FROM ibs WHERE lower(TRIM(email)) = :e LIMIT 1"), {"e": email}).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail="An IB with this email already exists — log in instead")
    # DEDUP: has this person already applied as an IB (same phone) OR is an existing client?
    phone9 = "".join(ch for ch in phone if ch.isdigit())[-9:]
    dup_req = db.execute(text("""SELECT id, name FROM ibs
        WHERE status IN ('pending','approved') AND phone IS NOT NULL
          AND RIGHT(regexp_replace(phone,'[^0-9]','','g'),9) = :p9 LIMIT 1"""),
        {"p9": phone9}).fetchone() if phone9 else None
    if dup_req:
        raise HTTPException(status_code=409,
            detail="An application with this phone number is already under review. Our desk will contact you.")
    # link to an existing CLIENT profile (same email or phone) — the desk can see they're a client too
    client_login = db.execute(text("""SELECT login FROM clients
        WHERE lower(email) = :e OR (:p9 <> '' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9) = :p9)
        LIMIT 1"""), {"e": email, "p9": phone9}).fetchone()
    profile = data.get("profile") or {}
    if client_login:
        profile["existing_client_login"] = client_login[0]
    # keep only socials whose URL domain matches their tagged platform (anti-tamper: the client
    # validates this too, but never trust the client — a "telegram" entry pointing at evil.com is dropped)
    from ib_social_verify import _host_ok_for_platform, _norm_url
    from urllib.parse import urlparse as _urlparse
    socials = []
    for _s in (data.get("social_links") or []):
        try:
            _u = _norm_url(_s.get("url", ""))
            _host = _urlparse(_u).hostname or ""
            if _u and _host_ok_for_platform(_host, (_s.get("platform") or "").lower()):
                socials.append(_s)
        except Exception:
            pass
    # ── ACCOUNT MANAGER (the reviewer) — desk rule Jul 2026 ──────────────────────────────────
    # If the applicant is already a CLIENT or a LEAD, keep their EXISTING account manager (same
    # person handles them). A brand-new applicant is assigned to the RETENTION team, round-robin
    # (the retention agent with the fewest IBs right now → balances "in order").
    mgr = None
    if client_login:
        mgr = db.execute(text("SELECT assigned_agent_id FROM clients WHERE login=:l AND assigned_agent_id IS NOT NULL LIMIT 1"),
                         {"l": client_login[0]}).scalar()
    if not mgr:
        mgr = db.execute(text("""SELECT assigned_agent_id FROM leads
            WHERE assigned_agent_id IS NOT NULL
              AND (lower(email)=:e OR (:p9<>'' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p9))
            ORDER BY assigned_at DESC NULLS LAST LIMIT 1"""), {"e": email, "p9": phone9}).scalar()
    if not mgr:
        mgr = db.execute(text("""SELECT u.id FROM users u
            LEFT JOIN ibs i ON i.assigned_agent_id = u.id
            WHERE LOWER(COALESCE(u.team_type,''))='retention' AND COALESCE(u.is_active, TRUE)
            GROUP BY u.id ORDER BY COUNT(i.id) ASC, u.id ASC LIMIT 1""")).scalar()

    agreed = bool(data.get("agreement_accepted"))
    from ib_portal_extras import AGREEMENT_VERSION as _AGR_VER   # keep signup version in sync with the source of truth
    row = db.execute(text("""
        INSERT INTO ibs (name, email, phone, country, city, ib_level, status, is_primary, assigned_agent_id,
                         password_hash, bio, applicant_profile, social_links,
                         agreement_accepted_at, agreement_version,
                         ib_creation_date, created_at, updated_at)
        VALUES (:n, :e, :p, :co, :ci, 5, 'pending', TRUE, :mgr, :ph, :bio,
                CAST(:prof AS jsonb), CAST(:soc AS jsonb),
                CASE WHEN :ag THEN NOW() ELSE NULL END, CASE WHEN :ag THEN :av ELSE NULL END,
                NOW(), NOW(), NOW())
        RETURNING id"""), {
        "n": name, "e": email, "p": phone, "co": (data.get("country") or "").strip(),
        "ci": (data.get("city") or "").strip(), "ph": get_password_hash(password), "mgr": mgr,
        "bio": (data.get("bio") or "").strip(), "prof": _json.dumps(profile),
        "soc": _json.dumps(socials), "ag": agreed, "av": _AGR_VER}).fetchone()
    db.commit()
    token = create_access_token({"sub": email, "scope": "ib", "ib_id": row[0]},
                                expires_delta=timedelta(days=7))
    return {"access_token": token, "ib_id": row[0], "status": "pending",
            "linked_client": bool(client_login),
            "message": "Application received — our partnership team will activate your account"}


@router.post("/verify-social")
def verify_social(body: dict):
    """Signup-time link check (no auth — the applicant has no token yet). Validates the domain
    matches the tagged platform and best-effort confirms the page exists / handle matches.
    SSRF-guarded inside verify_link()."""
    from ib_social_verify import verify_link
    url = (body.get("url") or "").strip()
    if len(url) > 500:
        raise HTTPException(status_code=400, detail="Link too long")
    return verify_link(body.get("platform") or "", url, body.get("name") or "")


@router.post("/auth/signup-otp")
def signup_otp(data: dict, db: Session = Depends(get_db)):
    """OTP for the new-IB signup wizard. channel=email|sms, purpose=signup_email|signup_phone."""
    import ib_otp
    channel = (data.get("channel") or "email").strip().lower()
    purpose = (data.get("purpose") or "signup_email").strip()
    if channel == "sms":
        phone = (data.get("phone") or "").strip()
        if not phone:
            raise HTTPException(status_code=400, detail="Phone number required")
        return ib_otp.send(db, "sms", phone, purpose)
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    return ib_otp.send(db, "email", email, purpose)


@router.post("/auth/signup-otp/verify")
def signup_otp_verify(data: dict, db: Session = Depends(get_db)):
    import ib_otp
    channel = (data.get("channel") or "email").strip().lower()
    purpose = (data.get("purpose") or "signup_email").strip()
    target = (data.get("phone") if channel == "sms" else data.get("email")) or ""
    ok = ib_otp.verify(db, target, purpose, (data.get("code") or "").strip())
    if not ok:
        raise HTTPException(status_code=400, detail="Wrong or expired code")
    return {"ok": True}


@router.post("/auth/login")
def login(data: dict, request: Request, db: Session = Depends(get_db)):
    _ensure_schema(db)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    ip = _client_ip(request)
    lock_ident = "ib:" + email          # namespaced so IB lockouts are independent of the client portal
    # Block before touching the password once over the limit.
    if _is_locked(db, lock_ident, ip):
        raise HTTPException(status_code=429,
            detail=f"Too many failed attempts. Try again in {WINDOW_MIN} minutes.")
    row = db.execute(text("""SELECT id, password_hash FROM ibs
        WHERE lower(TRIM(email)) = :e AND password_hash IS NOT NULL
        ORDER BY is_primary DESC NULLS LAST LIMIT 1"""), {"e": email}).fetchone()
    if row and verify_password(password, row[1]):
        _record_attempt(db, lock_ident, ip, True)
        token = create_access_token({"sub": email, "scope": "ib", "ib_id": row[0]},
                                    expires_delta=timedelta(days=7))
        return {"access_token": token, "ib_id": row[0]}
    # STAFF fallback: admins/staff may log in at the partner site too — they get a normal
    # staff token and the frontend shows an IB PICKER (view any IB exactly as the IB sees it).
    u = db.query(models.User).filter(models.User.email == email).first()
    if u and getattr(u, "is_active", True) and verify_password(password, u.hashed_password):
        _record_attempt(db, lock_ident, ip, True)
        token = create_access_token({"sub": u.email}, expires_delta=timedelta(days=1))
        return {"access_token": token, "staff": True,
                "name": u.full_name or "", "role": getattr(u, "role", "") or ""}
    _record_attempt(db, lock_ident, ip, False)
    raise HTTPException(status_code=401, detail="Wrong email or password")


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    payload = _token_payload(request)
    if payload.get("scope") == "ib":
        ib = db.query(models.IB).filter(models.IB.id == int(payload.get("ib_id") or 0)).first()
        if not ib:
            raise HTTPException(status_code=401, detail="IB not found")
        return {"ib_id": ib.id, "name": ib.name or "", "email": ib.email or "",
                "status": ib.status or "", "ib_code": ib.ib_code or "",
                "agent_id": ib.agent_id, "ib_level": ib.ib_level or 5,
                "pending": not ib.agent_id}
    # staff token
    u = db.query(models.User).filter(models.User.email == payload.get("sub")).first()
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    return {"staff": True, "name": u.full_name or "", "email": u.email,
            "full_name": u.full_name or "", "role": getattr(u, "role", "") or ""}


# ─── ACTIVATION / OTP / FORGOT-PASSWORD (existing IBs, Jul 15 2026) ────────────
def _mask_phone(p: str) -> str:
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    return ("•" * max(0, len(d) - 4) + d[-4:]) if d else ""


@router.post("/auth/lookup")
def auth_lookup(data: dict, db: Session = Depends(get_db)):
    """Frontend calls this when an email is entered at login. Tells it whether this is:
    an existing IB WITHOUT a password (→ activation wizard, shows the masked phone on file),
    an IB WITH a password (→ normal login), a staff user, or unknown."""
    _ensure_schema(db)
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return {"kind": "unknown"}
    row = db.execute(text("""SELECT id, phone, password_hash, name FROM ibs
        WHERE lower(TRIM(email)) = :e ORDER BY is_primary DESC NULLS LAST LIMIT 1"""),
        {"e": email}).fetchone()
    if row:
        if row[2]:
            return {"kind": "ib_has_password", "name": row[3] or ""}
        return {"kind": "ib_activate", "ib_id": row[0], "name": row[3] or "",
                "phone_mask": _mask_phone(row[1]), "has_phone": bool(row[1])}
    u = db.query(models.User).filter(models.User.email == email).first()
    if u:
        return {"kind": "staff"}
    return {"kind": "unknown"}


@router.post("/auth/otp/send")
def otp_send(data: dict, request: Request, db: Session = Depends(get_db)):
    """Send an OTP. channel=sms|email. For activation the phone is validated against the
    IB on file only when we HAVE one; a lost/dead phone falls back to channel=email."""
    import ib_otp
    _ensure_schema(db)
    channel = (data.get("channel") or "email").strip().lower()
    email = (data.get("email") or "").strip().lower()
    purpose = (data.get("purpose") or "activate").strip()
    ib = db.execute(text("SELECT id, phone FROM ibs WHERE lower(TRIM(email))=:e ORDER BY is_primary DESC NULLS LAST LIMIT 1"),
                    {"e": email}).fetchone()
    if channel == "sms":
        phone = (data.get("phone") or (ib[1] if ib else "") or "").strip()
        if not phone:
            raise HTTPException(status_code=400, detail="Phone number required")
        # remember the phone the IB is verifying so activation can save it
        res = ib_otp.send(db, "sms", phone, purpose)
        res["phone"] = phone
        return res
    return ib_otp.send(db, "email", email, purpose)


@router.post("/auth/activate")
def auth_activate(data: dict, request: Request, db: Session = Depends(get_db)):
    """Existing IB sets their first password after verifying an OTP (phone or email).
    Also stores the confirmed phone number (proves the mobile is live)."""
    import ib_otp
    _ensure_schema(db)
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    channel = (data.get("channel") or "email").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    ib = db.execute(text("SELECT id, phone FROM ibs WHERE lower(TRIM(email))=:e ORDER BY is_primary DESC NULLS LAST LIMIT 1"),
                    {"e": email}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="No IB account for that email")
    target = phone if channel == "sms" else email
    if not ib_otp.verify(db, target, "activate", code):
        raise HTTPException(status_code=400, detail="Wrong or expired code")
    upd = {"h": get_password_hash(password), "id": ib[0]}
    if channel == "sms" and phone:
        db.execute(text("UPDATE ibs SET password_hash=:h, phone=:p WHERE id=:id"),
                   {**upd, "p": phone})
    else:
        db.execute(text("UPDATE ibs SET password_hash=:h WHERE id=:id"), upd)
    db.commit()
    token = create_access_token({"sub": email, "scope": "ib", "ib_id": ib[0]}, expires_delta=timedelta(days=7))
    return {"access_token": token, "ib_id": ib[0]}


@router.post("/auth/forgot/send")
def forgot_send(data: dict, db: Session = Depends(get_db)):
    """Email OTP for a password reset (only for IBs who already have a password)."""
    import ib_otp
    _ensure_schema(db)
    email = (data.get("email") or "").strip().lower()
    ib = db.execute(text("SELECT id FROM ibs WHERE lower(TRIM(email))=:e AND password_hash IS NOT NULL LIMIT 1"),
                    {"e": email}).fetchone()
    if not ib:
        # do not reveal whether the email exists
        return {"sent": True, "channel": "email", "detail": "If the email is registered, a code was sent"}
    return ib_otp.send(db, "email", email, "reset")


@router.post("/auth/forgot/reset")
def forgot_reset(data: dict, db: Session = Depends(get_db)):
    import ib_otp
    _ensure_schema(db)
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    password = data.get("password") or ""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not ib_otp.verify(db, email, "reset", code):
        raise HTTPException(status_code=400, detail="Wrong or expired code")
    ib = db.execute(text("SELECT id FROM ibs WHERE lower(TRIM(email))=:e ORDER BY is_primary DESC NULLS LAST LIMIT 1"),
                    {"e": email}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="No IB account for that email")
    db.execute(text("UPDATE ibs SET password_hash=:h WHERE id=:id"),
               {"h": get_password_hash(password), "id": ib[0]})
    db.commit()
    # wipe the IB's lockout so they can log in immediately
    _record_attempt(db, "ib:" + email, "reset", True)
    token = create_access_token({"sub": email, "scope": "ib", "ib_id": ib[0]}, expires_delta=timedelta(days=7))
    return {"access_token": token, "ib_id": ib[0]}


# ── IB GRADES / promotion requirements (desk sheet Jul 13 2026) ───────────────
# level → grade name, $/lot shown to the IB, and what it takes to REACH that grade:
# minimum deposits, monthly-AVERAGE lots, minimum number of funded accounts.
# DB table is the source of truth (editable in the admin settings UI); this is only the seed.
_TIER_SEED = [
    (5,  "Bronze",    5,  0,      0,    0),
    (6,  "Silver",    6,  1500,   20,   5),
    (7,  "Golden",    7,  10000,  50,   15),
    (8,  "Diamond",   8,  100000, 200,  40),
    (9,  "Legendary", 9,  300000, 1000, 100),
    (10, "Prime IB",  10, 500000, 2500, 200),
]
_TIERS_READY = False


def ensure_tier_reqs(db):
    global _TIERS_READY
    if _TIERS_READY:
        return
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_tier_requirements (
            level        INTEGER PRIMARY KEY,
            name         VARCHAR NOT NULL,
            comm_per_lot DOUBLE PRECISION DEFAULT 0,
            min_deposit  DOUBLE PRECISION DEFAULT 0,
            min_lots_avg DOUBLE PRECISION DEFAULT 0,
            min_accounts INTEGER DEFAULT 0
        )"""))
    if not (db.execute(text("SELECT COUNT(*) FROM ib_tier_requirements")).scalar() or 0):
        for lvl, name, comm, dep, lots, accts in _TIER_SEED:
            db.execute(text("""
                INSERT INTO ib_tier_requirements (level, name, comm_per_lot, min_deposit, min_lots_avg, min_accounts)
                VALUES (:l, :n, :c, :d, :lo, :a) ON CONFLICT (level) DO NOTHING"""),
                {"l": lvl, "n": name, "c": comm, "d": dep, "lo": lots, "a": accts})
    db.commit()
    _TIERS_READY = True


def get_tier_reqs(db):
    ensure_tier_reqs(db)
    return [{"level": r[0], "name": r[1], "comm_per_lot": float(r[2] or 0),
             "min_deposit": float(r[3] or 0), "min_lots_avg": float(r[4] or 0),
             "min_accounts": int(r[5] or 0)}
            for r in db.execute(text("""
                SELECT level, name, comm_per_lot, min_deposit, min_lots_avg, min_accounts
                FROM ib_tier_requirements ORDER BY level""")).fetchall()]


@router.get("/admin/tier-reqs")
def get_tier_requirements(db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    return {"tiers": get_tier_reqs(db)}


@router.put("/admin/tier-reqs")
def save_tier_requirements(data: dict, db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    if (getattr(staff, "role", "") or "") not in ("super_admin", "admin", "director"):
        raise HTTPException(status_code=403, detail="Admin only")
    ensure_tier_reqs(db)
    def _f(v, d=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d
    for t in (data.get("tiers") or []):
        lvl = int(_f(t.get("level")))
        if lvl < 5 or lvl > 10:
            continue
        db.execute(text("""
            INSERT INTO ib_tier_requirements (level, name, comm_per_lot, min_deposit, min_lots_avg, min_accounts)
            VALUES (:l, :n, :c, :d, :lo, :a)
            ON CONFLICT (level) DO UPDATE SET name=:n, comm_per_lot=:c, min_deposit=:d,
                                              min_lots_avg=:lo, min_accounts=:a"""),
            {"l": lvl, "n": (t.get("name") or "").strip() or f"IB-{lvl}",
             "c": _f(t.get("comm_per_lot")), "d": _f(t.get("min_deposit")),
             "lo": _f(t.get("min_lots_avg")), "a": int(_f(t.get("min_accounts")))})
    db.commit()
    return {"ok": True, "tiers": get_tier_reqs(db)}


# ── partner-site ADMIN: challenge / career-path settings (staff only) ─────────
@router.get("/admin/challenge-defs")
def get_challenge_defs(db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    import ib_challenges
    return {"career": ib_challenges.get_career(db, include_disabled=True),
            "weekly": ib_challenges.get_weekly(db, include_disabled=True)}


@router.put("/admin/challenge-defs")
def save_challenge_defs(data: dict, db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    # mirror of the my1 nav gate: only admin-level staff may EDIT the challenge definitions
    if (getattr(staff, "role", "") or "") not in ("super_admin", "admin", "director"):
        raise HTTPException(status_code=403, detail="Admin only")
    import ib_challenges
    try:
        counts = ib_challenges.admin_save(db, data.get("career"), data.get("weekly"))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not save: {e}")
    return {"ok": True, **counts}
