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
import json
import re
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

# ── DB-editable definitions (partner-site admin) ─────────────────────────────
# The CAREER/WEEKLY constants above are only the FIRST-RUN SEED; after that the
# ibp_challenge_defs table is the source of truth (edited from the partner admin UI).
_DEFS_READY = False


def _num(v, default=0):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return default


def ensure_defs(db):
    global _DEFS_READY
    if _DEFS_READY:
        return
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ibp_challenge_defs (
            kind    VARCHAR NOT NULL,           -- career | weekly
            key     VARCHAR NOT NULL,
            ord     INTEGER NOT NULL DEFAULT 0,
            name    VARCHAR NOT NULL,
            descr   VARCHAR DEFAULT '',
            emoji   VARCHAR DEFAULT '',
            reward  DOUBLE PRECISION DEFAULT 0,
            days    INTEGER,
            targets JSONB,
            metric  VARCHAR,
            target  DOUBLE PRECISION,
            enabled BOOLEAN DEFAULT TRUE,
            PRIMARY KEY (kind, key)
        )
    """))
    if not (db.execute(text("SELECT COUNT(*) FROM ibp_challenge_defs")).scalar() or 0):
        for c in CAREER:
            db.execute(text("""
                INSERT INTO ibp_challenge_defs (kind, key, ord, name, descr, reward, days, targets, enabled)
                VALUES ('career', :k, :o, :n, :d, :r, :dy, CAST(:t AS jsonb), TRUE)
                ON CONFLICT DO NOTHING"""),
                {"k": c["key"], "o": c["stage"], "n": c["name"], "d": c["desc"],
                 "r": c["reward"], "dy": c["days"], "t": json.dumps(c["target"])})
        for i, w in enumerate(WEEKLY):
            db.execute(text("""
                INSERT INTO ibp_challenge_defs (kind, key, ord, name, descr, emoji, reward, metric, target, enabled)
                VALUES ('weekly', :k, :o, :n, :d, :e, :r, :m, :t, TRUE)
                ON CONFLICT DO NOTHING"""),
                {"k": w["key"], "o": i + 1, "n": w["name"], "d": w["desc"], "e": w["emoji"],
                 "r": w["reward"], "m": w["metric"], "t": w["target"]})
    db.commit()
    _DEFS_READY = True


def get_career(db, include_disabled=False):
    ensure_defs(db)
    out = []
    for r in db.execute(text("""
            SELECT key, ord, name, descr, reward, days, targets, enabled
            FROM ibp_challenge_defs WHERE kind = 'career' ORDER BY ord, key""")).fetchall():
        if not include_disabled and not r[7]:
            continue
        t = r[6] or {}
        if isinstance(t, str):
            t = json.loads(t)
        out.append({"key": r[0], "stage": int(r[1] or 0), "name": r[2], "desc": r[3] or "",
                    "reward": _num(r[4]), "days": int(r[5] or 30),
                    "target": {k: _num(v) for k, v in t.items() if _num(v)},
                    "enabled": bool(r[7])})
    return out


def get_weekly(db, include_disabled=False):
    ensure_defs(db)
    out = []
    for r in db.execute(text("""
            SELECT key, ord, name, descr, emoji, reward, metric, target, enabled
            FROM ibp_challenge_defs WHERE kind = 'weekly' ORDER BY ord, key""")).fetchall():
        if not include_disabled and not r[8]:
            continue
        out.append({"key": r[0], "emoji": r[4] or "🏅", "name": r[2], "desc": r[3] or "",
                    "metric": r[6] or "ftd", "target": _num(r[7], 1), "reward": _num(r[5]),
                    "enabled": bool(r[8])})
    return out


def _slug(name, existing):
    base = re.sub(r"[^a-z0-9]+", "_", (name or "challenge").lower()).strip("_") or "challenge"
    key, i = base, 2
    while key in existing:
        key, i = f"{base}_{i}", i + 1
    return key


def admin_save(db, career, weekly):
    """Full replace from the partner-admin editor. Keys are kept stable (they join to the
    IBs' accepted/claimed rows); new items get a slug key derived from the name."""
    ensure_defs(db)
    db.execute(text("DELETE FROM ibp_challenge_defs"))
    seen = set()
    for i, c in enumerate(career or []):
        key = (c.get("key") or "").strip() or _slug(c.get("name"), seen)
        if key in seen:
            continue
        seen.add(key)
        target = {k: _num(v) for k, v in (c.get("target") or {}).items()
                  if k in ("clients", "ftd", "nda", "lots") and _num(v)}
        db.execute(text("""
            INSERT INTO ibp_challenge_defs (kind, key, ord, name, descr, reward, days, targets, enabled)
            VALUES ('career', :k, :o, :n, :d, :r, :dy, CAST(:t AS jsonb), :en)"""),
            {"k": key, "o": i + 1, "n": (c.get("name") or "").strip() or key,
             "d": (c.get("desc") or "").strip(), "r": _num(c.get("reward")),
             "dy": max(1, int(_num(c.get("days"), 30))), "t": json.dumps(target or {"clients": 1}),
             "en": bool(c.get("enabled", True))})
    wseen = set()
    for i, w in enumerate(weekly or []):
        key = (w.get("key") or "").strip() or _slug(w.get("name"), seen | wseen)
        if key in wseen:
            continue
        wseen.add(key)
        metric = w.get("metric") if w.get("metric") in ("ftd", "nda", "lots", "deposits", "regs", "clicks") else "ftd"
        db.execute(text("""
            INSERT INTO ibp_challenge_defs (kind, key, ord, name, descr, emoji, reward, metric, target, enabled)
            VALUES ('weekly', :k, :o, :n, :d, :e, :r, :m, :t, :en)"""),
            {"k": key, "o": i + 1, "n": (w.get("name") or "").strip() or key,
             "d": (w.get("desc") or "").strip(), "e": (w.get("emoji") or "🏅").strip(),
             "r": _num(w.get("reward")), "m": metric, "t": _num(w.get("target"), 1) or 1,
             "en": bool(w.get("enabled", True))})
    db.commit()
    return {"career": len(seen), "weekly": len(wseen)}


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
        ALTER TABLE ibp_career ADD COLUMN IF NOT EXISTS base_nda INTEGER DEFAULT 0;
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
_FIRST_ACCT_CTE = """
    WITH ib_cust AS (
        SELECT DISTINCT c.customer_no FROM clients c
        WHERE c.agent = :a AND c.customer_no IS NOT NULL
    ),
    fa AS (
        SELECT DISTINCT ON (c.customer_no) c.customer_no, c.agent,
               NULLIF(c.first_deposit_at,'') AS fd, c.is_nda
        FROM clients c JOIN ib_cust ic ON ic.customer_no = c.customer_no
        WHERE NULLIF(c.first_deposit_at,'') IS NOT NULL
        ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC
    )
"""


def _totals(db, agent):
    """Lifetime totals for an IB's book: clients, funded (FTD), NDA, lots.
    FTD = customers whose FIRST-ever deposited account (any IB) is under THIS agent —
    an existing customer adding an account here is NOT an FTD (desk rule Jul 2026)."""
    clients = db.execute(text("SELECT COUNT(*) FROM clients WHERE agent = :a"), {"a": agent}).scalar() or 0
    row = db.execute(text(_FIRST_ACCT_CTE + """
        SELECT COUNT(*) FILTER (WHERE fa.agent = :a)               AS ftd,
               COUNT(*) FILTER (WHERE fa.agent = :a AND fa.is_nda) AS nda
        FROM fa"""), {"a": agent}).fetchone()
    lots = db.execute(text("""
        SELECT COALESCE(SUM(d.volume/10000.0),0) FROM deals d JOIN clients c ON c.login = d.login
        WHERE c.agent = :a AND d.action IN (0,1) AND d.volume > 0
    """), {"a": agent}).scalar() or 0
    return {"clients": int(clients), "ftd": int(row[0] or 0), "nda": int(row[1] or 0), "lots": float(lots)}


def _weekly(db, agent, since, ib_id=None):
    """This-week metrics (since = 'YYYY-MM-DD' week start)."""
    p = {"a": agent, "s": since}
    ftd = db.execute(text(_FIRST_ACCT_CTE + """
        SELECT COUNT(*) FROM fa WHERE fa.agent = :a AND fa.fd >= :s
    """), p).scalar() or 0
    nda = db.execute(text(_FIRST_ACCT_CTE + """
        SELECT COUNT(*) FROM fa WHERE fa.agent = :a AND fa.fd >= :s AND fa.is_nda
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
        WHERE c.agent = :a AND NULLIF(c.reg_date,'') >= :s
    """), p).scalar() or 0
    # unique referral-link clicks this week (feeds the 'clicks' weekly challenge metric)
    clicks = 0
    if ib_id and db.execute(text("SELECT to_regclass('public.ib_ref_clicks')")).scalar():
        clicks = db.execute(text("""SELECT COUNT(*) FROM ib_ref_clicks
            WHERE ib_id=:i AND is_unique AND at >= CAST(:s AS timestamptz)"""),
            {"i": ib_id, "s": since}).scalar() or 0
    return {"ftd": int(ftd), "nda": int(nda), "lots": float(lots), "deposits": float(deposits),
            "regs": int(regs), "clicks": int(clicks)}


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
    careers = get_career(db)
    cfg = next((c for c in careers if c["key"] == key), None)
    if not cfg:
        raise ValueError("unknown challenge")
    # SEQUENTIAL gate: you can only start a stage once the PREVIOUS stage is claimed.
    idx = next((i for i, c in enumerate(careers) if c["key"] == key), 0)
    if idx > 0:
        prev_key = careers[idx - 1]["key"]
        prev = db.execute(text("SELECT status FROM ibp_career WHERE ib_id=:ib AND challenge_key=:k"),
                          {"ib": ib_id, "k": prev_key}).fetchone()
        if not prev or prev[0] != "claimed":
            raise ValueError("Finish and claim the previous stage first")
    ib = db.execute(text("SELECT agent_id FROM ibs WHERE id = :id"), {"id": ib_id}).fetchone()
    if not ib:
        raise ValueError("ib not found")
    base = _totals(db, ib[0])
    db.execute(text("""
        INSERT INTO ibp_career (ib_id, challenge_key, accepted_at, deadline, base_clients, base_ftd, base_nda, base_lots, status, start_email)
        VALUES (:ib, :k, NOW(), NOW() + (:days || ' days')::interval, :bc, :bf, :bn, :bl, 'active', TRUE)
        ON CONFLICT (ib_id, challenge_key) DO UPDATE SET
            accepted_at = NOW(), deadline = NOW() + (:days || ' days')::interval,
            base_clients = :bc, base_ftd = :bf, base_nda = :bn, base_lots = :bl,
            status = 'active', completed_at = NULL, claimed_at = NULL, start_email = TRUE, end_email = FALSE
    """), {"ib": ib_id, "k": key, "days": cfg["days"], "bc": base["clients"], "bf": base["ftd"], "bn": base["nda"], "bl": base["lots"]})
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
    cfg = next((c for c in get_career(db, include_disabled=True) if c["key"] == key), {})
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
    cfg = next((w for w in get_weekly(db) if w["key"] == key), None)
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
               completed_at, claimed_at, end_email, COALESCE(base_nda,0)
        FROM ibp_career WHERE ib_id = :ib
    """), {"ib": ib_id}).fetchall()}

    career = []
    prev_claimed = True   # SEQUENTIAL career path: the first stage is always open; every later stage
                          # unlocks only once the PREVIOUS stage has been CLAIMED (not just completed).
    for cfg in get_career(db):
        r = rows.get(cfg["key"])
        item = {**{k: cfg[k] for k in ("key", "stage", "name", "desc", "reward", "days", "target")}}
        if not r:
            item.update(status=("available" if prev_claimed else "locked"),
                        progress={}, pct=0, accepted_at=None, deadline=None, seconds_left=None)
            career.append(item)
            prev_claimed = False
            continue
        accepted_at, deadline, bc, bf, bl, status, completed_at, claimed_at, end_email, bn = r[1:]
        prog = {}
        if "clients" in cfg["target"]: prog["clients"] = max(0, totals["clients"] - (bc or 0))
        if "ftd" in cfg["target"]:     prog["ftd"]     = max(0, totals["ftd"] - (bf or 0))
        if "nda" in cfg["target"]:     prog["nda"]     = max(0, totals["nda"] - (bn or 0))
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
        prev_claimed = (status == "claimed")

    # weekly
    ws = week_start_dt()
    since = ws.date().isoformat()
    wm = _weekly(db, agent, since, ib_id)
    claimed = {c[0] for c in db.execute(text(
        "SELECT challenge_key FROM ibp_weekly_claims WHERE ib_id=:ib AND week_start=:ws"),
        {"ib": ib_id, "ws": ws.date()}).fetchall()}
    weekly = []
    for cfg in get_weekly(db):
        cur = wm.get(cfg["metric"], 0)
        pct = int(min(100, 100 * (cur / cfg["target"] if cfg["target"] else 1)))
        weekly.append({**{k: cfg[k] for k in ("key", "emoji", "name", "desc", "metric", "target", "reward")},
                       "progress": cur, "pct": pct,
                       "ready": cur >= cfg["target"], "claimed": cfg["key"] in claimed})
    reset_at = ws + timedelta(days=7)
    seconds_to_reset = int((reset_at - datetime.now()).total_seconds())
    return {"career": career, "weekly": weekly,
            "totals": {"clients": totals["clients"], "ftd": totals["ftd"],
                       "nda": totals["nda"], "lots": round(totals["lots"], 1)},
            "week_start": ws.date().isoformat(), "seconds_to_reset": max(0, seconds_to_reset)}
