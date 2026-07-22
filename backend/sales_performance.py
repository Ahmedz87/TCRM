"""
sales_performance.py — monthly PERFORMANCE SCORE (0-100%) per sales/retention agent, and the
ELIGIBLE COMMISSION = commission × performance%.

The desk grades each agent monthly on weighted KPIs (weights/targets editable in crm_settings):
  • own NDA acquired         target 5    weight 30%   (genuinely-new deposits they brought)
  • active IBs               target 3    weight 30%   (their IBs that traded this month)
  • successful calls ≥80s    target 1000 weight 30%   (call_actions.duration_seconds >= 80)
  • Call-QA score            (0-100)     weight 10%   (avg call_qa.score for their extension)
Each metric scores min(1, actual/target) × weight; QA scores (avg/100) × weight. Sum = 0..100.

DEMO MONTH: the CURRENT month is seeded with a demo score in [70,85] (deterministic per agent)
and flagged demo=True — the desk asked to preview the mechanic before the real targets go live.
Any OTHER (past) month computes the real score from the metrics above.

    perf(db, agent_id, team_type, period_key, p_from, p_to_next) -> {score, demo, eligible_pct, breakdown[...]}
    perf_all(db, agents, period_key, p_from, p_to_next)          -> {agent_id: {...}}
"""
from sqlalchemy import text
import crm_settings as CFG

# defaults (overridable via crm_settings keys perf_w_* / perf_t_*)
DEF = {
    "perf_w_nda": 30, "perf_w_ib": 30, "perf_w_calls": 30, "perf_w_qa": 10,
    "perf_t_nda": 5,  "perf_t_ib": 3,  "perf_t_calls": 1000,
}


def _team_key(team):
    # team leaders/managers ('lead') are scored on the RETENTION rule set
    return "retention" if team in ("retention", "lead") else "sales"


def team_cfg(db, team):
    """The GENERAL rules for a team (sales | retention). Stored as crm_settings '<key>_<team>',
    falling back to the hardcoded DEF."""
    tk = _team_key(team)
    return {k: CFG.get_float(db, f"{k}_{tk}", v) for k, v in DEF.items()}


def agent_overrides(db, agent_id):
    """Individual per-agent scoring overrides (empty = none). These WIN over the team general rule."""
    out = {}
    try:
        for k, v in db.execute(text("SELECT key, val FROM agent_scoring_rules WHERE agent_id=:a"),
                               {"a": agent_id}).fetchall():
            out[k] = float(v)
    except Exception:
        db.rollback()
    return out


def _cfg(db, team, agent_id=None):
    """Effective rules for an agent: individual override > team general > default."""
    base = team_cfg(db, team)
    if agent_id is not None:
        base.update(agent_overrides(db, agent_id))
    return base


def _is_current_month(period_key, p_from):
    from crm_tz import today_local
    t = today_local()
    return period_key in ("this_month", "custom", "") and str(p_from)[:7] == t.isoformat()[:7]


def _metrics(db, agent_id, p_from, p_to_next):
    """Raw monthly metrics for one agent."""
    # own NDA acquired (same acquirer attribution as sales_commission)
    nda = db.execute(text("""
        WITH origin AS (
            SELECT DISTINCT ON (l.customer_no) l.customer_no, l.assigned_agent_id AS la
            FROM leads l WHERE l.customer_no IS NOT NULL AND l.assigned_agent_id IS NOT NULL
            ORDER BY l.customer_no, l.created_at, l.id),
        cust AS (
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.assigned_agent_id AS cur_aid,
                   c.is_nda, NULLIF(c.first_deposit_at,'') AS fda
            FROM clients c WHERE c.customer_no IS NOT NULL AND c.is_nda IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC NULLS LAST, c.login)
        SELECT COUNT(*) FROM cust
        LEFT JOIN origin ON origin.customer_no = cust.customer_no
        WHERE cust.is_nda AND cust.fda >= :f AND cust.fda < :t
          AND COALESCE(origin.la, cust.cur_aid) = :id
    """), {"id": agent_id, "f": p_from, "t": p_to_next}).scalar() or 0

    # active IBs — the agent's IBs whose clients traded this month
    active_ib = db.execute(text("""
        SELECT COUNT(DISTINCT i.id)
        FROM ibs i JOIN clients c ON c.login = i.agent_id
        WHERE c.assigned_agent_id = :id AND EXISTS (
            SELECT 1 FROM deals d JOIN clients cc ON cc.login = d.login
            WHERE cc.agent = i.agent_id AND d.action IN (0,1)
              AND d.deal_date <> '' AND d.deal_date >= :f AND d.deal_date < :t)
    """), {"id": agent_id, "f": p_from, "t": p_to_next}).scalar() or 0

    # successful calls (>= 80s) this month — from the ANALYZED recordings (call_qa.duration, the
    # reliable source) matched by the agent's extension, plus logged call_actions; take the larger.
    calls_ca = db.execute(text("""
        SELECT COUNT(*) FROM call_actions
        WHERE agent_id = :id AND COALESCE(duration_seconds,0) >= 80
          AND created_at >= :f AND created_at < :t
    """), {"id": agent_id, "f": p_from, "t": p_to_next}).scalar() or 0
    calls_qa = db.execute(text("""
        SELECT COUNT(*) FROM call_qa q JOIN users u ON u.id = :id
        WHERE COALESCE(q.duration,0) >= 80 AND q.agent_ext = u.extension
          AND q.call_time >= :f AND q.call_time < :t
    """), {"id": agent_id, "f": p_from, "t": p_to_next}).scalar() or 0
    calls = max(int(calls_ca), int(calls_qa))

    # Call-QA average score (0-10 scale in this DB) matched by the agent's extension
    qa = db.execute(text("""
        SELECT AVG(q.score)::float
        FROM call_qa q JOIN users u ON u.id = :id
        WHERE q.score IS NOT NULL AND q.agent_ext = u.extension
          AND q.call_time >= :f AND q.call_time < :t
    """), {"id": agent_id, "f": p_from, "t": p_to_next}).scalar()
    return {"nda": int(nda), "active_ib": int(active_ib), "calls": calls,
            "qa_score": round(qa, 1) if qa is not None else None}


