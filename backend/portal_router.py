"""
TNFX Client Portal — client-scoped API.
SECURITY: every data endpoint derives client_id from the verified JWT
(get_current_client), NEVER from request input. A trader can only ever
read/affect their own data.

Auth here is a TEMPORARY dev login that issues a portal-scoped JWT.
Swap dev_login for real client credential verification later.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from jose import jwt, JWTError

from database import get_db, settings  # reuse same SECRET_KEY / ALGORITHM
from auth import verify_password, get_password_hash, get_current_user  # bcrypt (passlib) + staff auth
import bonus_engine as BE  # welcome/deposit bonus + withdrawal guard

router = APIRouter(prefix="/portal", tags=["portal"])

# Set to True ONLY in a private/dev environment to allow passwordless impersonation.
# MUST stay False on the public site (my1.tnfx.co) — otherwise anyone could log in as
# any client just by typing a name/email.
ALLOW_DEV_LOGIN = False

# separate token URL so portal logins are distinct from admin
portal_oauth = OAuth2PasswordBearer(tokenUrl="portal/auth/dev-login", auto_error=False)

PORTAL_SCOPE = "portal"


def _make_portal_token(client_id: int, imp: bool = False) -> str:
    payload = {
        "sub": str(client_id),
        "scope": PORTAL_SCOPE,
        "exp": datetime.utcnow() + timedelta(hours=(1 if imp else 12)),
    }
    if imp:
        payload["imp"] = True   # admin "view as client" — read-only (mutations blocked), 1h expiry
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def impersonation_flag(token: str = Depends(portal_oauth)) -> bool:
    """True when the current portal session is an admin 'view as client' preview (read-only)."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return bool(payload.get("imp"))
    except Exception:
        return False


def block_impersonation(token: str = Depends(portal_oauth)):
    """Dependency for money/account mutations: 403 if this is an admin read-only 'view as client' session."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("imp"):
            raise HTTPException(status_code=403, detail="Admin preview is read-only — this action is disabled.")
    except HTTPException:
        raise
    except Exception:
        pass
    return True


@router.post("/impersonate/{login}")
def impersonate(login: int, _user=Depends(get_current_user), db: Session = Depends(get_db)):
    """STAFF-only: mint a read-only portal token to VIEW the portal as this client's login. The token
    carries imp=True (1h expiry) so money/account actions are blocked. The admin opens /portal/?imp=<token>."""
    cid = db.execute(text("SELECT id, name FROM clients WHERE login=:l ORDER BY id LIMIT 1"),
                     {"l": login}).fetchone()
    if not cid:
        return {"ok": False, "error": "no client account for that login"}
    return {"ok": True, "token": _make_portal_token(int(cid[0]), imp=True),
            "login": login, "name": cid[1]}


def get_current_client(token: str = Depends(portal_oauth), db: Session = Depends(get_db)) -> int:
    """Decode the portal JWT and return the client_id. Rejects admin tokens."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != PORTAL_SCOPE:
            raise HTTPException(status_code=401, detail="Wrong token scope")
        client_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return client_id


# ───────────────────────── LOGIN BRUTE-FORCE PROTECTION ─────────────────────────
# my1.tnfx.co is public, so the portal login is exposed to password guessing.
# DB-backed (shared across the 2 uvicorn workers + survives restarts) lockout:
#   - per identifier: LOCK after MAX_FAILS_IDENT fails within WINDOW_MIN
#   - per IP:         LOCK after MAX_FAILS_IP fails within WINDOW_MIN (slows account spraying)
# A successful login clears that identifier's failures.
MAX_FAILS_IDENT = 5
MAX_FAILS_IP = 20
WINDOW_MIN = 15

