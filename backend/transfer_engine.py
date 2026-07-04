"""
transfer_engine.py — reassign clients/leads between sales/retention agents with caps, an
audit log, and an on-record comment. Powers:
  • Phase C: auto sales→retention handover on first deposit, "transfer out of my data".
  • Phase D: bulk transfer (filters + multi-agent split by count/%), auto-distribute.

Ownership lives on clients.assigned_agent_id / leads.assigned_agent_id (the columns the Sales
Agents page + everything else read). The on-record comment goes to call_actions (clients, shows on
the client timeline) / leads.notes (leads). Every move is written to transfer_log.

CAPS (client books): Team Leader ≤ 300, Retention ≤ 1000, Sales = unlimited. When a retention/TL is
at the cap, don't route new clients to them.
"""
import datetime
from sqlalchemy import text

CAP_RETENTION = 1000
CAP_TEAM_LEADER = 300


# ─────────────────────────── schema ───────────────────────────
def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS transfer_log (
            id BIGSERIAL PRIMARY KEY,
            record_type VARCHAR(8),          -- 'client' | 'lead'
            record_key  BIGINT,              -- client login OR lead id
            from_agent_id INT, to_agent_id INT,
            by_user_id INT, by_user_name VARCHAR,
            reason TEXT, batch_id VARCHAR,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_transfer_log_to ON transfer_log(to_agent_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_transfer_log_batch ON transfer_log(batch_id)"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS transfer_requests (
            id BIGSERIAL PRIMARY KEY,
            record_type VARCHAR(8), record_key BIGINT,
            from_agent_id INT, requested_by_id INT, requested_by_name VARCHAR,
            manager_id INT, status VARCHAR(12) DEFAULT 'pending',  -- pending|done|rejected
            to_agent_id INT, reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(), resolved_at TIMESTAMPTZ
        )"""))
    db.commit()


# ─────────────────────────── agents + caps ───────────────────────────
def agent_info(db, agent_id):
    r = db.execute(text(
        "SELECT id, full_name, role, team_type, manager_id FROM users WHERE id=:i"
    ), {"i": agent_id}).fetchone()
    if not r:
        return None
    return {"id": r[0], "name": r[1], "role": r[2] or "", "team_type": r[3] or "", "manager_id": r[4]}


def cap_for(info):
    """Client-book cap for an agent. None = unlimited (sales)."""
    if not info:
        return None
    tt, role = (info.get("team_type") or "").lower(), (info.get("role") or "").lower()
    if tt == "retention":
        return CAP_RETENTION
    if tt == "lead" or role == "sales_manager":   # team leaders
        return CAP_TEAM_LEADER
    return None


def client_count(db, agent_id):
    # unique PEOPLE (customer_no), same grain as the Clients list — not raw account rows
    return db.execute(text("SELECT COUNT(DISTINCT customer_no) FROM clients WHERE assigned_agent_id=:a"),
                      {"a": agent_id}).scalar() or 0


def remaining_capacity(db, agent_id):
    """How many more clients this agent can take. None = unlimited."""
    cap = cap_for(agent_info(db, agent_id))
    if cap is None:
        return None
    return max(0, cap - client_count(db, agent_id))


def agent_caps_overview(db):
    """Every team agent with role/team, current client count, cap, remaining — for the transfer UI."""
    rows = db.execute(text("""
        SELECT u.id, u.full_name, u.role, u.team_type, u.manager_id, m.full_name AS mgr,
               COALESCE(cc.n,0) AS clients
        FROM users u
        LEFT JOIN users m ON m.id = u.manager_id
        LEFT JOIN (SELECT assigned_agent_id aid, COUNT(DISTINCT customer_no) n FROM clients GROUP BY assigned_agent_id) cc
               ON cc.aid = u.id
        WHERE (u.role IN ('sales_agent','sales_manager') OR u.title ILIKE '%team leader%' OR u.team_type IN ('sales','retention','lead'))
          AND COALESCE(u.is_active, TRUE)
        ORDER BY u.full_name
    """)).fetchall()
    out = []
    for r in rows:
        info = {"team_type": r[3], "role": r[2]}
        cap = cap_for(info)
        out.append({
            "id": r[0], "name": r[1], "role": r[2] or "", "team_type": r[3] or "",
            "manager_id": r[4], "manager": r[5] or "", "clients": r[6],
            "cap": cap, "remaining": (None if cap is None else max(0, cap - r[6])),
            "at_cap": (cap is not None and r[6] >= cap),
        })
    return out


# ─────────────────────────── the core move ───────────────────────────
def reassign(db, record_type, keys, to_agent_id, by_user, reason="", batch_id=None, commit=True):
    """Move records (client logins or lead ids) to to_agent_id. Writes transfer_log + an on-record
    comment. Returns the number moved. Does NOT enforce caps — callers decide (bulk respects caps)."""
    keys = [int(k) for k in keys if k]
    if not keys:
        return 0
    by_id = getattr(by_user, "id", None)
    by_name = getattr(by_user, "full_name", None) or getattr(by_user, "email", "") or "system"
    to_info = agent_info(db, to_agent_id)
    to_name = to_info["name"] if to_info else f"#{to_agent_id}"
    note = f"Transferred to you by {by_name}" + (f" — {reason}" if reason else "")

    moved = 0
    if record_type == "client":
        rows = db.execute(text("SELECT login, assigned_agent_id FROM clients WHERE login = ANY(:k)"),
                          {"k": keys}).fetchall()
        db.execute(text("UPDATE clients SET assigned_agent_id=:to WHERE login = ANY(:k)"),
                   {"to": to_agent_id, "k": keys})
        for login, frm in rows:
            db.execute(text("""INSERT INTO transfer_log
                (record_type,record_key,from_agent_id,to_agent_id,by_user_id,by_user_name,reason,batch_id)
                VALUES ('client',:rk,:frm,:to,:bid,:bn,:rs,:bt)"""),
                {"rk": login, "frm": frm, "to": to_agent_id, "bid": by_id, "bn": by_name, "rs": reason, "bt": batch_id})
            db.execute(text("INSERT INTO call_actions (login, agent_id, action, note, created_at) "
                            "VALUES (:l,:a,'transfer_in',:n,NOW())"),
                       {"l": login, "a": to_agent_id, "n": note})
            moved += 1
    else:  # lead
        rows = db.execute(text("SELECT id, assigned_agent_id FROM leads WHERE id = ANY(:k)"),
                          {"k": keys}).fetchall()
        db.execute(text("UPDATE leads SET assigned_agent_id=:to, assigned_at=NOW() WHERE id = ANY(:k)"),
                   {"to": to_agent_id, "k": keys})
        for lid, frm in rows:
            db.execute(text("""INSERT INTO transfer_log
                (record_type,record_key,from_agent_id,to_agent_id,by_user_id,by_user_name,reason,batch_id)
                VALUES ('lead',:rk,:frm,:to,:bid,:bn,:rs,:bt)"""),
                {"rk": lid, "frm": frm, "to": to_agent_id, "bid": by_id, "bn": by_name, "rs": reason, "bt": batch_id})
            db.execute(text("UPDATE leads SET notes = "
                            "CASE WHEN notes IS NULL OR notes='' THEN :n ELSE notes || E'\\n' || :n END "
                            "WHERE id=:i"), {"n": note + " (" + datetime.date.today().isoformat() + ")", "i": lid})
            moved += 1
    if commit:
        db.commit()
    return moved


# ─────────────────────────── record selection (bulk filters) ───────────────────────────
def select_records(db, record_type, from_agent_id, f):
    """Return record keys from from_agent_id's book matching the filters `f` (a dict):
      count, order ('oldest'|'newest'|'no_deposit'), no_deposit_days, country, city,
      ib ('yes'|'no'|''), last_activity_days, exclude_own (stub).  Capped to `count`.
    """
    f = f or {}
    where = ["assigned_agent_id = :a"]
    p = {"a": from_agent_id}
    if f.get("country"):
        where.append("country = :country"); p["country"] = f["country"]
    if f.get("city"):
        where.append("city = :city"); p["city"] = f["city"]
    la = int(f.get("last_activity_days") or 0)
    if la > 0:
        where.append("(last_call_at IS NULL OR last_call_at < NOW() - (:la || ' days')::interval)")
        p["la"] = la

    if record_type == "client":
        if f.get("ib") == "yes":
            where.append("agent IS NOT NULL AND agent > 0")
        elif f.get("ib") == "no":
            where.append("(agent IS NULL OR agent = 0)")
        nd = int(f.get("no_deposit_days") or 0)
        if f.get("order") == "no_deposit" or nd > 0:
            where.append("COALESCE(total_deposits,0) <= 0")
            if nd > 0:
                where.append("(last_call_at IS NULL OR last_call_at < NOW() - (:nd || ' days')::interval)")
                p["nd"] = nd
        order = {"oldest": "created_at ASC NULLS LAST", "newest": "created_at DESC NULLS LAST",
                 "no_deposit": "created_at ASC NULLS LAST"}.get(f.get("order"), "created_at DESC NULLS LAST")
        sql = f"SELECT login FROM clients WHERE {' AND '.join(where)} ORDER BY {order}"
    else:  # lead
        if f.get("source"):
            where.append("source = :source"); p["source"] = f["source"]
        order = {"oldest": "created_at ASC NULLS LAST", "newest": "created_at DESC NULLS LAST"}.get(
            f.get("order"), "created_at DESC NULLS LAST")
        sql = f"SELECT id FROM leads WHERE {' AND '.join(where)} ORDER BY {order}"

    cnt = int(f.get("count") or 0)
    if cnt > 0 and f.get("order") != "all":   # order='all' = take ALL matching, ignore the count
        sql += " LIMIT :lim"; p["lim"] = cnt
    return [int(r[0]) for r in db.execute(text(sql), p).fetchall()]


def count_book(db, record_type, agent_id, f=None):
    """How many records match the filters (no LIMIT) — for the live filtered count."""
    f = dict(f or {}); f.pop("count", None); f["order"] = "all"
    return len(select_records(db, record_type, agent_id, f))


def book_meta(db, record_type, agent_id):
    """Total book size + the distinct countries/cities present in this agent's book —
    powers the live total and the searchable country/city dropdowns in the transfer UI."""
    tbl = "clients" if record_type == "client" else "leads"
    total = db.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE assigned_agent_id=:a"),
                       {"a": agent_id}).scalar() or 0
    countries = [r[0] for r in db.execute(text(
        f"SELECT DISTINCT country FROM {tbl} WHERE assigned_agent_id=:a AND country IS NOT NULL AND country<>'' ORDER BY 1"
    ), {"a": agent_id}).fetchall()]
    cities = [r[0] for r in db.execute(text(
        f"SELECT DISTINCT city FROM {tbl} WHERE assigned_agent_id=:a AND city IS NOT NULL AND city<>'' ORDER BY 1"
    ), {"a": agent_id}).fetchall()]
    return {"total": total, "countries": countries, "cities": cities}


# ─────────────────────────── split across targets ───────────────────────────
def split_keys(keys, targets):
    """targets: [{agent_id, count?, pct?}]. Returns [(agent_id, [keys...]) ...].
    If counts given, take that many each in order; if pct, derive counts from the total."""
    total = len(keys)
    alloc = []
    has_pct = any(t.get("pct") for t in targets)
    if has_pct:
        for t in targets:
            alloc.append(int(round(total * float(t.get("pct") or 0) / 100.0)))
    else:
        alloc = [int(t.get("count") or 0) for t in targets]
    # clamp to available
    out, i = [], 0
    for t, n in zip(targets, alloc):
        n = max(0, min(n, total - i))
        out.append((t["agent_id"], keys[i:i + n]))
        i += n
    return out


# ─────────────────────────── bulk transfer ───────────────────────────
def bulk_transfer(db, from_agent_id, record_type, filters, targets, reason, by_user,
                  respect_caps=True, dry_run=False):
    """Select from_agent_id's matching records, split across targets (count or %), reassign.
    Returns a summary. dry_run returns the plan without moving anything."""
    ensure_schema(db)
    keys = select_records(db, record_type, from_agent_id, filters)
    plan = split_keys(keys, targets)

    result = {"record_type": record_type, "matched": len(keys), "dry_run": dry_run, "targets": []}
    batch_id = None if dry_run else f"bulk-{from_agent_id}-{int(datetime.datetime.now().timestamp()) if False else ''}"
    # batch id without timestamp() (kept deterministic-ish); use a uuid-ish from ids
    if not dry_run:
        first = keys[0] if keys else 0
        batch_id = f"bulk{from_agent_id}_{record_type}_{len(keys)}_{first}"

    for agent_id, akeys in plan:
        info = agent_info(db, agent_id)
        capped_keys = akeys
        skipped = 0
        if respect_caps and record_type == "client":
            rem = remaining_capacity(db, agent_id)
            if rem is not None and len(akeys) > rem:
                capped_keys = akeys[:rem]
                skipped = len(akeys) - rem
        moved = 0
        if not dry_run and capped_keys:
            moved = reassign(db, record_type, capped_keys, agent_id, by_user, reason, batch_id, commit=False)
        result["targets"].append({
            "agent_id": agent_id, "agent": info["name"] if info else f"#{agent_id}",
            "assigned": len(capped_keys) if dry_run else moved,
            "skipped_over_cap": skipped,
        })
    if not dry_run:
        db.commit()
    result["batch_id"] = batch_id
    return result


# ─────────────────────────── auto-distribute (separate rule) ───────────────────────────
def _team_leader_id(db, info):
    """The team-leader id that defines this agent's team. If the agent IS a team leader, it's
    their own id; otherwise it's their manager_id."""
    if not info:
        return None
    is_tl = (info.get("team_type") == "lead") or ((info.get("role") or "").lower() == "sales_manager")
    return info["id"] if is_tl else info.get("manager_id")


def _scope_targets(db, from_agent_id, scope, record_type="client"):
    """Targets for auto-distribute. TYPE-AWARE: leads go only to SALES agents, clients go only to
    RETENTION agents. internal = SAME TEAM (the team leader + their reports); external = other teams;
    all = company-wide. A team is defined by its team leader, so 'internal' for a TL = their own team."""
    info = agent_info(db, from_agent_id)
    tl_id = _team_leader_id(db, info)
    want_tt = "sales" if record_type == "lead" else "retention"
    rows = db.execute(text("""
        SELECT id, team_type, role, manager_id FROM users
        WHERE COALESCE(is_active,TRUE) AND id <> :me AND team_type = :tt
    """), {"me": from_agent_id, "tt": want_tt}).fetchall()
    out = []
    for rid, tt, role, mgr in rows:
        in_team = (mgr == tl_id) or (rid == tl_id)
        if scope == "internal" and not in_team:
            continue
        if scope == "external" and in_team:
            continue
        out.append(rid)
    return out


def auto_distribute(db, from_agent_id, record_type, scope, filters, reason, by_user, dry_run=False):
    """Evenly round-robin the matching records across the scope's agents, respecting client caps."""
    ensure_schema(db)
    keys = select_records(db, record_type, from_agent_id, filters)
    targets = _scope_targets(db, from_agent_id, scope, record_type)
    if not targets or not keys:
        return {"matched": len(keys), "targets": [], "dry_run": dry_run, "note": "no targets/records"}

    # round-robin assignment, skipping clients-capped agents
    buckets = {t: [] for t in targets}
    rem = {t: remaining_capacity(db, t) for t in targets} if record_type == "client" else {t: None for t in targets}
    order = list(targets)
    i = 0
    for k in keys:
        placed = False
        for _ in range(len(order)):
            t = order[i % len(order)]; i += 1
            if record_type == "client" and rem[t] is not None and len(buckets[t]) >= rem[t]:
                continue
            buckets[t].append(k); placed = True; break
        if not placed:
            break  # everyone capped
    batch_id = f"auto{from_agent_id}_{scope}_{record_type}_{len(keys)}"
    out = []
    for t, ks in buckets.items():
        if not ks:
            continue
        info = agent_info(db, t)
        moved = 0 if dry_run else reassign(db, record_type, ks, t, by_user, reason, batch_id, commit=False)
        out.append({"agent_id": t, "agent": info["name"] if info else f"#{t}",
                    "assigned": len(ks) if dry_run else moved})
    if not dry_run:
        db.commit()
    return {"matched": len(keys), "scope": scope, "targets": out, "dry_run": dry_run, "batch_id": batch_id}


# ─────────────────────────── transfer-out (request to manager) ───────────────────────────
def transfer_out(db, record_type, record_key, by_user, reason=""):
    """'Transfer out of my data' (hybrid): immediately move the record UP to the requester's manager
    (so it leaves their working list) AND log a pending request the manager resolves by reassigning
    it down to an under-cap agent. Returns {moved_to_manager, request_id}."""
    ensure_schema(db)
    me = agent_info(db, getattr(by_user, "id", None))
    mgr_id = me["manager_id"] if me else None
    if not mgr_id:
        # no manager (e.g. director) — nothing above; just record the request unresolved
        rid = db.execute(text("""INSERT INTO transfer_requests
            (record_type,record_key,from_agent_id,requested_by_id,requested_by_name,manager_id,reason)
            VALUES (:rt,:rk,:me,:me,:bn,NULL,:rs) RETURNING id"""),
            {"rt": record_type, "rk": int(record_key), "me": getattr(by_user, "id", None),
             "bn": getattr(by_user, "full_name", "") or "", "rs": reason}).scalar()
        db.commit()
        return {"moved_to_manager": None, "request_id": rid}
    # move it up to the manager (leaves my list immediately)
    reassign(db, record_type, [record_key], mgr_id, by_user, reason or "transfer-out request", commit=False)
    rid = db.execute(text("""INSERT INTO transfer_requests
        (record_type,record_key,from_agent_id,requested_by_id,requested_by_name,manager_id,reason)
        VALUES (:rt,:rk,:me,:me,:bn,:mgr,:rs) RETURNING id"""),
        {"rt": record_type, "rk": int(record_key), "me": getattr(by_user, "id", None),
         "bn": getattr(by_user, "full_name", "") or "", "mgr": mgr_id, "rs": reason}).scalar()
    db.commit()
    return {"moved_to_manager": mgr_id, "request_id": rid}


# ─────────────────────────── auto sales→retention on first deposit ───────────────────────────
def auto_retention_handover(db, by_user=None, dry_run=False, limit=5000):
    """Find clients currently on a SALES agent who have deposited, and reassign each to a RETENTION
    agent in the SAME team with the most remaining capacity (under the 1000 cap). Logs + comments."""
    ensure_schema(db)
    # clients on a sales agent, with a deposit
    rows = db.execute(text("""
        SELECT c.login, u.manager_id
        FROM clients c JOIN users u ON u.id = c.assigned_agent_id
        WHERE u.team_type = 'sales' AND COALESCE(c.total_deposits,0) > 0
        LIMIT :lim
    """), {"lim": limit}).fetchall()
    if not rows:
        return {"candidates": 0, "moved": 0, "dry_run": dry_run, "by_team": []}

    # retention agents per team (manager) with remaining capacity
    ret = db.execute(text("""
        SELECT u.id, u.manager_id, COALESCE(cc.n,0)
        FROM users u
        LEFT JOIN (SELECT assigned_agent_id aid, COUNT(DISTINCT customer_no) n FROM clients GROUP BY assigned_agent_id) cc ON cc.aid=u.id
        WHERE u.team_type='retention' AND COALESCE(u.is_active,TRUE)
    """)).fetchall()
    team_ret = {}   # manager_id -> [ [agent_id, load], ... ]
    for aid, mgr, load in ret:
        team_ret.setdefault(mgr, []).append([aid, load or 0])

    class _Sys:  # synthetic actor for the log when called by a job
        id = getattr(by_user, "id", None) if by_user else None
        full_name = getattr(by_user, "full_name", None) if by_user else "Auto (deposit→retention)"

    moved, by_team = 0, {}
    for login, mgr in rows:
        cands = team_ret.get(mgr)
        if not cands:
            continue  # team has no retention agent — leave on sales
        # pick the retention agent with the most remaining capacity (lowest load, under cap)
        cands.sort(key=lambda x: x[1])
        pick = next((c for c in cands if c[1] < CAP_RETENTION), None)
        if not pick:
            continue  # all retention in this team at cap
        if not dry_run:
            reassign(db, "client", [login], pick[0], _Sys, "auto handover: deposited → retention", commit=False)
        pick[1] += 1
        moved += 1
        by_team[mgr] = by_team.get(mgr, 0) + 1
    if not dry_run:
        db.commit()
    return {"candidates": len(rows), "moved": moved, "dry_run": dry_run,
            "by_team": [{"manager_id": k, "moved": v} for k, v in by_team.items()]}
