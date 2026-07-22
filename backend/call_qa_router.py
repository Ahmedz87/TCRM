"""
call_qa_router.py — API for the per-call QA report cards written by call_qa_engine.py.

GET /call-qa/reports        list (filters: agent, priority, date range, search) + KPI counts
GET /call-qa/reports/{id}   full report incl. transcript, coaching, and the customer's
                            previous scored calls (`history`)
GET /call-qa/agents         distinct agents seen in call_qa (for the filter dropdown)

VISIBILITY: staff-only (get_current_user). Users with role='sales_agent' see ONLY their
own calls — matched by users.extension against call_qa.agent_ext, falling back to a
full_name match against agent_name. Managers/admins/back-office see everything.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/call-qa", tags=["Call QA"])

_PRIORITIES = ("critical", "urgent", "medium", "normal")


def _table_exists(db):
    return db.execute(text("SELECT to_regclass('public.call_qa')")).scalar() is not None


def _scope_filter(db, user, own=False):
    """(clause, params) restricting call_qa rows to what `user` may see.
    - all-access roles (admin/director/backoffice/…) -> everything
    - team leader / sales manager -> the TEAM's calls (their subtree's extensions/names),
      or just their OWN when own=True (the "My own data" toggle)
    - sales agent -> own calls only
    call_qa links by PBX extension (agent_ext) + agent_name, so we resolve the visible user
    ids to their extensions + names and match on those.
    """
    import rbac
    ids = rbac.scope_agent_ids(db, user, section="calls", own=own)
    if ids is None:
        return "1=1", {}          # full access
    if not ids:
        return "1=0", {}          # restricted / sees nothing
    rows = db.execute(text("SELECT extension, full_name FROM users WHERE id = ANY(:ids)"),
                      {"ids": ids}).fetchall()
    exts  = sorted({(r[0] or "").strip() for r in rows if (r[0] or "").strip()})
    names = sorted({(r[1] or "").strip() for r in rows if (r[1] or "").strip()})
    clauses, params = [], {}
    if exts:
        clauses.append("agent_ext = ANY(:qa_exts)"); params["qa_exts"] = exts
    if names:
        # CASE-INSENSITIVE match (PBX agent_name casing differs from users.full_name, e.g.
        # 'Ali Mohamed saleh' vs 'Ali Mohamed Saleh') — restores the old ILIKE-equality behaviour
        # for agents who have no extension and are matched by name.
        clauses.append("LOWER(agent_name) = ANY(:qa_names)"); params["qa_names"] = [n.lower() for n in names]
    if not clauses:
        return "1=0", {}          # a leader with no extension/name on file -> nothing (safe)
    return "(" + " OR ".join(clauses) + ")", params


def _own_filter(user):  # back-compat shim (unused db-less callers)
    return "1=1", {}


@router.get("/reports")
def list_reports(
    agent: str = Query("", description="agent_ext or part of agent_name"),
    priority: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    search: str = Query(""),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    own: int = Query(0),          # 1 = team leader's "My own data" toggle (self only, not team)
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _table_exists(db):
        return {"reports": [], "counts": {p: 0 for p in _PRIORITIES}, "total": 0}

    own_clause, params = _scope_filter(db, user, own=bool(own))
    where = [own_clause]
    if agent:
        where.append("(agent_ext = :agent OR agent_name ILIKE :agent_like)")
        params["agent"] = agent
        params["agent_like"] = f"%{agent}%"
    if priority in _PRIORITIES:
        where.append("priority = :priority")
        params["priority"] = priority
    if date_from:
        where.append("call_time >= :dfrom")
        params["dfrom"] = date_from
    if date_to:
        where.append("call_time < (CAST(:dto AS date) + 1)")
        params["dto"] = date_to
    if search:
        # Deep search: phone / customer name / summary directly on call_qa, account number
        # (client_login), and email / name resolved through clients+leads (matched back to
        # calls by last-9 phone digits — same linkage auto_match uses).
        import re as _re
        s = search.strip()
        digits = _re.sub(r"\D", "", s)
        numeric = len(digits) >= 5          # only treat as phone/account # when mostly a number
        sub = ["customer_number ILIKE :q", "client_name ILIKE :q",
               "agent_name ILIKE :q", "summary ILIKE :q"]
        params["q"] = f"%{s}%"
        if numeric:
            sub.append("REGEXP_REPLACE(customer_number, '\\D', '', 'g') LIKE :qd")
            sub.append("client_login::TEXT LIKE :qd")
            params["qd"] = f"%{digits}%"
        sub.append("""RIGHT(REGEXP_REPLACE(customer_number, '\\D', '', 'g'), 9) IN (
            SELECT RIGHT(REGEXP_REPLACE(c.phone, '\\D', '', 'g'), 9) FROM clients c
            WHERE (c.email ILIKE :q OR c.name ILIKE :q OR c.login::TEXT = :qxact)
              AND COALESCE(c.phone, '') <> ''
            UNION
            SELECT RIGHT(REGEXP_REPLACE(l.phone, '\\D', '', 'g'), 9) FROM leads l
            WHERE (l.email ILIKE :q OR l.full_name ILIKE :q)
              AND COALESCE(l.phone, '') <> ''
        )""")
        params["qxact"] = digits if numeric else s
        where.append("(" + " OR ".join(sub) + ")")
    w = " AND ".join(where)

    counts = {p: 0 for p in _PRIORITIES}
    for p, n in db.execute(text(
            f"SELECT priority, COUNT(*) FROM call_qa WHERE {w} GROUP BY priority"), params):
        if p in counts:
            counts[p] = n
    total = sum(counts.values())

    unread = db.execute(text(
        f"SELECT COUNT(*) FROM call_qa WHERE {w} AND read_at IS NULL"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT q.id, q.recording_id, q.call_time, q.agent_ext, q.agent_name,
               q.customer_number, q.direction, q.duration, q.client_login,
               q.client_name, q.contact_type, q.summary, q.analysis, q.outcome,
               q.score, q.priority, q.strengths, q.weaknesses, q.recommendation, q.flags,
               q.coaching, q.read_at, q.read_by,
               (SELECT COUNT(*) FROM call_qa p
                WHERE p.customer_number = q.customer_number AND p.id <> q.id) AS prev_calls
        FROM call_qa q WHERE {w}
        ORDER BY CASE q.priority WHEN 'critical' THEN 0 WHEN 'urgent' THEN 1
                                 WHEN 'medium' THEN 2 ELSE 3 END,
                 q.call_time DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}).mappings().all()

    return {"reports": [dict(r) for r in rows], "counts": counts, "total": total,
            "unread": unread, "restricted": own_clause != "1=1"}


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Full report (incl. coaching) + `history`: every other scored call with the same
    customer number (newest first) so the desk can walk the whole relationship."""
    if not _table_exists(db):
        raise HTTPException(404, "no reports yet")
    own_clause, params = _scope_filter(db, user)
    row = db.execute(text(f"SELECT * FROM call_qa WHERE id = :id AND {own_clause}"),
                     {**params, "id": report_id}).mappings().first()
    if not row:
        raise HTTPException(404, "report not found")
    out = dict(row)
    out["history"] = [dict(h) for h in db.execute(text(f"""
        SELECT id, call_time, agent_name, direction, duration, score, priority,
               outcome, summary
        FROM call_qa
        WHERE customer_number = :num AND id <> :id AND {own_clause}
        ORDER BY call_time DESC LIMIT 50
    """), {**params, "num": row["customer_number"], "id": report_id}).mappings().all()]
    return out


