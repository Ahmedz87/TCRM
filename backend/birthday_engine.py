"""
Birthday bonus engine — a $100 gift a client can claim in a window around their birthday
(5 days before → 2 days after, configurable), IF they made a real deposit in the last 365 days.

Design (read before changing):
- Keyed on clients.date_of_birth (VARCHAR 'YYYY-MM-DD'). Today only ~a handful of clients have a DOB;
  backfill_dob.py fills it from registrations + KYC OCR and the KYC verify path keeps it growing.
- Eligibility = a real deposit within birthday_deposit_window_days. Deposit truth = the transactions
  ledger (tx_type='deposit', amount>0), same source the rest of the CRM uses. transactions.tx_date is
  a STRING datetime, so it's regex-guarded then cast to timestamp.
- The claim mirrors the welcome bonus: writes bonus_grants(kind='birthday') + bumps clients.credit +
  pushes the $100 to the real MT account as CREDIT (type 3) in the background (push_birthday_credit).
- Sales side: birthday_events holds per-client-per-year state (greeted / claimed) so the Clients page
  can show a 🎂 whose colour is grey (not greeted) → gold (greeted / called) → green (claimed). The
  +100 priority score is computed live in clients_router.get_clients (not stored here).
- Config lives in bonus_config via bonus_engine.get_config (birthday_* keys), so the desk tunes it in
  the admin Bonus settings and the AI bot can read it.
"""
from __future__ import annotations
from datetime import datetime, date, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import SessionLocal

import bonus_engine as BE   # reuse get_config / client_logins


# ───────────────────────── SCHEMA ─────────────────────────
def ensure_schema(db: Session):
    """birthday_events: one row per client per birthday-year (sales greeting + claim state)."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS birthday_events (
                id SERIAL PRIMARY KEY,
                client_id INT,
                login BIGINT,
                year INT,
                birthday_date DATE,
                greeted BOOLEAN DEFAULT FALSE,
                greeted_at TIMESTAMP,
                greeted_by VARCHAR(160),
                claimed BOOLEAN DEFAULT FALSE,
                claimed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (client_id, year)
            )
        """))
        db.commit()
    except Exception:
        db.rollback()


# ───────────────────────── CONFIG ─────────────────────────
def cfg_birthday(db: Session) -> dict:
    c = BE.get_config(db)
    return {
        "enabled":        bool(c.get("birthday_enabled", True)) and bool(c.get("bonuses_enabled", True)),
        "amount":         float(c.get("birthday_amount", 100.0) or 0),
        "before_days":    int(c.get("birthday_before_days", 5) or 0),
        "after_days":     int(c.get("birthday_after_days", 2) or 0),
        "deposit_days":   int(c.get("birthday_deposit_window_days", 365) or 365),
    }


# ───────────────────────── DATE WINDOW ─────────────────────────
def _today() -> date:
    return datetime.now().date()


def window_mmdd(cfg: dict, today: date | None = None) -> list:
    """The set of 'MM-DD' strings that are 'in the birthday window' today.
    Window per client = [birthday - before_days, birthday + after_days]; today is in that window iff
    the birthday's month-day falls in [today - after_days, today + before_days]. Feb-29 births are
    caught by adding '02-29' whenever '02-28' is in range (non-leap years)."""
    today = today or _today()
    out = set()
    for d in range(-cfg["after_days"], cfg["before_days"] + 1):
        out.add((today + timedelta(days=d)).strftime("%m-%d"))
    if "02-28" in out:
        out.add("02-29")
    return sorted(out)


def _parse_dob(s):
    """Parse a stored DOB string → date, or None. Accepts YYYY-MM-DD (the canonical form) plus a few
    common fallbacks; ignores anything unparseable."""
    if not s:
        return None
    s = str(s).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def _birthday_this_cycle(dob: date, today: date):
    """The client's birthday occurrence nearest to 'today' (this year, or last year's if we're within
    the after-window of a Dec/Jan wrap). Returns (occ_date, days_to) where days_to = occ - today."""
    def occ(year):
        try:
            return date(year, dob.month, dob.day)
        except ValueError:      # Feb-29 in a non-leap year
            return date(year, 2, 28)
    candidates = [occ(today.year - 1), occ(today.year), occ(today.year + 1)]
    best = min(candidates, key=lambda o: abs((o - today).days))
    return best, (best - today).days


