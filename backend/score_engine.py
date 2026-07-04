"""
score_engine.py — admin-defined SCORING RULES layered on the base priority score.

Each rule: scope ('lead'|'client'), field, value, points, active, expires_at. A rule ADDS its
points to a record's score when the field matches (e.g. country='Iraq' → +10; client with no
deposit for ≥30 days → +20; deposited via 'Zaincash' → +15). Rules can be activated/deactivated
(seasonal) and given an expiry date (or never). Recompute is IDEMPOTENT: the base is reset on each
run, then active, non-expired rules are added — so re-running never double-counts.

Leads keep their existing base formula (mirrors auto_match.compute_score); clients get a fresh
rules-only score in `clients.score` (separate from call_score/network_score/risk_score).
"""
from sqlalchemy import text

# field -> (SQL predicate, needs_value, multi)
#   multi=True  -> value is a comma-separated list; predicate uses  = ANY(:vlist)  (lower-cased list)
#   multi=False + needs_value -> single value via :v  (e.g. no_deposit_days = int)
#   needs_value=False -> boolean condition, no value
LEAD_FIELDS = {
    "country":      ("LOWER(COALESCE(country,'')) = ANY(:vlist)",      True,  True),
    "city":         ("LOWER(COALESCE(city,'')) = ANY(:vlist)",         True,  True),
    "source":       ("LOWER(COALESCE(source,'')) = ANY(:vlist)",       True,  True),
    "campaign":     ("LOWER(COALESCE(campaign_name,'')) = ANY(:vlist)", True, True),
    "status":       ("LOWER(COALESCE(status,'')) = ANY(:vlist)",       True,  True),
    "language":     ("LOWER(COALESCE(language,'')) = ANY(:vlist)",     True,  True),
    "match_badge":  ("LOWER(COALESCE(match_badge,'')) = ANY(:vlist)",  True,  True),
    "meta_quality": ("LOWER(COALESCE(meta_quality,'')) = ANY(:vlist)", True,  True),
    "verified":     ("kyc_status = 'verified'",                        False, False),
    "has_phone":    ("COALESCE(phone,'') <> ''",                       False, False),
    "no_phone":     ("COALESCE(phone,'') = ''",                        False, False),
}
CLIENT_FIELDS = {
    "country":         ("LOWER(COALESCE(country,'')) = ANY(:vlist)",   True,  True),
    "city":            ("LOWER(COALESCE(city,'')) = ANY(:vlist)",      True,  True),
    "source":          ("LOWER(COALESCE(source,'')) = ANY(:vlist)",    True,  True),
    "platform":        ("LOWER(COALESCE(NULLIF(platform,''),'mt5')) = ANY(:vlist)", True, True),
    "sales_agent":     ("assigned_agent_id IN (SELECT id FROM users WHERE LOWER(full_name) = ANY(:vlist))", True, True),
    "deposit_method":  ("EXISTS (SELECT 1 FROM transactions t WHERE t.login = clients.login "
                        "AND t.tx_type='deposit' AND LOWER(COALESCE(t.method,'')) = ANY(:vlist))", True, True),
    "verified":        ("kyc_status = 'verified'",                     False, False),
    "depositor":       ("COALESCE(total_deposits,0) > 0",              False, False),
    "no_deposit_ever": ("COALESCE(total_deposits,0) <= 0",             False, False),
    "no_deposit_days": ("COALESCE(total_deposits,0) <= 0 AND (last_call_at IS NULL "
                        "OR last_call_at < NOW() - ((:v)::int || ' days')::interval)", True, False),
    "has_ib":          ("COALESCE(NULLIF(agent::text,''),'0') <> '0'", False, False),
    "archived":        ("COALESCE(user_archived,FALSE) = TRUE",        False, False),
}
FIELDS = {"lead": LEAD_FIELDS, "client": CLIENT_FIELDS}


