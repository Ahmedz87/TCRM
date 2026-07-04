"""
ibp_career.py — the IB-portal Challenge engine (career path + weekly), real data.

Career challenges: an IB ACCEPTS a stage; we snapshot their baseline metrics + set a
deadline. Progress = (current metric − baseline) vs target, counted from the accept moment.
On completion / time-out we email the IB (once). Expired stages can be re-challenged.

Weekly challenges: progress is always computed from THIS WEEK's data (week = since the most
recent Sunday 00:00 server time), so everything auto-resets every Sunday; claims are keyed by
week_start, so last week's progress/claims never carry over.

Emails go out via email_send (degrades to a log line if SMTP isn't configured).
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

import email_send

# ── config ────────────────────────────────────────────────────────────────────
# target keys: clients (new clients), ftd (new funded), lots (new volume)
CAREER = [
    {"key": "getting_started", "stage": 1, "name": "Getting Started", "desc": "Onboard your first 5 clients",          "reward": 50,   "days": 30,  "target": {"clients": 5}},
    {"key": "first_blood",     "stage": 2, "name": "First Blood",     "desc": "Bring your first funded client (FTD)",   "reward": 100,  "days": 14,  "target": {"ftd": 1}},
    {"key": "momentum",        "stage": 3, "name": "Momentum",        "desc": "10 funded clients + 100 lots traded",    "reward": 250,  "days": 30,  "target": {"ftd": 10, "lots": 100}},
    {"key": "rising_star",     "stage": 4, "name": "Rising Star",     "desc": "25 funded clients + 500 lots",           "reward": 600,  "days": 60,  "target": {"ftd": 25, "lots": 500}},
    {"key": "power_partner",   "stage": 5, "name": "Power Partner",   "desc": "50 funded clients + 2,000 lots",         "reward": 1500, "days": 90,  "target": {"ftd": 50, "lots": 2000}},
    {"key": "legend",          "stage": 6, "name": "Legend",          "desc": "100 funded clients + 6,000 lots",        "reward": 4000, "days": 180, "target": {"ftd": 100, "lots": 6000}},
]
CAREER_BY_KEY = {c["key"]: c for c in CAREER}

WEEKLY = [
    {"key": "first_blood_w",  "emoji": "🩸", "name": "First Blood",     "desc": "Bring 1 FTD this week",         "metric": "ftd",      "target": 1,     "reward": 15},
    {"key": "double_down",    "emoji": "⚔️", "name": "Double Down",     "desc": "Bring 2 FTDs this week",        "metric": "ftd",      "target": 2,     "reward": 30},
    {"key": "hat_trick",      "emoji": "🎯", "name": "Hat Trick",       "desc": "Bring 3 FTDs this week",        "metric": "ftd",      "target": 3,     "reward": 60},
    {"key": "volume_hunter",  "emoji": "📊", "name": "Volume Hunter",   "desc": "Clients trade 50 lots",        "metric": "lots",     "target": 50,    "reward": 120},
    {"key": "cash_flow",      "emoji": "💵", "name": "Cash Flow",       "desc": "Clients deposit $5,000",       "metric": "deposits", "target": 5000,  "reward": 30},
    {"key": "link_builder",   "emoji": "🔗", "name": "Link Builder",    "desc": "10 new registrations",         "metric": "regs",     "target": 10,    "reward": 20},
    {"key": "whale_hunter",   "emoji": "🐋", "name": "Whale Hunter",    "desc": "Clients deposit $50,000",      "metric": "deposits", "target": 50000, "reward": 400},
]
WEEKLY_BY_KEY = {c["key"]: c for c in WEEKLY}


def ensure_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ibp_career (
            id            SERIAL PRIMARY KEY,
            ib_id         INTEGER NOT NULL,
            challenge_key VARCHAR NOT NULL,
            accepted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deadline      TIMESTAMPTZ,
            base_clients  INTEGER DEFAULT 0,
            base_ftd      INTEGER DEFAULT 0,
            base_lots     DOUBLE PRECISION DEFAULT 0,
            status        VARCHAR DEFAULT 'active',   -- active|completed|claimed|expired
            completed_at  TIMESTAMPTZ,
            claimed_at    TIMESTAMPTZ,
            start_email   BOOLEAN DEFAULT FALSE,
            end_email     BOOLEAN DEFAULT FALSE,
            UNIQUE (ib_id, challenge_key)
        );
        CREATE TABLE IF NOT EXISTS ibp_weekly_claims (
            ib_id         INTEGER NOT NULL,
            challenge_key VARCHAR NOT NULL,
            week_start    DATE NOT NULL,
            claimed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (ib_id, challenge_key, week_start)
        );
    """))
    db.commit()