# ───────────────────────── ELIGIBILITY ─────────────────────────
def has_recent_deposit(db: Session, client_id: int, days: int) -> bool:
    """Has this client made a real deposit within the last `days`? Deposit truth = transactions."""
    try:
        logins = BE.client_logins(db, client_id)
        if not logins:
            return False
        n = db.execute(text("""
            SELECT COUNT(*) FROM transactions
            WHERE login = ANY(:l) AND tx_type='deposit' AND COALESCE(amount,0) > 0
              AND tx_date ~ '^\\d{4}-\\d{2}-\\d{2}'
              AND tx_date::timestamp >= NOW() - (:d || ' days')::interval
        """), {"l": logins, "d": int(days)}).scalar() or 0
        return n > 0
    except Exception:
        db.rollback()
        return False


def _claimed_this_year(db: Session, client_id: int, year: int) -> bool:
    try:
        n = db.execute(text("""
            SELECT COUNT(*) FROM birthday_events
            WHERE client_id=:c AND year=:y AND claimed=TRUE
        """), {"c": client_id, "y": year}).scalar() or 0
        return n > 0
    except Exception:
        db.rollback()
        return False


# ───────────────────────── PORTAL STATUS ─────────────────────────
def birthday_status(db: Session, client_id: int) -> dict:
    """Portal payload for the bonus KPI / page.
    state ∈ disabled | none | eligible | need_deposit | claimed."""
    cfg = cfg_birthday(db)
    amount = cfg["amount"]
    base = {"enabled": cfg["enabled"], "amount": amount, "in_window": False,
            "days_to_birthday": None, "eligible": False, "claimed": False, "state": "none"}
    if not cfg["enabled"]:
        return {**base, "state": "disabled"}
    row = db.execute(text("SELECT date_of_birth FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    dob = _parse_dob(row[0]) if row else None
    if not dob:
        return {**base, "state": "none"}
    today = _today()
    occ, days_to = _birthday_this_cycle(dob, today)
    # days_to = occ - today: positive before the birthday, negative after. Claim opens before_days
    # BEFORE the birthday (days_to up to +before_days) and closes after_days AFTER (down to -after_days).
    in_window = (-cfg["after_days"] <= days_to <= cfg["before_days"])
    base["days_to_birthday"] = days_to
    if not in_window:
        return {**base, "state": "none"}
    base["in_window"] = True
    if _claimed_this_year(db, client_id, occ.year):
        return {**base, "claimed": True, "state": "claimed"}
    eligible = has_recent_deposit(db, client_id, cfg["deposit_days"])
    base["eligible"] = eligible
    return {**base, "state": "eligible" if eligible else "need_deposit"}


def claim_birthday(db: Session, client_id: int) -> dict:
    """Validate + grant the birthday bonus. Idempotent per client per birthday-year."""
    ensure_schema(db)
    st = birthday_status(db, client_id)
    if st["state"] == "claimed":
        return {"ok": False, "state": "claimed", "message": "Birthday bonus already claimed."}
    if st["state"] != "eligible":
        msgs = {
            "disabled": "The birthday bonus is currently unavailable.",
            "none": "The birthday bonus is only available around your birthday.",
            "need_deposit": "Make a deposit within the last 365 days to unlock your birthday bonus.",
        }
        return {"ok": False, "state": st["state"], "message": msgs.get(st["state"], "Not eligible.")}

    amount = float(st["amount"])
    logins = BE.client_logins(db, client_id)
    login = logins[0] if logins else None
    dobrow = db.execute(text("SELECT date_of_birth FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    dob = _parse_dob(dobrow[0]) if dobrow else None
    occ, _ = _birthday_this_cycle(dob, _today()) if dob else (_today(), 0)

    db.execute(text("""
        INSERT INTO bonus_grants (client_id, login, kind, deposit_amount, amount, status)
        VALUES (:c,:l,'birthday',0,:a,'credited')
    """), {"c": client_id, "l": login, "a": amount})
    db.execute(text("""
        INSERT INTO birthday_events (client_id, login, year, birthday_date, claimed, claimed_at)
        VALUES (:c,:l,:y,:bd,TRUE,NOW())
        ON CONFLICT (client_id, year)
        DO UPDATE SET claimed=TRUE, claimed_at=NOW(), login=EXCLUDED.login, birthday_date=EXCLUDED.birthday_date
    """), {"c": client_id, "l": login, "y": occ.year, "bd": occ})
    db.execute(text("UPDATE clients SET credit = COALESCE(credit,0) + :a WHERE id=:id"),
               {"a": amount, "id": client_id})
    db.commit()
    return {"ok": True, "state": "claimed", "amount": amount, "login": login,
            "message": f"🎂 ${amount:,.0f} birthday bonus credited to your trading account!"}


def push_birthday_credit(client_id: int):
    """Background: push the $100 to the REAL MT account as CREDIT (type 3) + email the client.
    Mirrors bonus_engine.push_welcome_credit. Opens its own session; never raises."""
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT g.login, g.amount, c.name, c.email FROM bonus_grants g JOIN clients c ON c.id=g.client_id
            WHERE g.client_id=:id AND g.kind='birthday' AND g.status<>'cancelled'
            ORDER BY g.id DESC LIMIT 1
        """), {"id": client_id}).fetchone()
        if not row:
            return
        login, amount = row[0], float(row[1] or 0)
        if login and int(login) > 0:
            try:
                import mt_provision
                res = mt_provision.credit_account(int(login), amount, "TNFX Birthday Bonus", credit_type=3)
                if not res.get("ok"):
                    print(f"[birthday] MT credit failed for login {login}: {res.get('error')}", flush=True)
            except Exception as e:
                print(f"[birthday] MT credit exception for login {login}: {e}", flush=True)
        try:
            import email_send
            if row[3] and email_send.configured():
                nm = (row[2] or "").split(" ")[0]
                body = (f"Dear {nm},\n\nOn behalf of TNFX, we wish you a happy birthday. Your ${amount:,.0f} birthday "
                        f"bonus has been credited to your trading account{(' #' + str(login)) if login else ''}. It "
                        "appears as Credit on your terminal and increases your available trading margin.\n\n"
                        "Kind regards,\nTNFX")
                email_send.send(row[3], f"Happy Birthday — your ${amount:,.0f} TNFX bonus has been credited", body)
        except Exception as e:
            print(f"[birthday] email failed for client {client_id}: {e}", flush=True)
    finally:
        db.close()


# ───────────────────────── SALES OVERLAY (Clients page) ─────────────────────────
def birthday_window_logins(db: Session, cfg: dict | None = None) -> dict:
    """Map login -> {birthday_date, occ_year, days_to} for every login whose DOB month-day is in the
    window today. Cheap: filtered to the few clients that actually have a DOB. Aggregation to
    phone+platform siblings happens in the caller (get_clients already has all_logins)."""
    cfg = cfg or cfg_birthday(db)
    if not cfg["enabled"]:
        return {}
    mmdd = window_mmdd(cfg)
    try:
        rows = db.execute(text("""
            SELECT login, date_of_birth FROM clients
            WHERE login IS NOT NULL
              AND date_of_birth ~ '^\\d{4}-\\d{2}-\\d{2}$'
              AND substring(date_of_birth from 6 for 5) = ANY(:mmdd)
        """), {"mmdd": mmdd}).fetchall()
    except Exception:
        db.rollback()
        return {}
    today = _today()
    out = {}
    for login, dobs in rows:
        dob = _parse_dob(dobs)
        if not dob:
            continue
        occ, days_to = _birthday_this_cycle(dob, today)
        if -cfg["after_days"] <= days_to <= cfg["before_days"]:
            out[login] = {"birthday_date": occ.isoformat(), "occ_year": occ.year, "days_to": days_to}
    return out


def event_state(db: Session, logins: list) -> dict:
    """login -> {greeted, claimed} from birthday_events for the current cycle years."""
    if not logins:
        return {}
    try:
        rows = db.execute(text("""
            SELECT login, bool_or(greeted), bool_or(claimed) FROM birthday_events
            WHERE login = ANY(:l) AND year >= :y GROUP BY login
        """), {"l": logins, "y": _today().year - 1}).fetchall()
    except Exception:
        db.rollback()
        return {}
    return {r[0]: {"greeted": bool(r[1]), "claimed": bool(r[2])} for r in rows}


def _cake_color(greeted: bool, claimed: bool) -> str:
    if claimed:
        return "green"
    if greeted:
        return "gold"
    return "grey"


def birthday_flags(db: Session, logins: list, cfg: dict | None = None) -> dict:
    """Per-login overlay for the Clients list: {in_window, greeted, claimed, cake_color,
    birthday_date, days_to}. Only returns logins that are in the window today."""
    cfg = cfg or cfg_birthday(db)
    win = birthday_window_logins(db, cfg)
    win = {l: v for l, v in win.items() if l in set(logins)} if logins else win
    if not win:
        return {}
    st = event_state(db, list(win.keys()))
    out = {}
    for login, v in win.items():
        s = st.get(login, {})
        greeted, claimed = bool(s.get("greeted")), bool(s.get("claimed"))
        out[login] = {"in_window": True, "greeted": greeted, "claimed": claimed,
                      "cake_color": _cake_color(greeted, claimed),
                      "birthday_date": v["birthday_date"], "days_to": v["days_to"]}
    return out


def mark_greeted(db: Session, login: int, by: str = "") -> dict:
    """Called when a successful ('connected_done') call is logged. If the client is in their birthday
    window, record the greeting (cake → gold, +100 score drops off). No-op otherwise."""
    ensure_schema(db)
    cfg = cfg_birthday(db)
    if not cfg["enabled"]:
        return {"ok": False, "skipped": "disabled"}
    win = birthday_window_logins(db, cfg)
    info = win.get(login)
    if not info:
        return {"ok": False, "skipped": "not_in_window"}
    row = db.execute(text("SELECT id FROM clients WHERE login=:l"), {"l": login}).fetchone()
    if not row:
        return {"ok": False, "skipped": "no_client"}
    client_id = row[0]
    try:
        db.execute(text("""
            INSERT INTO birthday_events (client_id, login, year, birthday_date, greeted, greeted_at, greeted_by)
            VALUES (:c,:l,:y,:bd,TRUE,NOW(),:by)
            ON CONFLICT (client_id, year)
            DO UPDATE SET greeted=TRUE, greeted_at=NOW(), greeted_by=:by
        """), {"c": client_id, "l": login, "y": info["occ_year"], "bd": info["birthday_date"],
               "by": (by or "")[:150]})
        db.commit()
        return {"ok": True, "greeted": True}
    except Exception as e:
        db.rollback()
        return {"ok": False, "error": str(e)}


def list_birthdays(db: Session) -> list:
    """Admin/desk view: clients whose birthday is in the window today, with greeted/claimed/eligible."""
    cfg = cfg_birthday(db)
    win = birthday_window_logins(db, cfg)
    if not win:
        return []
    logins = list(win.keys())
    st = event_state(db, logins)
    rows = db.execute(text("""
        SELECT login, id, name, phone, country, city, agent, kyc_status
        FROM clients WHERE login = ANY(:l)
    """), {"l": logins}).fetchall()
    out = []
    for login, cid, name, phone, country, city, agent, kyc in rows:
        v = win[login]; s = st.get(login, {})
        greeted, claimed = bool(s.get("greeted")), bool(s.get("claimed"))
        out.append({
            "login": login, "client_id": cid, "name": name, "phone": phone,
            "country": country, "city": city,
            "birthday_date": v["birthday_date"], "days_to": v["days_to"],
            "greeted": greeted, "claimed": claimed, "cake_color": _cake_color(greeted, claimed),
            "eligible": has_recent_deposit(db, cid, cfg["deposit_days"]),
        })
    out.sort(key=lambda x: x["days_to"])
    return out


if __name__ == "__main__":
    db = SessionLocal()
    ensure_schema(db)
    c = cfg_birthday(db)
    print("cfg:", c)
    print("window mm-dd:", window_mmdd(c))
    print("in-window logins:", len(birthday_window_logins(db, c)))
    db.close()