def _ensure_login_attempts_table():
    from database import SessionLocal
    db = SessionLocal()
    try:
        # Fail fast on lock contention so a backend restart can never hang here.
        db.execute(text("SET lock_timeout = '4s'"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS portal_login_attempts (
                id SERIAL PRIMARY KEY, ident VARCHAR(160), ip VARCHAR(64),
                ok BOOLEAN, created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_pla_ident_time ON portal_login_attempts (ident, created_at)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_pla_ip_time ON portal_login_attempts (ip, created_at)"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

_ensure_login_attempts_table()


def _client_ip(request: Request) -> str:
    # nginx sets X-Real-IP / X-Forwarded-For (real client behind the proxy)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    xr = request.headers.get("x-real-ip")
    if xr:
        return xr.strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _record_attempt(db: Session, ident: str, ip: str, ok: bool):
    try:
        db.execute(text(
            "INSERT INTO portal_login_attempts (ident, ip, ok) VALUES (:i,:p,:o)"
        ), {"i": (ident or "")[:160].lower(), "p": ip, "o": ok})
        # opportunistic cleanup of stale rows so the table stays small
        db.execute(text("DELETE FROM portal_login_attempts WHERE created_at < NOW() - INTERVAL '1 day'"))
        db.commit()
    except Exception:
        db.rollback()


# ───────────────────────── AUTH ─────────────────────────
@router.post("/auth/login")
def portal_login(payload: dict, request: Request, db: Session = Depends(get_db)):
    """
    REAL client login: identifier (email OR trading login OR client id) + password.
    Verifies clients.password_hash (bcrypt). A client with NO password set cannot log in.
    Public site (my1.tnfx.co) — there is NO passwordless path here.
    """
    ident = (payload.get("identifier") or payload.get("username") or "").strip()
    password = payload.get("password") or ""
    ip = _client_ip(request)
    bad = HTTPException(status_code=401, detail="Incorrect login or password")
    if not ident or not password:
        raise bad

    # ── Brute-force lockout: block before touching the password if over the limit ──
    try:
        fails = db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE ident=:i) AS by_ident,
              COUNT(*) FILTER (WHERE ip=:p)    AS by_ip
            FROM portal_login_attempts
            WHERE ok=FALSE AND created_at > NOW() - make_interval(mins => :w)
        """), {"i": ident.lower(), "p": ip, "w": WINDOW_MIN}).fetchone()
    except Exception:
        db.rollback(); fails = (0, 0)
    if (fails[0] or 0) >= MAX_FAILS_IDENT or (fails[1] or 0) >= MAX_FAILS_IP:
        raise HTTPException(status_code=429,
            detail=f"Too many failed attempts. Try again in {WINDOW_MIN} minutes.")

    # Match ONLY by hard identifiers (email / login number / client id) — never by name.
    # Require a password to be set (COALESCE guard) so passwordless rows are unreachable.
    row = db.execute(text("""
        SELECT id, name, password_hash, COALESCE(is_blocked, FALSE) FROM clients
        WHERE (LOWER(email) = LOWER(:exact)
               OR CAST(login AS TEXT) = :exact
               OR CAST(id AS TEXT) = :exact)
          AND COALESCE(password_hash, '') <> ''
        ORDER BY COALESCE(total_deposits,0) DESC, id ASC
        LIMIT 1
    """), {"exact": ident}).fetchone()
    if not row or not verify_password(password, row[2]):
        _record_attempt(db, ident, ip, False)
        raise bad
    if row[3]:   # account blocked by an admin
        raise HTTPException(status_code=403, detail="This account has been suspended. Please contact support.")

    # success — log it and clear this identifier's failure streak
    _record_attempt(db, ident, ip, True)
    try:
        db.execute(text("DELETE FROM portal_login_attempts WHERE ident=:i AND ok=FALSE"),
                   {"i": ident.lower()}); db.commit()
    except Exception:
        db.rollback()

    # an ARCHIVED client logging in = re-engagement -> bring them back to the active list
    # (+50 score, 📦 archive re-capture badge). See reactivation.py.
    try:
        import reactivation
        reactivation.reactivate_client_logins(db, _client_logins(db, int(row[0])), via="login")
    except Exception:
        db.rollback()

    return {
        "access_token": _make_portal_token(int(row[0])),
        "token_type": "bearer",
        "client_id": int(row[0]),
        "name": row[1] or f"Client #{row[0]}",
    }


@router.post("/auth/change-password")
def portal_change_password(payload: dict, client_id: int = Depends(get_current_client),
                           db: Session = Depends(get_db)):
    """Logged-in client changes their own portal password (verifies the current one).
    Returns a fresh token so the change doesn't log them out, and clears any lockout."""
    current = payload.get("current_password") or ""
    new = payload.get("new_password") or ""
    if len(new) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    row = db.execute(text("SELECT email, login, password_hash FROM clients WHERE id=:id"),
                     {"id": client_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    if not row[2] or not verify_password(current, row[2]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(new, row[2]):
        raise HTTPException(status_code=400, detail="New password must be different from the current one")
    db.execute(text("UPDATE clients SET password_hash=:h WHERE id=:id"),
               {"h": get_password_hash(new), "id": client_id})
    # clear any failed-login lockout for this client's identifiers
    try:
        idents = [str(row[1])]
        if row[0]:
            idents.append(str(row[0]).lower())
        db.execute(text("DELETE FROM portal_login_attempts WHERE ident = ANY(:ids)"), {"ids": idents})
    except Exception:
        db.rollback()
    db.commit()
    return {"ok": True, "message": "Password changed.",
            "access_token": _make_portal_token(client_id), "token_type": "bearer"}


@router.post("/auth/dev-login")
def dev_login(payload: dict, db: Session = Depends(get_db)):
    """DISABLED on the public site. Passwordless impersonation is gated behind
    ALLOW_DEV_LOGIN (False here) so it cannot be used at my1.tnfx.co."""
    if not ALLOW_DEV_LOGIN:
        raise HTTPException(status_code=403, detail="Disabled. Use /portal/auth/login with a password.")
    cid = payload.get("client_id")
    ident = (payload.get("identifier") or "").strip()
    if cid is not None:
        row = db.execute(text(
            "SELECT id FROM clients WHERE id=:n OR login=:n ORDER BY (id=:n) DESC LIMIT 1"
        ), {"n": int(cid)}).fetchone()
        cid = row[0] if row else None
    if cid is None and ident:
        like = f"%{ident}%"
        row = db.execute(text("""
            SELECT id FROM clients
            WHERE email ILIKE :exact OR name ILIKE :l OR phone ILIKE :l
                  OR CAST(id AS TEXT)=:exact OR CAST(login AS TEXT)=:exact
            ORDER BY COALESCE(total_deposits,0) DESC, id ASC LIMIT 1
        """), {"l": like, "exact": ident}).fetchone()
        if row:
            cid = row[0]
    if not cid:
        raise HTTPException(status_code=404, detail="Client not found")
    name_row = db.execute(text("SELECT name FROM clients WHERE id=:id LIMIT 1"),
                          {"id": int(cid)}).fetchone()
    return {
        "access_token": _make_portal_token(int(cid)),
        "token_type": "bearer",
        "client_id": int(cid),
        "name": (name_row[0] if name_row else None) or f"Client #{cid}",
    }


# ───────────────────────── PROFILE ─────────────────────────
@router.get("/me")
def me(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    r = db.execute(text("""
        SELECT id, name, email, phone, city, country, group_name
        FROM clients WHERE id=:id LIMIT 1
    """), {"id": client_id}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    # loyalty quick-summary
    loy = db.execute(text("""
        SELECT tier, points_balance, current_streak FROM loyalty_accounts WHERE client_id=:id
    """), {"id": client_id}).fetchone()
    return {
        "client_id": r[0], "name": r[1] or f"Client #{r[0]}",
        "email": r[2] or "", "phone": r[3] or "",
        "city": r[4] or "", "country": r[5] or "",
        "tier": (loy[0] if loy else None),
        "points": float(loy[1]) if loy else 0,
        "streak": (loy[2] if loy else 0),
    }


# ── Resolve every login that belongs to this portal client ──
# trading_accounts.client_id is NOT populated (NULL everywhere), so the link is by login:
# the client's own login PLUS every sibling account sharing the same phone+platform
# (same aggregation the Clients list uses). Cached per-request via the simple call site.
def _client_logins(db: Session, client_id: int) -> list:
    base = db.execute(text(
        "SELECT login, phone, COALESCE(platform,'') FROM clients WHERE id=:id"
    ), {"id": client_id}).fetchone()
    if not base:
        return []
    logins = {base[0]} if base[0] is not None else set()
    if base[1]:  # has a phone -> pull the whole phone+platform cluster
        for r in db.execute(text(
            "SELECT login FROM clients WHERE phone=:p AND COALESCE(platform,'')=:pl AND login IS NOT NULL"
        ), {"p": base[1], "pl": base[2]}).fetchall():
            logins.add(r[0])
    return sorted(logins)


def _assert_owns_login(db: Session, client_id: int, login) -> None:
    """Defense-in-depth: a client may only act on a login that belongs to them.
    login=None is allowed (the request isn't account-specific)."""
    if login in (None, "", 0):
        return
    if str(login) not in {str(l) for l in _client_logins(db, client_id)}:
        raise HTTPException(status_code=403, detail="That account is not yours.")


def _assert_not_archived(db: Session, login) -> None:
    """Archived (MT4/MT5-archived) accounts are READ-ONLY: no new deposits or internal
    transfers. History, IB/sales commission and loyalty stay intact — only money-IN actions
    are blocked. login=None is allowed (non-account-specific request)."""
    if login in (None, "", 0):
        return
    archived = db.execute(text(
        "SELECT archived_at FROM clients WHERE login=:l"), {"l": login}).scalar()
    if archived is not None:
        raise HTTPException(status_code=403,
            detail="This account is archived (inactive). You can view its history, but deposits "
                   "and transfers are disabled. Please use an active account.")


# ───────────────────────── ACCOUNTS ─────────────────────────
@router.get("/accounts")
def accounts(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    logins = _client_logins(db, client_id)
    # ONLY real MT logins (positive). The registrant's temp placeholder login is NEGATIVE
    # (-(1000000+rid)) and must NEVER be shown as a "dummy account".
    pos = [l for l in logins if l and l > 0]
    rows = []
    if pos:
        rows = db.execute(text("""
            SELECT ta.login, ta.name, ta.group_name, ta.account_type, ta.leverage, ta.balance, ta.platform,
                   (c.archived_at IS NOT NULL) AS archived
            FROM trading_accounts ta LEFT JOIN clients c ON c.login = ta.login
            WHERE ta.login = ANY(:logins)
            ORDER BY ta.balance DESC NULLS LAST
        """), {"logins": pos}).fetchall()
    # No real account yet -> tell the UI to show "pending verification" instead of a fake login.
    pending = False
    if not rows:
        ks = (db.execute(text("SELECT kyc_status FROM clients WHERE id=:id"), {"id": client_id}).scalar() or "").lower()
        pending = ks in ("pending_review", "under_review", "submitted", "in_review", "docs_needed", "pending", "verified")
    # Account TYPE + bonus eligibility are derived from the GROUP (ta.account_type is
    # unreliable — 'live'/NULL/raw group). Any STD* group = Standard = bonus-eligible.
    import account_types
    out_accts = []
    for r in rows:
        cg = account_types.classify_group(r[2] or "")
        out_accts.append({
            "login": r[0], "name": r[1] or "", "group": r[2] or "",
            "type": cg["label"] or (r[3] or ""),   # friendly label e.g. "Standard Islamic account"
            "base_type": cg["base"], "islamic": cg["islamic"], "is_standard": cg["is_standard"],
            "leverage": r[4], "balance": float(r[5]) if r[5] is not None else None,
            "platform": r[6] or "", "archived": bool(r[7]) if len(r) > 7 else False,
        })
    return {"accounts": out_accts, "pending": pending}


# ───────────────────────── TRADES ─────────────────────────
@router.get("/trades")
def trades(client_id: int = Depends(get_current_client), db: Session = Depends(get_db), limit: int = 50):
    logins = _client_logins(db, client_id)
    if not logins:
        return {"trades": []}
    rows = db.execute(text("""
        SELECT d.deal_time, d.login, d.symbol, d.volume, d.price, d.profit, d.action
        FROM deals d
        WHERE d.login = ANY(:logins) AND d.entry = 1 AND d.action IN (0,1)
        ORDER BY d.deal_time DESC
        LIMIT :lim
    """), {"logins": logins, "lim": min(limit, 200)}).fetchall()
    out = []
    for r in rows:
        ts = r[0]
        try:
            dt = datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M") if ts else ""
        except Exception:
            dt = ""
        out.append({
            "time": dt, "login": r[1], "symbol": r[2] or "",
            "lots": round((r[3] or 0) / 10000, 2), "price": float(r[4]) if r[4] else 0,
            "profit": float(r[5]) if r[5] is not None else 0,
            "side": "Buy" if r[6] == 0 else "Sell",
        })
    return {"trades": out}


# ── IB commission-trades for the logged-in IB (their clients' trades + commission) ──
@router.get("/ib-trades")
def ib_trades(
    client_login: int = None, country: str = None, city: str = None,
    platform: str = None, account_type: str = None,
    period: str = "this_month", date_from: str = None, date_to: str = None,
    view: str = "eligible", page: int = 1, page_size: int = 100,
    client_id: int = Depends(get_current_client), db: Session = Depends(get_db),
):
    from ib_router import period_dates
    ib_id = db.execute(text("""
        SELECT ib.id FROM ibs ib JOIN clients c ON c.login = ib.agent_id WHERE c.id = :cid
    """), {"cid": client_id}).scalar()
    if not ib_id:
        return {"totals": {"trades": 0, "lots": 0, "commission": 0},
                "filters": {"countries": [], "cities": [], "account_types": [], "platforms": []},
                "trades": [], "page": page}
    p_from, p_to = period_dates(period, date_from, date_to)
    where = ["t.ib_id = :ib", "t.close_time::date BETWEEN CAST(:pf AS DATE) AND CAST(:pt AS DATE)"]
    params = {"ib": ib_id, "pf": p_from, "pt": p_to}
    if client_login: where.append("t.login = :cl"); params["cl"] = client_login
    if country:      where.append("t.country = :co"); params["co"] = country
    if city:         where.append("t.city = :ci"); params["ci"] = city
    if platform:     where.append("t.platform = :pl"); params["pl"] = platform
    if account_type: where.append("t.account_type = :at"); params["at"] = account_type
    if view == "eligible":  where.append("t.eligible = TRUE")
    elif view == "short":   where.append("t.eligible = FALSE AND t.reason LIKE 'short%'")
    elif view == "credit":  where.append("t.reason = 'credit'")
    w = " AND ".join(where)
    tot = db.execute(text(f"""SELECT COUNT(*), COALESCE(SUM(lots),0), COALESCE(SUM(commission),0),
                              COALESCE(SUM(profit),0), COALESCE(SUM(lots*comm_per_lot),0)
                              FROM ib_trades t WHERE {w}"""), params).fetchone()
    rows = db.execute(text(f"""
        SELECT login, client_name, country, city, platform, account_type, symbol, direction,
               open_time, close_time, hold_sec, lots, open_price, close_price, profit, commission, eligible, reason,
               deal_id
        FROM ib_trades t WHERE {w} ORDER BY close_time DESC NULLS LAST LIMIT :lim OFFSET :off
    """), {**params, "lim": page_size, "off": (page - 1) * page_size}).fetchall()
    opts = db.execute(text("""SELECT
        ARRAY(SELECT DISTINCT country FROM ib_trades WHERE ib_id=:ib AND COALESCE(country,'')<>'' ORDER BY 1),
        ARRAY(SELECT DISTINCT city FROM ib_trades WHERE ib_id=:ib AND COALESCE(city,'')<>'' ORDER BY 1),
        ARRAY(SELECT DISTINCT account_type FROM ib_trades WHERE ib_id=:ib ORDER BY 1),
        ARRAY(SELECT DISTINCT platform FROM ib_trades WHERE ib_id=:ib ORDER BY 1)
    """), {"ib": ib_id}).fetchone()
    return {
        # IB portal must NOT expose client P&L — IBs should not see whether their clients win or
        # lose. Profit is intentionally omitted from both the totals and the per-trade rows below.
        "totals": {"trades": tot[0], "lots": float(tot[1] or 0), "commission": float(tot[2] or 0),
                   "potential": float(tot[4] or 0)},
        "filters": {"countries": list(opts[0] or []), "cities": list(opts[1] or []),
                    "account_types": list(opts[2] or []), "platforms": list(opts[3] or [])},
        "page": page,
        "trades": [{
            "deal_id": r[18],
            "login": r[0], "client": r[1], "country": r[2], "city": r[3], "platform": r[4],
            "account_type": r[5], "symbol": r[6], "direction": r[7],
            "open_time": str(r[8]) if r[8] else None, "close_time": str(r[9]) if r[9] else None,
            "hold_min": round(r[10] / 60.0, 1) if r[10] is not None else None,
            "lots": float(r[11] or 0),
            "commission": float(r[15] or 0),
            "eligible": r[16], "reason": r[17],
        } for r in rows],
    }


# ───────────────────────── DEPOSIT / WITHDRAW (SIMULATION) ─────────────────────────
@router.post("/deposit")
def deposit(payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    """SIMULATION MODE — records request, no real payment gateway yet."""
    amount = float(payload.get("amount") or 0)
    method = (payload.get("method") or "").strip()
    login = payload.get("login")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    _assert_owns_login(db, client_id, login)
    _assert_not_archived(db, login)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS portal_money_requests (
            id SERIAL PRIMARY KEY, client_id INT, login BIGINT, kind VARCHAR(12),
            amount NUMERIC, method VARCHAR(40), status VARCHAR(24) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    rid = db.execute(text("""
        INSERT INTO portal_money_requests (client_id, login, kind, amount, method, status)
        VALUES (:c,:l,'deposit',:a,:m,'pending_simulation') RETURNING id
    """), {"c": client_id, "l": login, "a": amount, "m": method}).scalar()
    db.commit()
    # auto-credit any deposit bonus (simulation — writes clients.credit + bonus_grants)
    bonus = {"bonus": 0.0}
    try:
        bonus = BE.credit_deposit_bonus(db, client_id, login, amount, deposit_request_id=rid)
    except Exception:
        db.rollback()
    msg = f"Deposit request for ${amount:,.2f} recorded (simulation — no real charge)."
    if bonus.get("bonus", 0) > 0:
        msg += f" Bonus of ${bonus['bonus']:,.2f} credited to your account."
    return {"ok": True, "simulation": True, "bonus": bonus.get("bonus", 0), "message": msg}


@router.post("/withdraw")
def withdraw(payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    """SIMULATION MODE — records request to admin queue, no real payout yet."""
    amount = float(payload.get("amount") or 0)
    method = (payload.get("method") or "").strip()
    login = payload.get("login")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    _assert_owns_login(db, client_id, login)
    _assert_not_archived(db, login)   # archived accounts are read-only — no withdrawals
    # GUARD: min-withdrawal rule + margin-level (150%) check on open trades
    try:
        chk = BE.withdraw_check(db, client_id, amount)
    except Exception:
        db.rollback()
        chk = {"ok": True, "clawback": 0.0}
    if not chk.get("ok"):
        raise HTTPException(status_code=400, detail=chk.get("reason", "Withdrawal not allowed"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS portal_money_requests (
            id SERIAL PRIMARY KEY, client_id INT, login BIGINT, kind VARCHAR(12),
            amount NUMERIC, method VARCHAR(40), status VARCHAR(24) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("""
        INSERT INTO portal_money_requests (client_id, login, kind, amount, method, status)
        VALUES (:c,:l,'withdraw',:a,:m,'pending_admin_review')
    """), {"c": client_id, "l": login, "a": amount, "m": method})
    db.commit()
    # proportional bonus clawback: withdrawing X% of balance removes X% of bonus credit
    claw = {"clawback": 0.0}
    try:
        claw = BE.apply_withdraw_clawback(db, client_id, amount)
    except Exception:
        db.rollback()
    msg = f"Withdrawal request for ${amount:,.2f} submitted for admin review (simulation)."
    if claw.get("clawback", 0) > 0:
        msg += f" ${claw['clawback']:,.2f} of bonus was deducted proportionally."
    return {"ok": True, "simulation": True, "clawback": claw.get("clawback", 0), "message": msg}


@router.get("/money-requests")
def money_requests(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT id, login, kind, amount, method, status, created_at
            FROM portal_money_requests WHERE client_id=:id ORDER BY id DESC LIMIT 50
        """), {"id": client_id}).fetchall()
    except Exception:
        return {"requests": []}
    return {"requests": [{
        "id": r[0], "login": r[1], "kind": r[2], "amount": float(r[3] or 0),
        "method": r[4] or "", "status": r[5], "date": str(r[6])[:16] if r[6] else None,
        "cancellable": (r[2] == 'withdraw' and str(r[5]).lower() in ('pending', 'pending_admin_review')),
    } for r in rows]}


@router.get("/transactions")
def transactions_history(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """The client's FULL money history: real deposits/withdrawals/transfers/bonus from the transactions
    ledger (the source of truth — built from MT5 deals + the MT4 journal), PLUS any still-pending requests
    they submitted. Newest first, with totals. Same data the AI chat reads."""
    logins = _client_logins(db, client_id)
    out = []
    if logins:
        try:
            rows = db.execute(text("""
                SELECT tx_type, amount, tx_date, COALESCE(status,'completed'), COALESCE(method,''), login
                FROM transactions
                WHERE login = ANY(:l)
                  AND tx_type IN ('deposit','withdrawal','internal_transfer','bonus_deposit','bonus_withdrawal')
                ORDER BY tx_date DESC NULLS LAST LIMIT 300
            """), {"l": logins}).fetchall()
            for tt, amt, dt, st, meth, lg in rows:
                out.append({"type": tt, "amount": float(amt or 0), "date": str(dt) if dt else None,
                            "status": st, "method": meth, "login": lg, "pending": False})
        except Exception:
            db.rollback()
    # pending requests the client submitted (deposit/withdraw not yet completed) — shown on top
    pend = []
    try:
        preq = db.execute(text("""
            SELECT kind, amount, COALESCE(method,''), COALESCE(status,'pending'), created_at, login
            FROM portal_money_requests
            WHERE client_id=:id
              AND LOWER(COALESCE(status,'')) NOT IN ('approved','completed','done','success','succeeded','rejected','cancelled','failed')
            ORDER BY id DESC LIMIT 50
        """), {"id": client_id}).fetchall()
        for kind, amt, meth, st, dt, lg in preq:
            pend.append({"type": ("deposit" if "depos" in (kind or "").lower() else "withdrawal"),
                         "amount": float(amt or 0), "date": str(dt) if dt else None,
                         "status": st, "method": meth, "login": lg, "pending": True})
    except Exception:
        db.rollback()
    dep = sum(t["amount"] for t in out if t["type"] == "deposit")
    wd = sum(t["amount"] for t in out if t["type"] == "withdrawal")
    return {"transactions": pend + out,
            "totals": {"deposits": round(dep, 2), "withdrawals": round(wd, 2), "net": round(dep - wd, 2),
                       "pending": len(pend)}}


@router.post("/money-requests/{req_id}/cancel")
def cancel_money_request(req_id: int, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """#3 — client cancels their OWN still-pending withdrawal from the dashboard."""
    row = db.execute(text("SELECT status, kind FROM portal_money_requests WHERE id=:i AND client_id=:c"),
                     {"i": req_id, "c": client_id}).fetchone()
    if not row:
        return {"ok": False, "error": "Request not found"}
    if row[1] != "withdraw":
        return {"ok": False, "error": "Only withdrawals can be cancelled"}
    if str(row[0]).lower() not in ("pending", "pending_admin_review"):
        return {"ok": False, "error": "This withdrawal can no longer be cancelled (already processed)."}
    db.execute(text("UPDATE portal_money_requests SET status='cancelled' WHERE id=:i AND client_id=:c"),
               {"i": req_id, "c": client_id})
    db.commit()
    return {"ok": True, "status": "cancelled"}


# ───────────────────────── LOYALTY (client-scoped) ─────────────────────────
@router.get("/loyalty")
def portal_loyalty(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    a = db.execute(text("""
        SELECT la.client_id, c.name, la.tier, la.points_balance, la.lifetime_points,
               la.current_streak, la.best_streak, la.last_trade_date, la.referral_code, la.best_tier,
               la.pass_tokens
        FROM loyalty_accounts la LEFT JOIN clients c ON c.id=la.client_id
        WHERE la.client_id=:id
    """), {"id": client_id}).fetchone()
    if not a:
        return {"error": "not_enrolled"}
    RATES = {"bronze": 4, "silver": 5, "gold": 6, "platinum": 7}
    NEXT = {"bronze": "silver", "silver": "gold", "gold": "platinum", "platinum": None}
    PROMO = {"bronze": 30, "silver": 30, "gold": 40}
    tier = a[2] or "bronze"
    streak = a[5] or 0
    promo_need = PROMO.get(tier)
    ledger = db.execute(text("""
        SELECT trade_date, symbol, lots, tier, points, kind
        FROM loyalty_ledger WHERE client_id=:id ORDER BY trade_date DESC, id DESC LIMIT 60
    """), {"id": client_id}).fetchall()
    return {
        "client_id": a[0], "name": a[1] or f"Client #{a[0]}",
        "tier": tier, "tier_rate": RATES.get(tier, 4),
        "best_tier": a[9] or tier,
        "points_balance": float(a[3] or 0), "lifetime_points": float(a[4] or 0),
        "current_streak": streak, "best_streak": a[6] or 0,
        "pass_tokens": a[10] if len(a) > 10 and a[10] is not None else 0,
        "next_tier": NEXT.get(tier),
        "promo_streak_needed": promo_need,
        "streak_to_promotion": max(0, (promo_need - streak)) if promo_need else 0,
        "last_trade_date": str(a[7]) if a[7] else None,
        "referral_code": a[8] or "",
        "ledger": [{"date": str(l[0]), "symbol": l[1], "lots": float(l[2] or 0),
                    "tier": l[3], "points": float(l[4] or 0), "kind": l[5]} for l in ledger],
    }


@router.get("/loyalty/rewards")
def portal_rewards(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT id, name, description, cost_points FROM loyalty_rewards
        ORDER BY cost_points ASC
    """)).fetchall()
    return {"rewards": [{"id": r[0], "name": r[1], "description": r[2] or "",
                         "cost_points": float(r[3] or 0)} for r in rows]}


@router.get("/loyalty/referrals")
def portal_referrals(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT id, referred_name, referred_phone, referred_login, bonus_points, status, created_at
        FROM loyalty_referrals WHERE referrer_client_id=:id ORDER BY id DESC LIMIT 50
    """), {"id": client_id}).fetchall()
    won = sum(1 for r in rows if r[5] == "won")
    pend = ("invited", "pending", "pending_admin_review", "registered", "verified", "funded")
    pending = sum(1 for r in rows if r[5] in pend)
    return {"summary": {"total": len(rows), "won": won, "pending": pending,
                        "points_earned": sum(float(r[4] or 0) for r in rows if r[5] == "won")},
            "invites": [{"id": r[0], "name": r[1] or chr(8212), "phone": r[2] or "",
                         "login": r[3], "bonus": float(r[4] or 0), "status": r[5],
                         "date": str(r[6])[:10] if r[6] else None} for r in rows]}


@router.post("/loyalty/redeem")
def portal_redeem(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    reward_id = payload.get("reward_id")
    rw = db.execute(text("SELECT name, cost_points FROM loyalty_rewards WHERE id=:r"),
                    {"r": reward_id}).fetchone()
    if not rw:
        raise HTTPException(status_code=404, detail="Reward not found")
    acc = db.execute(text("SELECT points_balance FROM loyalty_accounts WHERE client_id=:c"),
                     {"c": client_id}).fetchone()
    bal = float(acc[0]) if acc else 0
    cost = float(rw[1] or 0)
    if bal < cost:
        return {"error": "insufficient points", "needed": cost, "balance": bal}
    db.execute(text("UPDATE loyalty_accounts SET points_balance=points_balance-:c, updated_at=NOW() WHERE client_id=:cid"),
               {"c": cost, "cid": client_id})
    db.execute(text("""INSERT INTO loyalty_redemptions (client_id, reward_id, cost_points, status)
                       VALUES (:c,:r,:p,'pending')"""),
               {"c": client_id, "r": reward_id, "p": cost})
    db.commit()
    return {"ok": True, "reward": rw[0], "new_balance": bal - cost}


@router.post("/loyalty/referral")
def portal_referral(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    name = payload.get("referred_name", "")
    phone = payload.get("referred_phone", "")
    bonus = float(payload.get("bonus_points", 100))
    try:
        db.execute(text("ALTER TABLE loyalty_referrals ADD COLUMN IF NOT EXISTS referred_name VARCHAR(120)"))
        db.execute(text("ALTER TABLE loyalty_referrals ADD COLUMN IF NOT EXISTS referred_phone VARCHAR(40)"))
        db.commit()
    except Exception:
        db.rollback()
    db.execute(text("""INSERT INTO loyalty_referrals
                       (referrer_client_id, referred_login, referred_name, referred_phone, bonus_points, status)
                       VALUES (:r,0,:n,:p,:b,'invited')"""),
               {"r": client_id, "n": name, "p": phone, "b": bonus})
    db.commit()
    return {"ok": True, "message": "Invite recorded", "bonus_points": bonus}


# ───────────────────────── DASHBOARD (client-scoped KPIs) ─────────────────────────
@router.get("/dashboard")
def portal_dashboard(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    # profile
    prof = db.execute(text("""
        SELECT id, name, email, phone, city, country FROM clients WHERE id=:id LIMIT 1
    """), {"id": client_id}).fetchone()

    # all logins that belong to this client (link is by login, not the NULL client_id)
    logins = _client_logins(db, client_id)

    # balances across accounts. Prefer the `clients` table per login (it carries balance + equity + credit,
    # kept current by the sync/deposit/credit flows) and only fall back to trading_accounts for a login that
    # has no clients row. (trading_accounts.balance can lag — e.g. a stale negative pre-deposit snapshot — and
    # its equity is often NULL.)
    bal = db.execute(text("""
        WITH acct AS (
            SELECT unnest(CAST(:logins AS bigint[])) AS login
        )
        SELECT
            COALESCE(SUM(COALESCE(c.balance, ta.balance, 0)), 0)                                   AS balance,
            COALESCE(SUM(COALESCE(NULLIF(c.equity,0), c.balance, NULLIF(ta.equity,0), ta.balance, 0)), 0) AS equity,
            COALESCE(SUM(COALESCE(c.credit, ta.credit, 0)), 0)                                     AS credit,
            COUNT(*)                                                                               AS n
        FROM acct a
        LEFT JOIN LATERAL (SELECT balance, equity, credit FROM clients          WHERE login=a.login LIMIT 1) c  ON TRUE
        LEFT JOIN LATERAL (SELECT balance, equity, credit FROM trading_accounts WHERE login=a.login LIMIT 1) ta ON TRUE
    """), {"logins": logins or [0]}).fetchone()
    total_balance = float(bal[0] or 0)
    total_equity = float(bal[1] or 0)
    total_credit = float(bal[2] or 0)
    n_accounts = int(bal[3] or 0)

    # loyalty
    loy = db.execute(text("""
        SELECT tier, points_balance, lifetime_points, current_streak, best_tier
        FROM loyalty_accounts WHERE client_id=:id
    """), {"id": client_id}).fetchone()

    # trades in last 30 days + open P/L proxy (sum profit of recent closed) + win rate
    import time as _t
    cutoff = int(_t.time()) - 30 * 86400
    tr = db.execute(text("""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN d.profit > 0 THEN 1 ELSE 0 END),0),
               COALESCE(SUM(d.profit),0)
        FROM deals d
        WHERE d.login = ANY(:logins) AND d.entry=1 AND d.action IN (0,1) AND d.deal_time>=:cut
    """), {"logins": logins or [0], "cut": cutoff}).fetchone()
    trades_30 = int(tr[0] or 0)
    wins_30 = int(tr[1] or 0)
    pnl_30 = float(tr[2] or 0)
    win_rate = round((wins_30 / trades_30 * 100), 1) if trades_30 else 0.0

    # deposits (from portal money requests, simulation) — best-effort
    deposits = 0.0
    try:
        dep = db.execute(text("""
            SELECT COALESCE(SUM(amount),0) FROM portal_money_requests
            WHERE client_id=:id AND kind='deposit'
        """), {"id": client_id}).fetchone()
        deposits = float(dep[0] or 0)
    except Exception:
        db.rollback()  # a failed query aborts the txn; recover so later queries don't 500
        deposits = 0.0

    # sales / referral performance (the big KPI)
    refs = db.execute(text("""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN status='won' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN status='won' THEN bonus_points ELSE 0 END),0)
        FROM loyalty_referrals WHERE referrer_client_id=:id
    """), {"id": client_id}).fetchone()
    inv_total = int(refs[0] or 0)
    inv_won = int(refs[1] or 0)
    inv_points = float(refs[2] or 0)

    return {
        "profile": {
            "client_id": prof[0] if prof else client_id,
            "name": (prof[1] if prof else None) or f"Client #{client_id}",
            "email": (prof[2] if prof else "") or "",
            "phone": (prof[3] if prof else "") or "",
            "city": (prof[4] if prof else "") or "",
            "country": (prof[5] if prof else "") or "",
        },
        "kpis": {
            "balance": total_balance,
            "accounts": n_accounts,
            "equity": total_equity,   # real equity from clients (falls back to balance when not synced)
            "credit": total_credit,   # bonus/credit on the account(s)
            "open_pl": pnl_30,        # 30d realized P/L as proxy
            "deposits": deposits,
            "trades_30": trades_30,
            "win_rate": win_rate,
            "loyalty_points": float(loy[1]) if loy else 0,
            "loyalty_tier": (loy[0] if loy else "bronze"),
            "loyalty_streak": (loy[3] if loy else 0),
        },
        "sales": {
            "invites": inv_total,
            "won": inv_won,
            "pending": inv_total - inv_won,
            "points_earned": inv_points,
            "referral_code": None,  # filled from loyalty if needed
        },
    }


# ───────────────────────── NEW ACCOUNT REQUEST (safe: admin queue) ─────────────────────────
@router.post("/accounts/request")
def request_account(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """Submit a new-account request to the admin queue (no live provisioning here)."""
    platform = (payload.get("platform") or "").upper()      # MT4 / MT5
    acc_type = (payload.get("account_type") or "").strip()  # Standard/Zero/Cent/VIP
    leverage = payload.get("leverage")
    islamic = bool(payload.get("islamic", False))
    if platform not in ("MT4", "MT5"):
        raise HTTPException(status_code=400, detail="Platform must be MT4 or MT5")
    if acc_type not in ("Standard", "Zero", "Cent", "VIP"):
        raise HTTPException(status_code=400, detail="Invalid account type")
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS portal_account_requests (
            id SERIAL PRIMARY KEY, client_id INT, platform VARCHAR(8),
            account_type VARCHAR(20), leverage INT, islamic BOOLEAN,
            status VARCHAR(24) DEFAULT 'pending_admin_review', created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("""
        INSERT INTO portal_account_requests (client_id, platform, account_type, leverage, islamic)
        VALUES (:c,:p,:t,:l,:i)
    """), {"c": client_id, "p": platform, "t": acc_type, "l": int(leverage or 0), "i": islamic})
    db.commit()
    return {"ok": True, "message": f"{platform} {acc_type}{' (Islamic)' if islamic else ''} account requested. Our team will set it up shortly."}


@router.get("/accounts/requests")
def list_account_requests(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT id, platform, account_type, leverage, islamic, status, created_at
            FROM portal_account_requests WHERE client_id=:id ORDER BY id DESC LIMIT 30
        """), {"id": client_id}).fetchall()
    except Exception:
        return {"requests": []}
    return {"requests": [{
        "id": r[0], "platform": r[1], "account_type": r[2], "leverage": r[3],
        "islamic": bool(r[4]), "status": r[5], "date": str(r[6])[:16] if r[6] else None,
    } for r in rows]}


# ───────────────────────── TRANSFER (between own accounts, simulation) ─────────────────────────
@router.post("/transfer")
def transfer(payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    """Internal transfer between the client's own accounts (simulation/admin-review)."""
    from_login = payload.get("from_login")
    to_login = payload.get("to_login")
    amount = float(payload.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if not from_login or not to_login or from_login == to_login:
        raise HTTPException(status_code=400, detail="Choose two different accounts")
    # verify both logins belong to this client (link is by login, not the NULL client_id)
    owned_set = {str(l) for l in _client_logins(db, client_id)}
    if str(from_login) not in owned_set or str(to_login) not in owned_set:
        raise HTTPException(status_code=403, detail="Both accounts must be yours")
    # archived accounts can't send OR receive internal transfers
    _assert_not_archived(db, from_login)
    _assert_not_archived(db, to_login)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS portal_transfers (
            id SERIAL PRIMARY KEY, client_id INT, from_login BIGINT, to_login BIGINT,
            amount NUMERIC, status VARCHAR(24) DEFAULT 'pending_simulation', created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("""
        INSERT INTO portal_transfers (client_id, from_login, to_login, amount)
        VALUES (:c,:f,:t,:a)
    """), {"c": client_id, "f": from_login, "t": to_login, "a": amount})
    db.commit()
    return {"ok": True, "simulation": True,
            "message": f"Transfer of ${amount:,.2f} from #{from_login} to #{to_login} recorded (simulation)."}


# ═══════════════════════ PORTAL v2: manager, wizards, KYC ═══════════════════════
import random, string

# ---------- SALES MANAGER (for the 1x2 dashboard card) ----------
@router.get("/manager")
def portal_manager(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT u.full_name, u.phone, u.email, u.avatar_url, u.role, u.extension
        FROM clients c JOIN users u ON u.id = c.assigned_agent_id
        WHERE c.id = :id
    """), {"id": client_id}).fetchone()
    if not row:
        return {"manager": None}
    phone = (row[1] or "").strip()
    wa = "".join(ch for ch in phone if ch.isdigit())
    return {"manager": {
        "name": row[0] or "Your account manager",
        "phone": phone,
        "whatsapp": f"https://wa.me/{wa}" if wa else None,
        "email": row[2] or "",
        "avatar_url": row[3] or "",
        "role": (row[4] or "account manager").replace("_", " ").title(),
        "extension": row[5] or "",
    }}


# ---------- KYC STATUS / UPLOAD (uses real clients.kyc_status) ----------
def _client_reg(db, client_id):
    """Resolve the client's KYC registration by a STABLE key. During provisioning the client's
    login is promoted from a negative temp value (e.g. -1000039) to a real MT5 number, and the
    registration's mt_login/account_login lag behind for a few seconds — so a login-ONLY match
    drops the documents mid-process (the "KPI approved but no docs/account" symptom). Matching on
    account_login OR mt_login OR email keeps docs + status stable before, during and after verify."""
    c = db.execute(text("SELECT login, lower(email) AS em FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    if not c:
        return None
    try:
        return db.execute(text("""
            SELECT id, mt_login, account_login, verify_status, status, verify_reason,
                   ocr_fields, id_number, address, network_json
            FROM registrations
            WHERE (:lg IS NOT NULL AND (mt_login=:lg OR account_login=:lg))
               OR (:em IS NOT NULL AND :em <> '' AND lower(email)=:em)
            ORDER BY id DESC LIMIT 1
        """), {"lg": c.login, "em": c.em or ""}).fetchone()
    except Exception:
        db.rollback()
        return None


def _kyc_reason(db, login):
    """Plain-language reason for the current KYC verdict (from the registration). Guarded:
    the verify_reason column is created by the KYC engine, so tolerate it not existing yet."""
    if login is None:
        return None
    try:
        return db.execute(text(
            "SELECT verify_reason FROM registrations WHERE mt_login=:lg ORDER BY id DESC LIMIT 1"
        ), {"lg": login}).scalar()
    except Exception:
        db.rollback()
        return None


@router.get("/kyc/status")
def kyc_status(background: BackgroundTasks, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    row = db.execute(text("SELECT login, kyc_status FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    login = row[0] if row else None
    status = (row[1] if row else None) or "not_submitted"
    # SELF-HEAL: if the client uploaded documents (e.g. from the phone via QR) but the AI never
    # processed them (registration has docs but no verify_status), kick off processing now and
    # show "under review" — so the dashboard never disagrees with the documents in the profile.
    reg = _client_reg(db, client_id)
    if login is not None and status not in ("verified", "rejected", "exists", "docs_needed"):
        try:
            if reg:
                ndocs = db.execute(text("SELECT COUNT(*) FROM reg_kyc_documents WHERE registration_id=:r"),
                                   {"r": reg.id}).scalar()
                if (ndocs or 0) > 0 and (reg.verify_status or "") in ("", "pending"):
                    from registration_router import _process_kyc_bg
                    background.add_task(_process_kyc_bg, reg.id)
                    db.execute(text("UPDATE clients SET kyc_status='pending_review' WHERE id=:id AND kyc_status IS DISTINCT FROM 'verified'"),
                               {"id": client_id})
                    db.commit()
                    status = "pending_review"
        except Exception:
            db.rollback()
    # SAFETY NET: verdict is 'verified' but the trading account never got provisioned (rare hard
    # failure during on_verified) -> KPI would sit on "finalizing" forever. Re-run provisioning
    # (idempotent via registrations.account_login) so it always converges to a real account.
    if reg and (reg.verify_status or "") == "verified" and not reg.account_login:
        try:
            import kyc_postverify
            kyc_postverify.on_verified(db, reg.id)
            r2 = db.execute(text("SELECT kyc_status FROM clients WHERE id=:id"), {"id": client_id}).scalar()
            status = r2 or status
        except Exception:
            db.rollback()
    reason = (reg.verify_reason if reg else None) if status != "verified" else None
    existing_account = None
    if status == "exists" and reg is not None:
        try:
            nj = reg.network_json
            if isinstance(nj, dict):
                ea = nj.get("existing_account")
                if ea:   # client only sees MASKED contact, never the full email/phone
                    existing_account = {"email_masked": ea.get("email_masked"), "phone_masked": ea.get("phone_masked")}
        except Exception:
            db.rollback()
    # POA-in-another-name: tell the portal to show the "upload your husband/wife ID" control.
    need_family_id = False
    poa_holder = None
    id_approved = False
    try:
        nj = reg.network_json if reg else None
        if isinstance(nj, dict):
            poa = nj.get("poa") or {}
            if poa.get("verdict") == "need_family_id":
                need_family_id = True
                poa_holder = poa.get("holder_name")
        # has the ID itself been approved yet? (so the portal can show a GREEN "ID approved" KPI on
        # top, and a SEPARATE card below for whatever is still missing). During the brief AI review
        # the ID doc is still 'uploaded'/'review', so this stays False and the top KPI says "reviewing".
        if reg:
            ids = db.execute(text("SELECT status FROM reg_kyc_documents WHERE registration_id=:r AND side IN ('front','main')"),
                             {"r": reg.id}).fetchall()
            id_approved = bool(ids) and all((x[0] or "") == "approved" for x in ids)
    except Exception:
        db.rollback()
    return {"status": status, "verified": status == "verified", "reason": reason,
            "existing_account": existing_account,
            "need_family_id": need_family_id, "poa_holder": poa_holder, "id_approved": id_approved}


@router.get("/kyc/documents")
def kyc_documents(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """The client's uploaded KYC documents + the per-document review status (and expiry once
    approved). Documents are uploaded at registration into reg_kyc_documents, keyed to the
    registration whose mt_login == this client's login."""
    login = db.execute(text("SELECT login FROM clients WHERE id=:id"), {"id": client_id}).scalar()
    reg = _client_reg(db, client_id)   # stable resolver (login flips during provisioning)

    # overall verification status -> the label each document carries
    OVERALL = {"verified": "approved", "review": "under_review", "pending": "under_review",
               "pending_review": "under_review", "under_review": "under_review",
               "docs_needed": "docs_needed", "rejected": "rejected", "pending_kyc": "not_submitted"}
    # per-document raw status -> display status
    DOC_MAP = {"approved": "approved", "rejected": "rejected", "review": "under_review",
               "uploaded": "under_review", "read": "under_review", "needs_upload": "not_submitted"}
    overall = "not_submitted"
    expiry = None
    docs = []
    if reg:
        overall = OVERALL.get(((reg.verify_status or reg.status) or "").lower(), "under_review")
        ocr = reg.ocr_fields if isinstance(reg.ocr_fields, dict) else {}
        expiry = (ocr or {}).get("expiry_date") or None
        LABEL = {"front": "ID — front", "back": "ID — back", "main": "Passport photo page",
                 "selfie": "Selfie", "proof_of_address": "Proof of residence",
                 "proof_of_address_back": "Proof of residence — back",
                 "family_id_front": "Family member's ID — front",
                 "family_id_back": "Family member's ID — back"}
        rows = db.execute(text("""
            SELECT doc_type, side, status FROM reg_kyc_documents WHERE registration_id=:r ORDER BY id
        """), {"r": reg.id}).fetchall()
        for d in rows:
            dstatus = DOC_MAP.get((d.status or "").lower(), overall if overall in ("approved", "rejected", "under_review") else "under_review")
            docs.append({
                "doc_type": d.doc_type, "side": d.side,
                "label": LABEL.get(d.side, d.side),
                "status": dstatus,
                "expiry_date": expiry if dstatus == "approved" else None,
            })
    reason = (reg.verify_reason if reg else None) if overall != "approved" else None
    id_number = (reg.id_number if reg else None) or ((reg.ocr_fields or {}).get("id_number") if reg and isinstance(reg.ocr_fields, dict) else None)
    address = (reg.address if reg else None)
    return {"overall": overall, "expiry_date": expiry if overall == "approved" else None,
            "reason": reason, "id_number": id_number, "address": address, "documents": docs}


def _get_or_create_registration(db, client_id):
    """The client's registration row (KYC lives there). Create a minimal one if the client has
    none (e.g. an imported client uploading via the portal), so portal KYC has a home."""
    c = db.execute(text("SELECT login, name, email, phone, country, city FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    if not c or c[0] is None:
        return None
    login = c[0]
    reg = _client_reg(db, client_id)   # stable resolver — never make a duplicate reg post-promotion
    if reg:
        return reg.id
    parts = (c[1] or "").strip().split(" ", 1)
    fn, ln = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    try:
        rid = db.execute(text("""
            INSERT INTO registrations (first_name,last_name,email,phone,country,city,status,mt_login,created_at)
            VALUES (:fn,:ln,:e,:p,:co,:ci,'pending_kyc',:lg,NOW()) RETURNING id
        """), {"fn": fn, "ln": ln, "e": c[2], "p": c[3], "co": c[4], "ci": c[5], "lg": login}).scalar()
        db.commit()
        return rid
    except Exception:
        db.rollback()
        return None


def _save_kyc_image(db, rid, doc_type, side, image_b64, ocr_json=None):
    """Persist an uploaded portal KYC image into reg_kyc_documents (one row per side) so it shows
    in the profile + admin console and the AI engine can read it."""
    import base64, os, json as _json
    from registration_router import KYC_DIR
    try:
        raw = (image_b64 or "").split(",")[-1]
        data = base64.b64decode(raw + "=" * (-len(raw) % 4))
        ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        path = os.path.join(KYC_DIR, f"reg{rid}_{doc_type}_{side}{ext}")
        with open(path, "wb") as f:
            f.write(data)
        db.execute(text("DELETE FROM reg_kyc_documents WHERE registration_id=:r AND side=:s"), {"r": rid, "s": side})
        db.execute(text("""
            INSERT INTO reg_kyc_documents (registration_id, doc_type, side, file_path, ocr_json, status)
            VALUES (:r,:dt,:s,:p,CAST(:j AS JSONB),'uploaded')
        """), {"r": rid, "dt": doc_type, "s": side, "p": path, "j": _json.dumps(ocr_json or {})})
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"[portal-kyc] save image failed: {e}", flush=True)
        return False


@router.post("/kyc/upload")
def kyc_upload(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """Pre-fill the KYC review form by reading the uploaded ID image with a REAL vision OCR
    (Claude, ai_config.CHAT_MODEL). Ticket #25: the portal now sends the ACTUAL image bytes
    (base64) in `image`; we decode (capped at 7MB, data: prefix stripped) and extract ONLY the
    fields actually visible on the document — the model returns "" for anything not present, so
    we NEVER fabricate an ID number or any other value.

    If no image is sent (older client / image read failed), fall back to seeding the client's own
    known profile details and leaving every document-specific field BLANK for the client to type.
    PII / image bytes are never logged."""
    doc_type = payload.get("doc_type", "national_id")  # national_id | passport | drivers_license
    prof = db.execute(text("""
        SELECT name, date_of_birth, nationality, country FROM clients WHERE id=:id
    """), {"id": client_id}).fetchone()
    name = (prof[0] if prof else "") or ""
    dob = str(prof[1]) if prof and prof[1] else ""
    nationality = (prof[2] if prof else "") or (prof[3] if prof else "") or ""

    # Start from a fully-BLANK document shape — never seed an ID number.
    extracted = {
        "document_type": doc_type,
        "full_name": "",
        "id_number": "",
        "father_name": "",
        "mother_name": "",
        "date_of_birth": "",
        "place_of_birth": "",
        "nationality": "",
        "gender": "",
        "issue_date": "",
        "expiry_date": "",
    }

    image_b64 = payload.get("image") or payload.get("image_b64")
    ocr_status = "no_image"
    if image_b64:
        try:
            import kyc_ai
            fields = kyc_ai.extract_id_fields_from_b64(image_b64, doc_type) or {}
        except Exception:
            fields = {"_status": "error"}
        st = fields.get("_status")
        if st:
            # OCR could not read the doc (no key / bad image / too large / model error).
            # Do NOT fabricate — return blanks pre-seeded with the client's own profile and a note.
            ocr_status = st
        else:
            ocr_status = "read"
            # copy ONLY the document fields the model actually returned; "" stays "" (never invented)
            for k in list(extracted.keys()):
                if k == "document_type":
                    continue
                v = fields.get(k)
                if isinstance(v, str):
                    extracted[k] = v.strip()
            # id_number: only a genuine non-empty value survives; placeholder/simulated flags drop it
            if fields.get("_simulated") or fields.get("_status") in ("simulated", "placeholder"):
                extracted["id_number"] = ""

    if ocr_status != "read":
        # fall back to the client's known profile for the convenience fields only — NEVER id_number
        if not extracted.get("full_name"):
            extracted["full_name"] = name
        if not extracted.get("date_of_birth"):
            extracted["date_of_birth"] = dob
        if not extracted.get("nationality"):
            extracted["nationality"] = nationality
        extracted["_note"] = ("We couldn't read the document automatically. Please enter the details "
                              "exactly as they appear on your document, then submit.")

    # persist the uploaded image(s) so they appear in the profile + admin console and the AI can read them
    rid = _get_or_create_registration(db, client_id)
    if rid:
        if image_b64:
            _save_kyc_image(db, rid, doc_type, "front", image_b64, extracted)
        if payload.get("image_back"):
            _save_kyc_image(db, rid, doc_type, "back", payload.get("image_back"))
        if payload.get("image_poa"):
            _save_kyc_image(db, rid, "proof_of_address", "proof_of_address", payload.get("image_poa"))
        # family-member ID (the person named on a proof of address that isn't in the client's own
        # name) — used to confirm the household via the shared Family ID on the back of the card.
        if payload.get("image_family_id_front"):
            _save_kyc_image(db, rid, "family_id", "family_id_front", payload.get("image_family_id_front"))
        if payload.get("image_family_id_back"):
            _save_kyc_image(db, rid, "family_id", "family_id_back", payload.get("image_family_id_back"))

    return {"ok": True, "ocr_status": ocr_status, "extracted": extracted}


@router.post("/kyc/submit")
def kyc_submit(payload: dict, background: BackgroundTasks, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS portal_kyc_submissions (
                id SERIAL PRIMARY KEY, client_id INT, doc_type VARCHAR(24),
                fields JSONB, status VARCHAR(24) DEFAULT 'pending_review', created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.commit()
    except Exception:
        db.rollback()
    import json as _json
    db.execute(text("""
        INSERT INTO portal_kyc_submissions (client_id, doc_type, fields, status)
        VALUES (:c,:d,CAST(:f AS JSONB),'pending_review')
    """), {"c": client_id, "d": payload.get("document_type", "national_id"),
           "f": _json.dumps(payload.get("fields", {}))})
    db.commit()
    rid = _get_or_create_registration(db, client_id)
    if rid:
        try:
            from registration_router import _process_kyc_bg, set_immediate_docs_status
            # If a required doc (proof of address / ID back) is missing, ask for it in the KPI right
            # away; otherwise show "under review" while the AI checks the full set.
            if not set_immediate_docs_status(db, rid):
                db.execute(text("UPDATE clients SET kyc_status='pending_review' WHERE id=:id AND kyc_status IS DISTINCT FROM 'verified'"),
                           {"id": client_id})
                db.commit()
            background.add_task(_process_kyc_bg, rid)
        except Exception as e:
            print(f"[portal-kyc] could not queue AI review: {e}", flush=True)
    # uploading KYC is re-engagement -> a user-archived client comes back to the active list
    try:
        import reactivation
        reactivation.reactivate_client_logins(db, _client_logins(db, client_id), via="kyc")
    except Exception:
        db.rollback()
    return {"ok": True, "message": "Your documents were submitted for review. We'll notify you once verified."}


@router.post("/kyc/family-id")
def kyc_family_id(payload: dict, background: BackgroundTasks, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """Upload the ID of the family member named on a proof of address that isn't in the client's
    own name (husband/wife/parent). Saved as family_id_front/back, then KYC is re-run — if that
    person's Family ID matches the client's, the proof of address is accepted and the account is
    provisioned. Expects base64 images in image_family_id_front / image_family_id_back."""
    rid = _get_or_create_registration(db, client_id)
    if not rid:
        return {"ok": False, "error": "No registration on file."}
    saved = 0
    if payload.get("image_family_id_front"):
        _save_kyc_image(db, rid, "family_id", "family_id_front", payload.get("image_family_id_front")); saved += 1
    if payload.get("image_family_id_back"):
        _save_kyc_image(db, rid, "family_id", "family_id_back", payload.get("image_family_id_back")); saved += 1
    if not saved:
        return {"ok": False, "error": "Please attach the front and back of the family member's ID."}
    db.execute(text("UPDATE clients SET kyc_status='pending_review' WHERE id=:id AND kyc_status IS DISTINCT FROM 'verified'"),
               {"id": client_id})
    db.commit()
    try:
        from registration_router import _process_kyc_bg
        background.add_task(_process_kyc_bg, rid)
    except Exception as e:
        print(f"[portal-kyc] could not queue family-ID review: {e}", flush=True)
    return {"ok": True, "message": "Thank you — we're verifying the family member's ID against your record."}


# ---------- NEW ACCOUNT WIZARD (SIMULATED provisioning) ----------
@router.post("/accounts/{login}/password")
def account_set_password(login: int, payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    """Change the client's own trading-account MASTER or INVESTOR password on the MT5 server."""
    _assert_owns_login(db, client_id, login)
    pw = (payload.get("password") or "").strip()
    kind = (payload.get("kind") or "master").lower()
    if kind not in ("master", "investor"):
        return {"ok": False, "error": "kind must be master or investor"}
    if len(pw) < 8:
        return {"ok": False, "error": "Password must be at least 8 characters."}
    try:
        import mt_provision
        res = mt_provision.set_password(login, pw, kind)
    except Exception as e:
        res = {"ok": False, "error": str(e)}
    return {"ok": bool(res.get("ok")), "error": res.get("error"), "kind": kind}


@router.post("/accounts/{login}/leverage")
def account_set_leverage(login: int, payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    """Change the client's own trading-account leverage on the MT5 server."""
    _assert_owns_login(db, client_id, login)
    try:
        lev = int(payload.get("leverage") or 0)
    except Exception:
        lev = 0
    if lev <= 0:
        return {"ok": False, "error": "Invalid leverage."}
    try:
        import mt_provision
        res = mt_provision.set_leverage(login, lev)
    except Exception as e:
        res = {"ok": False, "error": str(e)}
    if res.get("ok"):
        try:
            db.execute(text("UPDATE trading_accounts SET leverage=:l WHERE login=:lg"), {"l": lev, "lg": login})
            db.commit()
        except Exception:
            db.rollback()
    return {"ok": bool(res.get("ok")), "error": res.get("error"), "leverage": lev}


@router.post("/accounts/create")
def create_account(payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    """Open an ADDITIONAL trading account — provisions a REAL MT5 account on the live server via the
    bridge (same path as KYC approval), no dummy logins. Inserts the matching clients + trading_accounts
    rows (sharing the client's phone) so it shows immediately in the portal cluster."""
    # Gate: a client must be KYC-verified before opening a new trading account.
    crow = db.execute(text("SELECT name, email, phone, country, city, agent, kyc_status, COALESCE(platform,'') FROM clients WHERE id=:id"),
                      {"id": client_id}).fetchone()
    if not crow or (crow[6] or "").lower() != "verified":
        return {"ok": False, "error": "kyc_required",
                "message": "Your account needs to be verified before you can open a new trading account. "
                           "Please complete your identity verification (KYC) first."}
    platform = (payload.get("platform") or "MT5").upper()
    acc_type = (payload.get("account_type") or "Standard").strip()
    leverage = int(payload.get("leverage") or 500)
    islamic = bool(payload.get("islamic", False))
    name = (crow[0] or "").strip()
    parts = name.split(" ", 1)
    first, last = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    email, phone, country, city = (crow[1] or ""), (crow[2] or ""), (crow[3] or ""), (crow[4] or "")
    try:
        agent = int(crow[5] or 0)
    except Exception:
        agent = 0
    # The portal groups a person's accounts by phone + platform (clients table). Use the SAME platform
    # value as the base client so the new account joins their cluster: registration sets 'MT5', legacy
    # imports leave it blank — both mean MT5, so mirror whatever the base uses.
    base_platform = crow[7] or ""
    new_platform = base_platform if base_platform in ("", "MT5") else "MT5"

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS portal_account_requests (
            id SERIAL PRIMARY KEY, client_id INT, platform VARCHAR(8),
            account_type VARCHAR(20), leverage INT, islamic BOOLEAN,
            status VARCHAR(24) DEFAULT 'pending_admin_review', created_at TIMESTAMP DEFAULT NOW()
        )
    """)); db.commit()
    req_id = db.execute(text("""
        INSERT INTO portal_account_requests (client_id, platform, account_type, leverage, islamic, status)
        VALUES (:c,:p,:t,:l,:i,'provisioning') RETURNING id
    """), {"c": client_id, "p": platform, "t": acc_type, "l": leverage, "i": islamic}).scalar()
    db.commit()

    # Real MT4 self-service provisioning isn't wired (the MT4 manager API can't UserAdd here).
    if platform != "MT5":
        db.execute(text("UPDATE portal_account_requests SET status='mt4_unavailable' WHERE id=:i"), {"i": req_id})
        db.commit()
        return {"ok": False, "error": "mt4_unavailable",
                "message": "MT4 accounts can't be opened automatically yet — please contact support to add one."}

    # ── provision a REAL MT5 account via the bridge ──
    try:
        import mt_provision
        group = mt_provision.real_group(acc_type, islamic)
        # idempotent per portal request row: a double-click / retry can't open two real accounts.
        res = mt_provision.create_account_idempotent(
            db, f"portal_req_{req_id}", group, first, last, leverage=leverage, email=email,
            phone=phone, country=country, city=city, agent=agent)
    except Exception as e:
        res = {"ok": False, "error": str(e)}
    if not res.get("ok"):
        db.execute(text("UPDATE portal_account_requests SET status='failed' WHERE id=:i"), {"i": req_id}); db.commit()
        print(f"[portal] additional-account provision failed for client {client_id}: {res.get('error')}", flush=True)
        return {"ok": False, "error": "provision_failed",
                "message": "We couldn't open the account right now — please try again shortly or contact support."}

    login = int(res["login"]); master = res.get("master") or ""; investor = res.get("investor") or ""
    # Make it appear immediately: a clients row (same phone, MT5='' platform → groups in the portal cluster)
    # + a trading_accounts row. The bridge will also sync this real account on its next cycle.
    try:
        db.execute(text("""
            INSERT INTO clients (login, name, email, phone, country, city, platform, group_name, leverage,
                                 balance, equity, credit, kyc_status, agent, source, reg_date)
            VALUES (:lg,:nm,:em,:ph,:co,:ci,:pl,:grp,:lev,0,0,0,'verified',:ag,'portal_new',to_char(NOW(),'YYYY-MM-DD'))
        """), {"lg": login, "nm": name, "em": email, "ph": phone, "co": country, "ci": city,
               "pl": new_platform, "grp": group, "lev": leverage, "ag": agent})
        db.execute(text("""
            INSERT INTO trading_accounts (login, client_id, name, email, phone, group_name, platform,
                account_type, is_islamic, leverage, balance, equity, kyc_status, source, is_active, agent, reg_date)
            VALUES (:lg,:cid,:nm,:em,:ph,:grp,'MT5','live',:isl,:lev,0,0,'verified','portal_new',TRUE,:ag,
                    to_char(NOW(),'YYYY-MM-DD'))
            ON CONFLICT (login) DO NOTHING
        """), {"lg": login, "cid": client_id, "nm": name, "em": email, "ph": phone, "grp": group,
               "isl": islamic, "lev": leverage, "ag": agent})
        db.execute(text("UPDATE portal_account_requests SET status='created' WHERE id=:i"), {"i": req_id})
        db.commit()
        try:
            import connection_engine as CE
            CE.refresh_account(db, login)   # wire the new account into the network/connection page at once
        except Exception:
            db.rollback()
    except Exception as e:
        db.rollback()
        print(f"[portal] account row insert failed (account {login} exists on MT, bridge will sync): {e}", flush=True)

    return {"ok": True, "account": {
        "login": login, "password": master, "investor": investor, "server": "TNFX-Live",
        "platform": "MT5", "account_type": acc_type, "leverage": leverage, "islamic": islamic,
    }}


# ---------- DEPOSIT METHODS + INITIATE (mix of api/manual) ----------
def _method_currency(code, name):
    """Local deposit methods take LOCAL currency: Qi/Zain/Fastpay -> IQD (Iraq), Sham -> SYP (Syria)."""
    s = f"{code or ''} {name or ''}".lower()
    if "sham" in s:
        return "SYP"
    if "qi" in s or "zain" in s or "fastpay" in s or "fast pay" in s or "q card" in s or "q-card" in s:
        return "IQD"
    return "USD"


@router.get("/deposit/methods")
def deposit_methods(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """Reads payment_methods table, filtered to what this client can use for DEPOSIT:
    active + deposit_enabled + country allowed. Falls back to a static list if table absent."""
    # client country (for region filtering)
    crow = db.execute(text("SELECT country FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    country = (crow[0] if crow else "") or ""
    try:
        from payment_cards_router import fx_rates as _fx
        rates = _fx(db)
    except Exception:
        rates = {"IQD": 1550.0, "SYP": 15000.0}
    try:
        rows = db.execute(text("""
            SELECT code,name,logo,kind,blurb,fee,min_deposit,max_deposit,
                   allow_countries,block_countries,manual_details,api_config
            FROM payment_methods
            WHERE is_active=TRUE AND deposit_enabled=TRUE
            ORDER BY sort_order, id
        """)).fetchall()
    except Exception:
        # table not created yet -> safe fallback
        return {"methods": [
            {"id": "bank_wire", "name": "Bank Wire", "logo": "bank", "type": "manual",
             "blurb": "International wire", "min": 100, "fee": "0%", "details": {}},
        ]}
    def _aliases(s):
        s = (s or "").strip().lower()
        al = {s}
        if s in ("iraq", "iq", "irq", "عراق", "العراق"):
            al |= {"iraq", "iq"}
        return al
    cset = _aliases(country)
    out = []
    for r in rows:
        allow = [a for a in (r[8] or []) if str(a).strip()]
        block = [a for a in (r[9] or []) if str(a).strip()]
        # block wins; allow only filters when the client's country is KNOWN (case-insensitive, IQ/Iraq alias)
        if block and any(_aliases(b) & cset for b in block):
            continue
        if allow and country and not any(_aliases(a) & cset for a in allow):
            continue
        cur = _method_currency(r[0], r[1])
        out.append({
            "id": r[0], "name": r[1], "logo": r[2],
            "type": "api" if r[3] == "auto" else "manual",
            "blurb": r[4] or "", "min": float(r[6]) if r[6] is not None else 0,
            "max": float(r[7]) if r[7] is not None else None,
            "fee": r[5] or "0%",
            "details": (r[10] or {}) if r[3] == "manual" else {},
            # local-currency deposit: enter in this currency, converted to USD at `rate` (units per $1)
            "currency": cur, "rate": rates.get(cur) if cur != "USD" else None,
        })
    return {"methods": out, "fx_rates": rates}


@router.post("/deposit/initiate")
def deposit_initiate(payload: dict, client_id: int = Depends(get_current_client), _imp=Depends(block_impersonation), db: Session = Depends(get_db)):
    method = (payload.get("method") or "").strip()
    amount = float(payload.get("amount") or 0)
    login = payload.get("login")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    _assert_owns_login(db, client_id, login)
    _assert_not_archived(db, login)

    # enforce per-method min + first-deposit minimum by account type
    try:
        mrow = db.execute(text("SELECT min_deposit, max_deposit FROM payment_methods WHERE code=:c AND is_active=TRUE AND deposit_enabled=TRUE"),
                          {"c": method}).fetchone()
        if mrow:
            if mrow[0] is not None and amount < float(mrow[0]):
                raise HTTPException(status_code=400, detail=f"Minimum deposit for this method is ${float(mrow[0]):,.0f}")
            if mrow[1] is not None and amount > float(mrow[1]):
                raise HTTPException(status_code=400, detail=f"Maximum deposit for this method is ${float(mrow[1]):,.0f}")
        # first-deposit minimum: only if the client has no prior completed deposit
        prior = db.execute(text("SELECT COUNT(*) FROM portal_money_requests WHERE client_id=:c AND kind='deposit' AND status IN ('confirmed','completed','approved')"),
                           {"c": client_id}).fetchone()
        is_first = (prior[0] or 0) == 0
        if is_first and login:
            # find the account's type to look up its first_deposit_min (link by login,
            # not the NULL client_id) — only honour a login the client actually owns
            owned = {str(l) for l in _client_logins(db, client_id)}
            arow = None
            if str(login) in owned:
                arow = db.execute(text("SELECT account_type FROM trading_accounts WHERE login=:l"),
                                  {"l": login}).fetchone()
            atype = (arow[0] if arow else "") or ""
            if atype:
                trow = db.execute(text("SELECT first_deposit_min, name FROM account_types WHERE LOWER(code)=LOWER(:t) OR LOWER(name)=LOWER(:t)"),
                                  {"t": atype}).fetchone()
                if trow and trow[0] is not None and amount < float(trow[0]):
                    raise HTTPException(status_code=400,
                        detail=f"First deposit for a {trow[1]} account must be at least ${float(trow[0]):,.0f}")
    except HTTPException:
        raise
    except Exception:
        db.rollback()  # limits table issues shouldn't block, but don't poison txn

    # record the intent
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS portal_money_requests (
                id SERIAL PRIMARY KEY, client_id INT, login BIGINT, kind VARCHAR(12),
                amount NUMERIC, method VARCHAR(40), status VARCHAR(24) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)); db.commit()
    except Exception:
        db.rollback()
    rid = db.execute(text("""
        INSERT INTO portal_money_requests (client_id, login, kind, amount, method, status)
        VALUES (:c,:l,'deposit',:a,:m,'pending_payment') RETURNING id
    """), {"c": client_id, "l": login, "a": amount, "m": method}).scalar()
    db.commit()
    # auto-credit deposit bonus (simulation)
    bonus = {"bonus": 0.0}
    try:
        bonus = BE.credit_deposit_bonus(db, client_id, login, amount, deposit_request_id=rid)
    except Exception:
        db.rollback()
    bval = bonus.get("bonus", 0)

    api_methods = {"card"}
    if method in api_methods:
        # SIMULATED redirect — real version returns the gateway's hosted-payment URL
        return {"mode": "redirect", "simulated": True, "bonus": bval,
                "redirect_url": f"https://pay.tnfx.co/checkout?amt={amount}&ref={client_id}",
                "message": "Redirecting to secure payment…"}
    return {"mode": "manual", "upload_required": True, "bonus": bval,
            "message": "Complete your transfer using the details, then upload your payment proof."
                       + (f" A ${bval:,.2f} bonus has been credited." if bval > 0 else "")}


# ───────────────────────── AI ASSISTANT (live chat) ─────────────────────────
# Reuses the grounding/context builders from chat_router, but authenticates with the
# PORTAL token (get_current_client) and aggregates across all of the client's logins.
import ai_config as _ai
import chat_router as _chat


# ── Client notes: a private memo the AI assistant remembers, editable via the chat ──
def _ensure_notes_table(db: Session):
    db.execute(text("""CREATE TABLE IF NOT EXISTS client_notes (
        id SERIAL PRIMARY KEY, client_id INT, note TEXT, source VARCHAR(20) DEFAULT 'chat',
        created_at TIMESTAMP DEFAULT NOW())"""))
    db.commit()

def get_client_notes(db: Session, client_id: int) -> list:
    try:
        rows = db.execute(text(
            "SELECT note, created_at FROM client_notes WHERE client_id=:c ORDER BY id"
        ), {"c": client_id}).fetchall()
        return [{"note": r[0], "at": str(r[1])[:16]} for r in rows]
    except Exception:
        db.rollback(); return []

def _handle_note_command(db: Session, client_id: int, msg: str):
    """If the message is a `note` command, handle it and return a reply string; else None."""
    s = (msg or "").strip()
    low = s.lower()
    is_note = low in ("note", "notes", "my notes", "/note", "/notes") \
        or low.startswith("note ") or low.startswith("note:") or low.startswith("/note ") or low.startswith("/note:")
    if not is_note:
        return None
    _ensure_notes_table(db)
    # strip the leading "note"/"/note" + separators
    rest = s
    for p in ("/note", "note"):
        if low.startswith(p):
            rest = s[len(p):]; break
    rest = rest.lstrip(" :;-").strip()
    if rest.lower() in ("clear", "delete", "reset", "remove", "clear all"):
        db.execute(text("DELETE FROM client_notes WHERE client_id=:c"), {"c": client_id}); db.commit()
        return "🗒️ All your notes have been cleared."
    if not rest:  # just "note" -> list
        notes = get_client_notes(db, client_id)
        if not notes:
            return "🗒️ You have no notes yet. Add one by typing: **note: <your note>**"
        body = "\n".join(f"• {n['note']}  _( {n['at']} )_" for n in notes)
        return f"🗒️ **Your notes:**\n{body}"
    db.execute(text("INSERT INTO client_notes (client_id, note, source) VALUES (:c,:n,'chat')"),
               {"c": client_id, "n": rest[:1000]}); db.commit()
    return f"🗒️ Saved to your notes: \"{rest[:200]}\". I'll remember this."


@router.get("/chat/health")
def portal_chat_health():
    return {"configured": _ai.is_configured()}

@router.get("/chat/notes")
def portal_chat_notes(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    return {"notes": get_client_notes(db, client_id)}


@router.get("/chat/suggestions")
def portal_chat_suggestions():
    return {"suggestions": [
        "How is my account doing?",
        "What did I do wrong in my recent trades?",
        "Any big market moves today?",
        "How do withdrawals work?",
        "How does the IB program work?",
    ]}


@router.post("/chat")
def portal_chat(payload: dict, client_id: int = Depends(get_current_client),
                db: Session = Depends(get_db)):
    # last user message (used for note-command + topic focus)
    _raw0 = payload.get("messages") or []
    _last_user = ""
    for m in reversed(_raw0):
        if m.get("role") != "assistant":
            _last_user = (m.get("content") or "").strip(); break
    # '#' TICKET COMMAND — the only way a client opens a support ticket now (manual ticket
    # creation is disabled). Works even without the AI key. Handled before the note command.
    if _last_user.startswith("#"):
        _cname = db.execute(text("SELECT name FROM clients WHERE id=:i"), {"i": client_id}).scalar()
        _tr = _chat.ticket_from_hash(db, _last_user, creator_type="client", creator_id=client_id,
                                     creator_name=(_cname or f"Client #{client_id}"), source="chat")
        if _tr is not None:
            return {"reply": _tr, "parts": _chat._split_parts(_tr)}

    # NOTE COMMAND — handled deterministically, works even if the AI key isn't set
    note_reply = _handle_note_command(db, client_id, _last_user)
    if note_reply is not None:
        return {"reply": note_reply, "parts": _chat._split_parts(note_reply)}

    if not _ai.is_configured():
        raise HTTPException(status_code=503,
            detail="The assistant isn't available right now. Please try again later.")

    logins = _client_logins(db, client_id)          # SECURITY: only this client's own logins
    client_ctx = _chat.build_client_context(db, logins) if logins else None
    market = _chat.build_market_snapshot(db)
    try:
        import autochartist_api as _ac
        signals = _ac.opportunities_text(limit=5)
    except Exception:
        signals = ""

    system = _chat.PERSONA + "\n\n=== COMPANY INFO ===\n" + _chat.COMPANY_INFO + "\n\n=== " + market
    if signals:
        system += "\n\n=== " + signals
    if client_ctx:
        system += "\n\n=== " + client_ctx
    notes = get_client_notes(db, client_id)
    if notes:
        system += "\n\n=== CLIENT NOTES (private memo about this client — remember & honour these) ===\n" \
                  + "\n".join(f"- {n['note']}" for n in notes)

    raw = payload.get("messages") or []
    history = []
    for m in raw[-12:]:
        role = "assistant" if (m.get("role") == "assistant") else "user"
        content = (m.get("content") or "").strip()
        if content:
            history.append({"role": role, "content": content[:4000]})
    if not history or history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="Last message must be from the user")

    # remember the last user TEXT before a possible vision-block conversion
    _last_text = history[-1]["content"]
    system += _chat.topic_focus(_last_text)

    # KNOWLEDGE BASE (ticket #79): the portal chat previously had only COMPANY_INFO, so it
    # improvised topics like the account-opening steps. Advertise the full KB index and inject
    # the on-topic article(s) for the client's question (registration, copy trading, deposit,
    # withdraw, bonus, IB, loyalty, autochartist, vps) so the bot answers from the real source.
    try:
        system += "\n\n=== KNOWLEDGE BASE INDEX ===\n" + _chat.kb_articles.article_index()
        _kb_full = _chat.kb_articles.relevant_articles(_last_text)
        if _kb_full:
            system += ("\n\n=== RELEVANT KNOWLEDGE BASE ARTICLE(S) — answer the client's question "
                       "FULLY from this; do NOT deflect to the account manager for information ===\n"
                       + _kb_full)
    except Exception:
        pass

    # OPTIONAL image attachment for the current turn -> vision content blocks (ticket #88)
    _chat.attach_image_to_history(history, payload.get("image_b64"), payload.get("image_media_type"))

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_ai.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=_ai.CHAT_MODEL, max_tokens=_ai.CHAT_MAX_TOKENS,
            system=system, messages=history,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

    reply = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if not reply:
        reply = "Sorry, I couldn't generate a reply just now. Please try again."
    # Process the bot's hidden [[ESCALATE]] flag: opens a Chatbot ticket (source='chat') for any
    # client note / request / feedback the team should see, and strips the marker before the client
    # sees it. Portal chat was missing this, so live-chat notes were never captured (fix Jul 2026).
    _esc_login = logins[0] if logins else None
    reply = _chat._maybe_teach(db, reply, "client", _esc_login, _last_user)      # teach the brain directly
    reply = _chat._maybe_escalate(db, reply, "client", _esc_login, _last_user)   # + open a ticket for team issues
    return {"reply": reply, "parts": _chat._split_parts(reply)}