def _demo_pct(agent_id, team_type=""):
    """Deterministic demo score (no RNG — stable across reloads). Retention/leads 65-85, sales 70-85."""
    if _team_key(team_type) == "retention":
        return 65 + (agent_id * 7 + 3) % 21     # 65..85
    return 70 + (agent_id * 7 + 3) % 16          # 70..85


def _metrics_all(db, aids, p_from, p_to_next):
    """Batched metrics for MANY agents in a handful of grouped queries (replaces the per-agent
    N+1 that re-scanned leads/clients/deals for every agent — ~29s on the Sales Agents page)."""
    P = {"f": p_from, "t": p_to_next}
    # own NDA acquired per agent (origin/cust computed ONCE, grouped by the attributed agent)
    nda = {r[0]: int(r[1]) for r in db.execute(text("""
        WITH origin AS (
            SELECT DISTINCT ON (l.customer_no) l.customer_no, l.assigned_agent_id AS la
            FROM leads l WHERE l.customer_no IS NOT NULL AND l.assigned_agent_id IS NOT NULL
            ORDER BY l.customer_no, l.created_at, l.id),
        cust AS (
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.assigned_agent_id AS cur_aid,
                   c.is_nda, NULLIF(c.first_deposit_at,'') AS fda
            FROM clients c WHERE c.customer_no IS NOT NULL AND c.is_nda IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC NULLS LAST, c.login)
        SELECT COALESCE(origin.la, cust.cur_aid) AS aid, COUNT(*)
        FROM cust LEFT JOIN origin ON origin.customer_no = cust.customer_no
        WHERE cust.is_nda AND cust.fda >= :f AND cust.fda < :t
        GROUP BY 1
    """), P).fetchall()}
    # IB agent-codes whose referred clients traded in the period (from the fast rollup)
    traded_ibs = {r[0] for r in db.execute(text("""
        SELECT DISTINCT cc.agent FROM clients cc JOIN deals_login_daily m ON m.login = cc.login
        WHERE m.day >= :f AND m.day < :t AND COALESCE(cc.agent,0) > 0
    """), P).fetchall()}
    # each sales agent's active IBs = their IBs whose code is in traded_ibs
    active_ib = {}
    for aid, ibid, ib_agent in db.execute(text("""
        SELECT c.assigned_agent_id AS aid, i.id AS ibid, i.agent_id AS ib_agent
        FROM ibs i JOIN clients c ON c.login = i.agent_id WHERE c.assigned_agent_id IS NOT NULL
    """)).fetchall():
        if ib_agent in traded_ibs:
            active_ib.setdefault(aid, set()).add(ibid)
    # calls >=80s from call_actions, and from analyzed call_qa (matched by extension)
    ca = {r[0]: int(r[1]) for r in db.execute(text("""
        SELECT agent_id, COUNT(*) FROM call_actions
        WHERE COALESCE(duration_seconds,0) >= 80 AND created_at >= :f AND created_at < :t
        GROUP BY 1"""), P).fetchall()}
    ext = {r[0]: (int(r[1] or 0), (round(float(r[2]),1) if r[2] is not None else None))
           for r in db.execute(text("""
        SELECT u.id, COUNT(*) FILTER (WHERE COALESCE(q.duration,0) >= 80),
               AVG(q.score) FILTER (WHERE q.score IS NOT NULL)
        FROM users u JOIN call_qa q ON q.agent_ext = u.extension
        WHERE q.call_time >= :f AND q.call_time < :t GROUP BY u.id"""), P).fetchall()}
    out = {}
    for aid in aids:
        qc, qs = ext.get(aid, (0, None))
        out[aid] = {"nda": nda.get(aid, 0), "active_ib": len(active_ib.get(aid, ())),
                    "calls": max(ca.get(aid, 0), qc), "qa_score": qs}
    return out


