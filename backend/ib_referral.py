"""
ib_referral.py — the SOLID standalone IB referral link (desk spec Jul 15 2026).

Link pattern:   https://my1.tnfx.co/r/<CODE>            (+ optional ?src=google|telegram|...)
What it does:   1) logs the click — UNIQUE per (code, ip-hash) per 30 days (the unique-click
                   count feeds the weekly challenges), with the traffic source captured
                2) sets a 30-DAY cookie  tnfx_ref=<CODE>|<src>  (Domain=.tnfx.co so it
                   survives my1/partner1)
                3) redirects to the my1 register page with ?ref=<CODE> as belt-and-braces
Attribution:    registration_router reads the ?ref param OR the cookie and stamps the new
                lead with the IB (leads.ib_id + a row in ib_ref_signups). Old link styles
                (register?ref=..., Plugit custom links) keep working unchanged.

Codes are per-IB, short and stable: existing ib_code if it's clean, else TX<base36(ib_id)>.
"""
import hashlib
import re
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db

router = APIRouter(tags=["IB Referral"])

REGISTER_URL = "https://my1.tnfx.co/register"
COOKIE_DAYS = 30

_READY = False


def _ensure(db):
    global _READY
    if _READY:
        return
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_ref_codes (
            ib_id INTEGER PRIMARY KEY,
            code  VARCHAR(24) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS ib_ref_clicks (
            id SERIAL PRIMARY KEY,
            code VARCHAR(24) NOT NULL,
            ib_id INTEGER,
            ip_hash VARCHAR(40),
            src VARCHAR(40),
            ua VARCHAR(200),
            is_unique BOOLEAN DEFAULT FALSE,
            at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_ib_ref_clicks_code ON ib_ref_clicks (code, ip_hash, at);
        CREATE TABLE IF NOT EXISTS ib_ref_signups (
            id SERIAL PRIMARY KEY,
            code VARCHAR(24),
            ib_id INTEGER,
            src VARCHAR(40),
            lead_id INTEGER,
            email VARCHAR(180),
            phone VARCHAR(60),
            at TIMESTAMPTZ DEFAULT NOW()
        );
    """))
    db.commit()
    _READY = True


def _b36(n: int) -> str:
    s, a = "", "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # no I/L/O/U — unambiguous
    n = max(1, int(n))
    while n:
        n, r = divmod(n, 32)
        s = a[r] + s
    return s


def get_or_create_code(db, ib_id: int) -> str:
    """Stable short code for the IB. Prefers a CLEAN existing ib_code (letters/digits, <=12)."""
    _ensure(db)
    row = db.execute(text("SELECT code FROM ib_ref_codes WHERE ib_id=:i"), {"i": ib_id}).fetchone()
    if row:
        return row[0]
    ibc = db.execute(text("SELECT ib_code FROM ibs WHERE id=:i"), {"i": ib_id}).scalar() or ""
    cand = ibc.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,12}", cand or ""):
        cand = "TX" + _b36(ib_id)
    base, n = cand, 2
    while db.execute(text("SELECT 1 FROM ib_ref_codes WHERE code=:c"), {"c": cand}).fetchone():
        cand, n = f"{base}{n}", n + 1
    db.execute(text("INSERT INTO ib_ref_codes (ib_id, code) VALUES (:i,:c) ON CONFLICT (ib_id) DO NOTHING"),
               {"i": ib_id, "c": cand})
    db.commit()
    return cand


def resolve_code(db, code: str):
    """code -> ib_id (also accepts a raw ib_code for old-style links)."""
    if not code:
        return None
    _ensure(db)
    c = str(code).strip().upper()
    row = db.execute(text("SELECT ib_id FROM ib_ref_codes WHERE UPPER(code)=:c"), {"c": c}).fetchone()
    if row:
        return row[0]
    row = db.execute(text("SELECT id FROM ibs WHERE UPPER(TRIM(ib_code))=:c LIMIT 1"), {"c": c}).fetchone()
    return row[0] if row else None


def record_signup(db, ref_raw: str, lead_id, email: str, phone: str):
    """Called by registration: ref_raw = 'CODE' or 'CODE|src'. Returns ib_id or None."""
    if not ref_raw:
        return None
    parts = str(ref_raw).split("|", 1)
    code, src = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    ib_id = resolve_code(db, code)
    if not ib_id:
        return None
    db.execute(text("""INSERT INTO ib_ref_signups (code, ib_id, src, lead_id, email, phone)
                       VALUES (:c,:i,:s,:l,:e,:p)"""),
               {"c": code.upper(), "i": ib_id, "s": src[:40], "l": lead_id,
                "e": (email or "")[:180], "p": (phone or "")[:60]})
    return ib_id


@router.get("/r/{code}")
def ref_redirect(code: str, request: Request, src: str = "", db: Session = Depends(get_db)):
    """The public referral hop: log click (unique per ip/30d), set the 30-day cookie, redirect."""
    _ensure(db)
    ib_id = resolve_code(db, code)
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or request.headers.get("x-real-ip", "")
          or (request.client.host if request.client else ""))
    ip_hash = hashlib.sha1(f"{code.upper()}|{ip}".encode()).hexdigest()[:32]
    src = re.sub(r"[^a-zA-Z0-9_\-\.]", "", src or "")[:40]
    if ib_id:
        seen = db.execute(text("""SELECT 1 FROM ib_ref_clicks
            WHERE code=:c AND ip_hash=:h AND is_unique AND at > NOW() - INTERVAL '30 days' LIMIT 1"""),
            {"c": code.upper(), "h": ip_hash}).fetchone()
        db.execute(text("""INSERT INTO ib_ref_clicks (code, ib_id, ip_hash, src, ua, is_unique)
                           VALUES (:c,:i,:h,:s,:u,:q)"""),
                   {"c": code.upper(), "i": ib_id, "h": ip_hash, "s": src,
                    "u": (request.headers.get("user-agent") or "")[:200], "q": not seen})
        db.commit()
    resp = RedirectResponse(url=f"{REGISTER_URL}?ref={code.upper()}" + (f"&src={src}" if src else ""),
                            status_code=302)
    resp.set_cookie("tnfx_ref", f"{code.upper()}|{src}", max_age=COOKIE_DAYS * 86400,
                    domain=".tnfx.co", path="/", samesite="lax")
    return resp


def unique_clicks(db, ib_id: int, since: str = None) -> int:
    _ensure(db)
    q = "SELECT COUNT(*) FROM ib_ref_clicks WHERE ib_id=:i AND is_unique"
    p = {"i": ib_id}
    if since:
        q += " AND at >= CAST(:s AS timestamptz)"
        p["s"] = since
    return db.execute(text(q), p).scalar() or 0