def week_start_dt(now=None):
    """Most recent Sunday 00:00 (server local time)."""
    now = now or datetime.now()
    days_since_sun = (now.weekday() + 1) % 7   # Mon=0..Sun=6 -> Sun=0
    ws = (now - timedelta(days=days_since_sun)).replace(hour=0, minute=0, second=0, microsecond=0)
    return ws


# ── metric computation (real data) ────────────────────────────────────────────
def _totals(db, agent):
    """Lifetime totals for an IB's book: clients, funded (FTD), lots."""
    clients = db.execute(text("SELECT COUNT(*) FROM clients WHERE agent = :a"), {"a": agent}).scalar() or 0
    ftd = db.execute(text("""
        SELECT COUNT(DISTINCT t.login) FROM transactions t JOIN clients c ON c.login = t.login
        WHERE c.agent = :a AND t.tx_type = 'deposit'
    """), {"a": agent}).scalar() or 0
    lots = db.execute(text("""
        SELECT COALESCE(SUM(d.volume/10000.0),0) FROM deals d JOIN clients c ON c.login = d.login
        WHERE c.agent = :a AND d.action IN (0,1) AND d.volume > 0
    """), {"a": agent}).scalar() or 0
    return {"clients": int(clients), "ftd": int(ftd), "lots": float(lots)}


