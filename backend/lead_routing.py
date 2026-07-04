"""
lead_routing.py — rule-based lead assignment engine.

The desk defines ordered RULES (Settings -> Leads Settings). Each rule has:
  - name, priority (higher number wins), is_active
  - criteria (JSONB): any of countries / cities / campaigns / sources / ib_ids / timing.
      * a field that is empty/absent is NOT a constraint (matches everything)
      * within a field's list the match is OR (country in [...])
      * across fields the match is AND (all specified fields must match)
      * timing = {days:[0..6 Mon..Sun], from:"HH:MM", to:"HH:MM"} matched against the
        lead's arrival time (meta_created, else created_at), shifted by config.tz_offset.
  - agent_ids (int[]): the sales agents the rule assigns to. One lead -> ONE agent,
    chosen ROUND-ROBIN across the list so "Iraqis -> X,Y,Z" spreads evenly.

assign_lead() walks active rules by priority DESC and takes the FIRST match. So an Iraqi
lead from Facebook is resolved by whichever of the two rules has the higher priority.

If NO rule matches and the IB default is enabled, an IB lead goes to that IB's managing
sales agent (ibs.assigned_agent_id). Rules are ALWAYS evaluated first, so a Leads-Settings
rule overrides the IB default (the order the desk asked for).

Everything here is additive and idempotent. Safe to import from the Meta fetch loop; the
caller must wrap the call so a routing error can never block lead insertion.
"""
import json
import datetime
from sqlalchemy import text