def perf(db, agent_id, team_type, period_key, p_from, p_to_next, _m=None):
    w = _cfg(db, team_type, agent_id)
    m = _m if _m is not None else _metrics(db, agent_id, p_from, p_to_next)
    parts = [
        ("nda",   "Own NDA",          m["nda"],       w["perf_t_nda"],   w["perf_w_nda"]),
        ("ib",    "Active IBs",       m["active_ib"], w["perf_t_ib"],    w["perf_w_ib"]),
        ("calls", "Calls ≥80s",       m["calls"],     w["perf_t_calls"], w["perf_w_calls"]),
    ]
    breakdown = []
    real = 0.0
    for key, label, actual, target, weight in parts:
        got = min(1.0, actual / target) * weight if target else 0.0
        breakdown.append({"key": key, "label": label, "actual": actual, "target": target,
                          "weight": weight, "points": round(got, 1)})
        real += got
    qa = m["qa_score"]
    qa_pts = (qa / 10.0) * w["perf_w_qa"] if qa is not None else 0.0   # call_qa.score is 0-10
    breakdown.append({"key": "qa", "label": "Call-QA score", "actual": qa if qa is not None else 0,
                      "target": 10, "weight": w["perf_w_qa"], "points": round(qa_pts, 1)})
    real += qa_pts
    real = round(min(100.0, real), 1)

    demo = _is_current_month(period_key, p_from)
    if demo:
        score = float(_demo_pct(agent_id, team_type))
    else:
        # a full calendar month in the past → use the FROZEN snapshot if one exists
        snap = None
        pf = str(p_from)
        if pf.endswith("-01") and period_key in ("last_month", "frozen", "custom", ""):
            snap = _snapshot_score(db, agent_id, pf[:7])
        score = snap if snap is not None else real
    return {"score": score, "demo": demo, "real_score": real,
            "breakdown": breakdown, "metrics": m}


def ensure_snap(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS perf_snapshots (
        agent_id INT, month VARCHAR(7), score FLOAT, metrics JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW(), PRIMARY KEY (agent_id, month))"""))
    db.commit()


def _snapshot_score(db, agent_id, month):
    try:
        r = db.execute(text("SELECT score FROM perf_snapshots WHERE agent_id=:a AND month=:m"),
                       {"a": agent_id, "m": month}).fetchone()
        return float(r[0]) if r else None
    except Exception:
        db.rollback(); return None


def freeze_month(db, month):
    """Compute and STORE the final real score for every sales/retention agent for `month`
    (YYYY-MM). Run at month-end so past eligible-commission never drifts. Idempotent (upsert)."""
    import calendar
    ensure_snap(db)
    y, mo = map(int, month.split("-"))
    p_from = f"{month}-01"
    last = calendar.monthrange(y, mo)[1]
    p_to_next = f"{month}-{last:02d}"
    from datetime import date, timedelta
    p_to_next = (date(y, mo, last) + timedelta(days=1)).isoformat()
    agents = db.execute(text(
        "SELECT id, team_type FROM users WHERE team_type IN ('sales','retention','lead')")).fetchall()
    n = 0
    for aid, tt in agents:
        p = perf(db, aid, tt or "", "frozen", p_from, p_to_next)   # not current -> real score
        db.execute(text("""INSERT INTO perf_snapshots (agent_id, month, score, metrics)
            VALUES (:a,:m,:s,:mj) ON CONFLICT (agent_id, month)
            DO UPDATE SET score=EXCLUDED.score, metrics=EXCLUDED.metrics, created_at=NOW()"""),
            {"a": aid, "m": month, "s": p["real_score"],
             "mj": __import__("json").dumps(p["metrics"])})
        n += 1
    db.commit()
    return {"month": month, "frozen": n}


def perf_all(db, agents, period_key, p_from, p_to_next):
    aids = [a["id"] if isinstance(a, dict) else a for a in agents]
    mall = _metrics_all(db, aids, p_from, p_to_next)   # one batched pass, not per-agent N+1
    out = {}
    for a in agents:
        aid = a["id"] if isinstance(a, dict) else a
        tt = (a.get("team") or a.get("team_type") or "") if isinstance(a, dict) else ""
        out[aid] = perf(db, aid, tt, period_key, p_from, p_to_next, _m=mall.get(aid))
    return out


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from database import SessionLocal
    from ib_router import period_dates
    from datetime import datetime, timedelta
    db = SessionLocal()
    try:
        pf, pt = period_dates("this_month", "", "")
        ptn = (datetime.strptime(pt, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        rows = db.execute(text("SELECT id, full_name, team_type FROM users WHERE team_type IN ('sales','retention') LIMIT 8")).fetchall()
        for aid, name, tt in rows:
            p = perf(db, aid, tt, "this_month", pf, ptn)
            print(f"{name[:22]:24} score={p['score']}% demo={p['demo']} real={p['real_score']}  "
                  f"nda={p['metrics']['nda']} ib={p['metrics']['active_ib']} calls={p['metrics']['calls']} qa={p['metrics']['qa_score']}")
    finally:
        db.close()