@router.post("/reports/{report_id}/read")
def mark_read(report_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """The agent (or a manager) confirms they read & understood the report card."""
    if not _table_exists(db):
        raise HTTPException(404, "no reports yet")
    own_clause, params = _scope_filter(db, user)
    reader = getattr(user, "full_name", None) or getattr(user, "email", "staff")
    row = db.execute(text(f"""
        UPDATE call_qa SET read_at = COALESCE(read_at, NOW()),
                           read_by = COALESCE(read_by, :reader)
        WHERE id = :id AND {own_clause}
        RETURNING id, read_at, read_by
    """), {**params, "id": report_id, "reader": reader}).mappings().first()
    db.commit()
    if not row:
        raise HTTPException(404, "report not found")
    return dict(row)


@router.get("/agents")
def list_agents(own: int = Query(0), db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not _table_exists(db):
        return []
    own_clause, params = _scope_filter(db, user, own=bool(own))
    rows = db.execute(text(f"""
        SELECT agent_ext, agent_name, COUNT(*) AS calls,
               ROUND(AVG(score), 1) AS avg_score,
               COUNT(*) FILTER (WHERE priority IN ('critical','urgent')) AS needs_review
        FROM call_qa
        WHERE {own_clause}
        GROUP BY agent_ext, agent_name
        ORDER BY calls DESC
    """), params).mappings().all()
    return [dict(r) for r in rows]