def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS lead_assignment_rules (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            priority INT NOT NULL DEFAULT 100,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
            agent_ids INT[] NOT NULL DEFAULT '{}',
            rr_pointer INT NOT NULL DEFAULT 0,
            created_by INT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS lead_routing_config (
            id INT PRIMARY KEY DEFAULT 1,
            auto_assign_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ib_default_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
            fallback_agent_id INT,
            tz_offset INT NOT NULL DEFAULT 3,        -- hours added to UTC for timing rules (Baghdad=+3)
            updated_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("INSERT INTO lead_routing_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS assigned_rule_id INT"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP"))
    db.commit()


# ───────────────────────── config ─────────────────────────
def get_config(db):
    ensure_schema(db)
    r = db.execute(text("""
        SELECT auto_assign_enabled, ib_default_enabled, fallback_agent_id, tz_offset
        FROM lead_routing_config WHERE id=1
    """)).fetchone()
    if not r:
        return {"auto_assign_enabled": True, "ib_default_enabled": True,
                "fallback_agent_id": None, "tz_offset": 3}
    return {"auto_assign_enabled": bool(r[0]), "ib_default_enabled": bool(r[1]),
            "fallback_agent_id": r[2], "tz_offset": int(r[3] or 0)}


def save_config(db, data):
    ensure_schema(db)
    db.execute(text("""
        UPDATE lead_routing_config SET
            auto_assign_enabled = COALESCE(:a, auto_assign_enabled),
            ib_default_enabled  = COALESCE(:i, ib_default_enabled),
            fallback_agent_id   = :f,
            tz_offset           = COALESCE(:t, tz_offset),
            updated_at = NOW()
        WHERE id=1
    """), {"a": data.get("auto_assign_enabled"), "i": data.get("ib_default_enabled"),
           "f": data.get("fallback_agent_id"), "t": data.get("tz_offset")})
    db.commit()
    return get_config(db)


# ───────────────────────── matching ─────────────────────────
def _norm(s):
    return (s or "").strip().lower()


def _list_norm(v):
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    return [_norm(x) for x in v if str(x).strip() != ""]


def _arrival(lead, tz_offset):
    """Best arrival datetime for the lead, shifted to the config timezone (naive)."""
    dt = lead.get("meta_created") or lead.get("created_at")
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    # treat naive as UTC, then shift
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt + datetime.timedelta(hours=tz_offset or 0)


def _hm(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _timing_match(timing, lead, tz_offset):
    if not timing:
        return True
    days = timing.get("days") or []
    frm = _hm(timing.get("from")) if timing.get("from") else None
    to = _hm(timing.get("to")) if timing.get("to") else None
    if not days and frm is None and to is None:
        return True
    at = _arrival(lead, tz_offset)
    if at is None:
        return False
    if days and at.weekday() not in [int(d) for d in days]:
        return False
    if frm is not None and to is not None:
        cur = at.hour * 60 + at.minute
        if frm <= to:
            if not (frm <= cur <= to):
                return False
        else:                       # overnight window e.g. 22:00 -> 06:00
            if not (cur >= frm or cur <= to):
                return False
    return True


def match(criteria, lead, tz_offset=0):
    """True if the lead satisfies every specified criterion in the rule."""
    c = criteria or {}
    countries = _list_norm(c.get("countries"))
    if countries and _norm(lead.get("country")) not in countries:
        return False
    cities = _list_norm(c.get("cities"))
    if cities and _norm(lead.get("city")) not in cities:
        return False
    campaigns = _list_norm(c.get("campaigns"))
    if campaigns and _norm(lead.get("campaign_name")) not in campaigns:
        return False
    sources = _list_norm(c.get("sources"))
    if sources and _norm(lead.get("source")) not in sources:
        return False
    ib_ids = c.get("ib_ids") or []
    if ib_ids:
        try:
            wanted = {int(x) for x in ib_ids}
        except Exception:
            wanted = set()
        if lead.get("ib_id") is None or int(lead["ib_id"]) not in wanted:
            return False
    if not _timing_match(c.get("timing"), lead, tz_offset):
        return False
    return True


# ───────────────────────── assignment ─────────────────────────
def _active_rules(db):
    rows = db.execute(text("""
        SELECT id, name, priority, criteria, agent_ids, rr_pointer
        FROM lead_assignment_rules
        WHERE is_active = TRUE
        ORDER BY priority DESC, id ASC
    """)).fetchall()
    return [{"id": r[0], "name": r[1], "priority": r[2],
             "criteria": r[3] or {}, "agent_ids": list(r[4] or []), "rr_pointer": int(r[5] or 0)}
            for r in rows]


def _pick_round_robin(db, rule):
    agents = [a for a in (rule.get("agent_ids") or []) if a]
    if not agents:
        return None
    ptr = int(rule.get("rr_pointer") or 0) % len(agents)
    agent = agents[ptr]
    db.execute(text("UPDATE lead_assignment_rules SET rr_pointer=:p WHERE id=:i"),
               {"p": (ptr + 1) % len(agents), "i": rule["id"]})
    rule["rr_pointer"] = ptr + 1
    return agent


def _ib_default_agent(db, lead, cfg):
    """The managing sales agent for the lead's IB (ibs.assigned_agent_id), if any."""
    if not cfg.get("ib_default_enabled"):
        return None
    ib_id = lead.get("ib_id")
    if ib_id:
        a = db.execute(text("SELECT assigned_agent_id FROM ibs WHERE id=:i"), {"i": ib_id}).scalar()
        if a:
            return a
    # derive via the matched client's MT agent -> ibs
    ml = lead.get("matched_login")
    if ml:
        a = db.execute(text("""
            SELECT ib.assigned_agent_id
            FROM clients c JOIN ibs ib ON ib.agent_id = c.agent
            WHERE c.login = :l AND ib.assigned_agent_id IS NOT NULL
            LIMIT 1
        """), {"l": ml}).scalar()
        if a:
            return a
    return None


def resolve(db, lead, rules, cfg):
    """Return (agent_id, rule_id, reason) for one lead — does NOT write the lead."""
    for rule in rules:
        if match(rule["criteria"], lead, cfg.get("tz_offset", 0)):
            agent = _pick_round_robin(db, rule)
            if agent:
                return agent, rule["id"], f"rule:{rule['name']}"
    a = _ib_default_agent(db, lead, cfg)
    if a:
        return a, None, "ib_default"
    if cfg.get("fallback_agent_id"):
        return cfg["fallback_agent_id"], None, "fallback"
    return None, None, "none"


def _lead_row(db, lead_id):
    r = db.execute(text("""
        SELECT id, country, city, campaign_name, source, ib_id, matched_login,
               meta_created, created_at, COALESCE(ai_managed, FALSE)
        FROM leads WHERE id=:i
    """), {"i": lead_id}).fetchone()
    if not r:
        return None
    return {"id": r[0], "country": r[1], "city": r[2], "campaign_name": r[3], "source": r[4],
            "ib_id": r[5], "matched_login": r[6], "meta_created": r[7], "created_at": r[8],
            "ai_managed": bool(r[9])}


def assign_lead(db, lead_id, force=False, commit=True):
    """Assign one lead by id. By default skips leads that already have an agent
    (force=True re-assigns). Returns a small result dict."""
    cfg = get_config(db)
    if not cfg.get("auto_assign_enabled"):
        return {"ok": False, "reason": "auto_assign_disabled"}
    lead = _lead_row(db, lead_id)
    if not lead:
        return {"ok": False, "reason": "not_found"}
    if lead.get("ai_managed"):
        return {"ok": False, "reason": "ai_managed"}     # AI owns this lead — no human assignment
    if not force:
        cur = db.execute(text("SELECT assigned_agent_id FROM leads WHERE id=:i"), {"i": lead_id}).scalar()
        if cur:
            return {"ok": False, "reason": "already_assigned", "agent_id": cur}
    rules = _active_rules(db)
    agent, rule_id, reason = resolve(db, lead, rules, cfg)
    if agent:
        db.execute(text("""
            UPDATE leads SET assigned_agent_id=:a, assigned_rule_id=:r, assigned_at=NOW(),
                             updated_at=NOW()
            WHERE id=:i
        """), {"a": agent, "r": rule_id, "i": lead_id})
    if commit:
        db.commit()
    return {"ok": bool(agent), "agent_id": agent, "rule_id": rule_id, "reason": reason}


def apply_all(db, only_unassigned=True, dry_run=False):
    """Bulk-assign existing leads. Returns stats. Re-runnable."""
    cfg = get_config(db)
    rules = _active_rules(db)
    # never route AI-owned (WhatsApp AI) leads to humans
    where = "WHERE COALESCE(ai_managed,FALSE)=FALSE" + (" AND assigned_agent_id IS NULL" if only_unassigned else "")
    rows = db.execute(text(f"""
        SELECT id, country, city, campaign_name, source, ib_id, matched_login,
               meta_created, created_at
        FROM leads {where}
    """)).fetchall()
    stats = {"scanned": len(rows), "assigned": 0, "by_rule": 0, "by_ib": 0,
             "by_fallback": 0, "unassigned": 0, "per_agent": {}}
    n = 0
    for r in rows:
        lead = {"id": r[0], "country": r[1], "city": r[2], "campaign_name": r[3], "source": r[4],
                "ib_id": r[5], "matched_login": r[6], "meta_created": r[7], "created_at": r[8]}
        agent, rule_id, reason = resolve(db, lead, rules, cfg)
        if not agent:
            stats["unassigned"] += 1
            continue
        stats["assigned"] += 1
        stats["per_agent"][agent] = stats["per_agent"].get(agent, 0) + 1
        if reason.startswith("rule:"):
            stats["by_rule"] += 1
        elif reason == "ib_default":
            stats["by_ib"] += 1
        elif reason == "fallback":
            stats["by_fallback"] += 1
        if not dry_run:
            db.execute(text("""
                UPDATE leads SET assigned_agent_id=:a, assigned_rule_id=:r, assigned_at=NOW(),
                                 updated_at=NOW()
                WHERE id=:i
            """), {"a": agent, "r": rule_id, "i": lead[0] if isinstance(lead, list) else lead["id"]})
            n += 1
            if n % 500 == 0:
                db.commit()
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return stats


def preview_rule(db, criteria, only_unassigned=False):
    """Count how many existing leads a (possibly unsaved) rule's criteria would match."""
    cfg = get_config(db)
    where = "WHERE assigned_agent_id IS NULL" if only_unassigned else ""
    rows = db.execute(text(f"""
        SELECT country, city, campaign_name, source, ib_id, meta_created, created_at
        FROM leads {where}
    """)).fetchall()
    cnt = 0
    for r in rows:
        lead = {"country": r[0], "city": r[1], "campaign_name": r[2], "source": r[3],
                "ib_id": r[4], "meta_created": r[5], "created_at": r[6]}
        if match(criteria, lead, cfg.get("tz_offset", 0)):
            cnt += 1
    return {"matches": cnt, "scanned": len(rows)}