def _weekly(db, agent, since):
    """This-week metrics (since = 'YYYY-MM-DD' week start)."""
    p = {"a": agent, "s": since}
    ftd = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT t.login, MIN(t.tx_date) AS first_dep
            FROM transactions t JOIN clients c ON c.login = t.login
            WHERE c.agent = :a AND t.tx_type = 'deposit'
            GROUP BY t.login
        ) x WHERE x.first_dep >= :s
    """), p).scalar() or 0
    lots = db.execute(text("""
        SELECT COALESCE(SUM(d.volume/10000.0),0) FROM deals d JOIN clients c ON c.login = d.login
        WHERE c.agent = :a AND d.action IN (0,1) AND d.volume > 0 AND d.deal_date >= :s
    """), p).scalar() or 0
    deposits = db.execute(text("""
        SELECT COALESCE(SUM(t.amount),0) FROM transactions t JOIN clients c ON c.login = t.login
        WHERE c.agent = :a AND t.tx_type = 'deposit' AND t.tx_date >= :s
    """), p).scalar() or 0
    regs = db.execute(text("""
        SELECT COUNT(*) FROM clients c
        WHERE c.agent = :a AND COALESCE(NULLIF(c.reg_date,''), c.created_at::text) >= :s
    """), p).scalar() or 0
    return {"ftd": int(ftd), "lots": float(lots), "deposits": float(deposits), "regs": int(regs)}


# ── email helpers ─────────────────────────────────────────────────────────────
def _email(db, ib_id, subject, heading, message, sub=None):
    row = db.execute(text("SELECT email, name FROM ibs WHERE id = :id"), {"id": ib_id}).fetchone()
    if not row or not row[0]:
        return
    try:
        email_send.send(row[0], subject, message, email_send.notice_html(heading, message, sub))
    except Exception as e:
        print(f"[challenges] email failed: {e}", flush=True)


# ── public API ────────────────────────────────────────────────────────────────
def accept(db, ib_id, key):
    cfg = CAREER_BY_KEY.get(key)
    if not cfg:
        raise ValueError("unknown challenge")
    ib = db.execute(text("SELECT agent_id FROM ibs WHERE id = :id"), {"id": ib_id}).fetchone()
    if not ib:
        raise ValueError("ib not found")
    base = _totals(db, ib[0])
    db.execute(text("""
        INSERT INTO ibp_career (ib_id, challenge_key, accepted_at, deadline, base_clients, base_ftd, base_lots, status, start_email)
        VALUES (:ib, :k, NOW(), NOW() + (:days || ' days')::interval, :bc, :bf, :bl, 'active', TRUE)
        ON CONFLICT (ib_id, challenge_key) DO UPDATE SET
            accepted_at = NOW(), deadline = NOW() + (:days || ' days')::interval,
            base_clients = :bc, base_ftd = :bf, base_lots = :bl,
            status = 'active', completed_at = NULL, claimed_at = NULL, start_email = TRUE, end_email = FALSE
    """), {"ib": ib_id, "k": key, "days": cfg["days"], "bc": base["clients"], "bf": base["ftd"], "bl": base["lots"]})
    db.commit()
    _email(db, ib_id, f"🚀 Challenge started: {cfg['name']}",
           f"Challenge started — {cfg['name']}",
           f"You've accepted the '{cfg['name']}' challenge: {cfg['desc']}. You have {cfg['days']} days. "
           f"Reward: ${cfg['reward']}. Track your progress in your Partner Portal.",
           "Good luck — the clock is ticking!")
    return list_all(db, ib_id)


def claim(db, ib_id, key):
    """Claim a completed career reward."""
    row = db.execute(text("SELECT status FROM ibp_career WHERE ib_id=:ib AND challenge_key=:k"),
                     {"ib": ib_id, "k": key}).fetchone()
    if not row or row[0] != "completed":
        raise ValueError("not claimable")
    db.execute(text("UPDATE ibp_career SET status='claimed', claimed_at=NOW() WHERE ib_id=:ib AND challenge_key=:k"),
               {"ib": ib_id, "k": key})
    db.commit()
    cfg = CAREER_BY_KEY.get(key, {})
    _email(db, ib_id, f"💰 Reward claimed: {cfg.get('name','')}",
           f"Reward claimed — ${cfg.get('reward',0)}",
           f"You claimed your ${cfg.get('reward',0)} reward for '{cfg.get('name','')}'. It will be credited to your IB account.")
    return list_all(db, ib_id)


def rechallenge(db, ib_id, key):
    """Reset an expired career challenge so it can be accepted again."""
    db.execute(text("DELETE FROM ibp_career WHERE ib_id=:ib AND challenge_key=:k AND status='expired'"),
               {"ib": ib_id, "k": key})
    db.commit()
    return list_all(db, ib_id)


def claim_weekly(db, ib_id, key):
    cfg = WEEKLY_BY_KEY.get(key)
    if not cfg:
        raise ValueError("unknown weekly challenge")
    ib = db.execute(text("SELECT agent_id FROM ibs WHERE id=:id"), {"id": ib_id}).fetchone()
    if not ib:
        raise ValueError("ib not found")
    ws = week_start_dt()
    since = ws.date().isoformat()
    m = _weekly(db, ib[0], since)
    if m.get(cfg["metric"], 0) < cfg["target"]:
        raise ValueError("not completed yet")
    db.execute(text("""
        INSERT INTO ibp_weekly_claims (ib_id, challenge_key, week_start, claimed_at)
        VALUES (:ib, :k, :ws, NOW()) ON CONFLICT DO NOTHING
    """), {"ib": ib_id, "k": key, "ws": ws.date()})
    db.commit()
    return list_all(db, ib_id)


def list_all(db, ib_id):
    """Career + weekly with live progress; lazily transitions status + fires emails."""
    ensure_tables(db)
    ib = db.execute(text("SELECT agent_id FROM ibs WHERE id=:id"), {"id": ib_id}).fetchone()
    if not ib:
        return {"career": [], "weekly": [], "week_start": None, "seconds_to_reset": 0}
    agent = ib[0]
    totals = _totals(db, agent)
    now = datetime.now(timezone.utc)

    rows = {r[0]: r for r in db.execute(text("""
        SELECT challenge_key, accepted_at, deadline, base_clients, base_ftd, base_lots, status,
               completed_at, claimed_at, end_email
        FROM ibp_career WHERE ib_id = :ib
    """), {"ib": ib_id}).fetchall()}

    career = []
    for cfg in CAREER:
        r = rows.get(cfg["key"])
        item = {**{k: cfg[k] for k in ("key", "stage", "name", "desc", "reward", "days", "target")}}
        if not r:
            item.update(status="available", progress={}, pct=0, accepted_at=None, deadline=None, seconds_left=None)
            career.append(item); continue
        accepted_at, deadline, bc, bf, bl, status, completed_at, claimed_at, end_email = r[1:]
        prog = {}
        if "clients" in cfg["target"]: prog["clients"] = max(0, totals["clients"] - (bc or 0))
        if "ftd" in cfg["target"]:     prog["ftd"]     = max(0, totals["ftd"] - (bf or 0))
        if "lots" in cfg["target"]:    prog["lots"]    = max(0, totals["lots"] - (bl or 0))
        met = all(prog.get(k, 0) >= v for k, v in cfg["target"].items())
        pct = int(min(100, 100 * min((prog.get(k, 0) / v if v else 1) for k, v in cfg["target"].items())))
        # lazy transitions
        if status == "active" and met:
            status = "completed"
            db.execute(text("UPDATE ibp_career SET status='completed', completed_at=NOW(), end_email=TRUE WHERE ib_id=:ib AND challenge_key=:k"), {"ib": ib_id, "k": cfg["key"]})
            db.commit()
            _email(db, ib_id, f"🎉 Challenge complete: {cfg['name']}",
                   f"Challenge complete — {cfg['name']}",
                   f"You completed '{cfg['name']}'! Head to your Partner Portal to claim your ${cfg['reward']} reward.")
        elif status == "active" and deadline and now > deadline.astimezone(timezone.utc):
            status = "expired"
            db.execute(text("UPDATE ibp_career SET status='expired', end_email=TRUE WHERE ib_id=:ib AND challenge_key=:k"), {"ib": ib_id, "k": cfg["key"]})
            db.commit()
            _email(db, ib_id, f"⏰ Time's up: {cfg['name']}",
                   f"Time's up — {cfg['name']}",
                   f"The time for '{cfg['name']}' ran out. Don't worry — you can re-challenge and try again any time.",
                   "Tap Re-challenge in your Partner Portal to restart.")
        seconds_left = int((deadline.astimezone(timezone.utc) - now).total_seconds()) if deadline else None
        item.update(status=status, progress=prog, pct=pct,
                    accepted_at=accepted_at.isoformat() if accepted_at else None,
                    deadline=deadline.isoformat() if deadline else None,
                    seconds_left=max(0, seconds_left) if seconds_left is not None else None)
        career.append(item)

    # weekly
    ws = week_start_dt()
    since = ws.date().isoformat()
    wm = _weekly(db, agent, since)
    claimed = {c[0] for c in db.execute(text(
        "SELECT challenge_key FROM ibp_weekly_claims WHERE ib_id=:ib AND week_start=:ws"),
        {"ib": ib_id, "ws": ws.date()}).fetchall()}
    weekly = []
    for cfg in WEEKLY:
        cur = wm.get(cfg["metric"], 0)
        pct = int(min(100, 100 * (cur / cfg["target"] if cfg["target"] else 1)))
        weekly.append({**{k: cfg[k] for k in ("key", "emoji", "name", "desc", "metric", "target", "reward")},
                       "progress": cur, "pct": pct,
                       "ready": cur >= cfg["target"], "claimed": cfg["key"] in claimed})
    reset_at = ws + timedelta(days=7)
    seconds_to_reset = int((reset_at - datetime.now()).total_seconds())
    return {"career": career, "weekly": weekly,
            "week_start": ws.date().isoformat(), "seconds_to_reset": max(0, seconds_to_reset)}