def _rule_params(cond, value, points):
    """Build SQL params for a rule; return None if a required value is missing/empty."""
    p = {"p": int(points or 0)}
    needs_value, multi = cond[1], cond[2]
    if needs_value:
        if multi:
            vlist = [v.strip().lower() for v in str(value or "").split(",") if v.strip()]
            if not vlist:
                return None
            p["vlist"] = vlist
        else:
            if not str(value or "").strip():
                return None
            p["v"] = str(value).strip()
    return p


def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS score_rules (
            id BIGSERIAL PRIMARY KEY,
            scope VARCHAR(8),               -- 'lead' | 'client'
            field VARCHAR(24),
            value TEXT,
            points INT DEFAULT 0,
            active BOOLEAN DEFAULT TRUE,
            label VARCHAR,
            expires_at DATE,                -- NULL = never expires
            created_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    # Only ALTER clients if the column is genuinely missing — `ADD COLUMN IF NOT EXISTS` still grabs
    # an ACCESS EXCLUSIVE lock on the busy 160k-row table and times out when run every request.
    has = db.execute(text("SELECT 1 FROM information_schema.columns "
                          "WHERE table_name='clients' AND column_name='score'")).scalar()
    if not has:
        db.execute(text("ALTER TABLE clients ADD COLUMN score INT DEFAULT 0"))
    db.commit()


def _active_rules(db, scope):
    return db.execute(text("""
        SELECT id, field, value, points FROM score_rules
        WHERE scope=:s AND active=TRUE AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)
        ORDER BY id
    """), {"s": scope}).fetchall()


def apply_rules(db):
    """Recompute lead + client scores: base reset, then add every active non-expired rule. Idempotent.
    Heavy (rewrites ~343k rows) — wait for concurrent writers (auto_match) instead of failing fast."""
    ensure_schema(db)
    db.execute(text("SET LOCAL lock_timeout = '120s'"))
    db.execute(text("SET LOCAL statement_timeout = '600s'"))

    # LEADS — reset to the base blended formula (mirror of auto_match.compute_score), then add rules.
    db.execute(text("""
        UPDATE leads SET score = LEAST(100,
              (CASE WHEN match_badge IN ('recapture','registered_no_deposit') THEN 50 ELSE 0 END)
            + (CASE WHEN phone_verified THEN 15 ELSE 0 END)
            + (CASE WHEN email_verified THEN 15 ELSE 0 END)
            + (CASE WHEN COALESCE(phone,'')<>'' AND COALESCE(email,'')<>'' THEN 10 ELSE 0 END)
            + (CASE WHEN COALESCE(meta_created, created_at) >= NOW() - INTERVAL '48 hours' THEN 30
                    WHEN COALESCE(meta_created, created_at) >= NOW() - INTERVAL '7 days'  THEN 10
                    WHEN COALESCE(meta_created, created_at) >= NOW() - INTERVAL '30 days' THEN 5 ELSE 0 END))
    """))
    nlead = 0
    for _id, field, value, points in _active_rules(db, "lead"):
        cond = LEAD_FIELDS.get(field)
        if not cond:
            continue
        params = _rule_params(cond, value, points)
        if params is None:
            continue
        db.execute(text(f"UPDATE leads SET score = LEAST(100, GREATEST(0, score + :p)) WHERE {cond[0]}"), params)
        nlead += 1

    # CLIENTS — rules-only score (engine-owned column), reset to 0 then add rules.
    db.execute(text("UPDATE clients SET score = 0"))
    nclient = 0
    for _id, field, value, points in _active_rules(db, "client"):
        cond = CLIENT_FIELDS.get(field)
        if not cond:
            continue
        params = _rule_params(cond, value, points)
        if params is None:
            continue
        db.execute(text(f"UPDATE clients SET score = LEAST(100, GREATEST(0, score + :p)) WHERE {cond[0]}"), params)
        nclient += 1

    db.commit()
    return {"lead_rules_applied": nlead, "client_rules_applied": nclient}


if __name__ == "__main__":
    from database import SessionLocal
    db = SessionLocal()
    print(apply_rules(db))
    db.close()
