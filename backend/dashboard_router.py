"""
dashboard_router.py â€” Real-time KPIs for the dashboard
Supports period filtering: today, this_week, this_month, last_month, this_year, last_year, all_time
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, date, timedelta
from database import get_db
from auth import get_current_user
from perf_cache import cached
import models

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_period_dates(period: str):
    today = date.today()
    if period == "today":
        return today.isoformat(), today.isoformat()
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat()
    elif period == "this_month":
        return today.replace(day=1).isoformat(), today.isoformat()
    elif period == "last_month":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        return start.isoformat(), end.isoformat()
    elif period == "this_year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    elif period == "last_year":
        y = today.year - 1
        return f"{y}-01-01", f"{y}-12-31"
    else:  # all_time
        return "2000-01-01", today.isoformat()


@router.get("/kpis")
def get_dashboard_kpis(
    period: str = Query("all_time"),
    agent: str = Query(""),            # optional sales-agent NAME filter (matches the Transactions page)
    date_from: str = Query(""),        # optional explicit window (overrides the period preset)
    date_to: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ── Role scoping: agent -> own clients; manager -> team; director/admin -> all ──
    _agent_ids = _scope_agent_ids(db, current_user)
    # Optional explicit sales-agent filter (by name) — narrow the KPIs to that agent's clients so the
    # cards match the Transactions table when a sales agent is selected. Resolved by full_name ILIKE
    # (same match the transactions list uses); intersected with the caller's role scope.
    if agent.strip():
        ids = db.execute(text("SELECT COALESCE(array_agg(id),'{}') FROM users WHERE full_name ILIKE :a"),
                         {"a": f"%{agent.strip()}%"}).scalar() or []
        ids = list(ids)
        _agent_ids = (ids or [-1]) if _agent_ids is None else ([i for i in ids if i in set(_agent_ids)] or [-1])
    scope = "all" if _agent_ids is None else "a:" + ",".join(map(str, sorted(_agent_ids)))
    return cached(f"dash:kpis:{period}:{date_from}:{date_to}:{scope}", 60,
                  lambda: _build_dashboard_kpis(period, db, _agent_ids, date_from, date_to))


# Genuine client deposit only — exclude internal MT balance adjustments (method='MT5' or an internal
# label) so the KPI cards / tab counts match the Deposits list + Finance (same rule everywhere).
_DEP = (r"t.tx_type='deposit' AND COALESCE(t.method,'') <> 'MT5' "
        r"AND COALESCE(t.method,'') !~* '(deposit\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance"
        r"|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back|credit\s*(in|out)|bonus\s*adjustment)'")
# Real withdrawal only — exclude REJECTED (a rejected withdrawal was reverted/refunded, so it never left).
_WD = "t.tx_type='withdrawal' AND COALESCE(t.status,'') <> 'rejected'"


def _build_dashboard_kpis(period: str, db: Session, _agent_ids, date_from: str = "", date_to: str = ""):
    p_from, p_to = get_period_dates(period)
    # explicit window (from the Transactions date pickers) overrides the period preset
    if date_from: p_from = date_from
    if date_to:   p_to   = date_to
    # index-friendly date boundaries (compare the RAW indexed column to 'YYYY-MM-DD' strings;
    # never wrap the column in ::date — that defeats the tx_date/created_at indexes). End-day
    # INCLUSIVE is preserved via `< next-day`.
    p_to_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    d3        = (date.fromisoformat(p_to) - timedelta(days=3)).isoformat()       # last-3-days lower bound
    d14       = (date.today() - timedelta(days=14)).isoformat()
    today_s   = date.today().isoformat()
    tom_s     = (date.today() + timedelta(days=1)).isoformat()
    yr_start  = f"{date.today().year}-01-01"
    yr_next   = f"{date.today().year + 1}-01-01"

    base = {"f": p_from, "t": p_to, "tnext": p_to_next, "d3": d3, "d14": d14,
            "today_s": today_s, "tom_s": tom_s, "yr_start": yr_start, "yr_next": yr_next}
    if _agent_ids is None:
        base_p = dict(base)
        TJOIN = ""                                  # transactions: no client join needed
        TX    = ""                                  # transactions extra filter
        CL    = ""                                  # clients extra filter
    else:
        base_p = dict(base, aids=_agent_ids)
        TJOIN = "JOIN clients c ON c.login = t.login"
        TX    = " AND c.assigned_agent_id = ANY(:aids) "
        CL    = " AND assigned_agent_id = ANY(:aids) "

    # ── Period transactions: ONE conditional-aggregation scan instead of ~6 separate ones.
    # Covers deposits (sum/count), withdrawals (sum/count), bonus given, transfer count,
    # bonus count, and active traders — all over the SAME [:f, :tnext) range + role scope. ──
    per = db.execute(text(f"""
        SELECT
          COALESCE(SUM(t.amount) FILTER (WHERE {_DEP}),0)                        AS dep_sum,
          COUNT(*)                FILTER (WHERE {_DEP})                          AS dep_cnt,
          COALESCE(SUM(t.amount) FILTER (WHERE {_WD}),0)                         AS wth_sum,
          COUNT(*)                FILTER (WHERE {_WD})                           AS wth_cnt,
          COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='bonus_deposit'),0)      AS bonus_sum,
          COUNT(*)                FILTER (WHERE t.tx_type='internal_transfer')    AS transfer_cnt,
          COUNT(*)                FILTER (WHERE t.tx_type IN ('bonus_deposit','bonus_withdrawal')) AS bonus_cnt,
          COUNT(DISTINCT t.login) FILTER (WHERE {_DEP})                          AS active_traders
        FROM transactions t {TJOIN}
        WHERE t.tx_date >= :f AND t.tx_date < :tnext {TX}
    """), base_p).fetchone()
    dep            = (per[0], per[1])      # (sum, count) — preserves old tuple-indexed reads
    wth            = (per[2], per[3])
    bonus          = per[4]
    transfer_count = per[5] or 0
    bonus_count    = per[6] or 0
    active_traders = per[7] or 0

    # Pending withdrawals (all time)
    pending_w = db.execute(text(f"""
        SELECT COUNT(*) FROM transactions t {TJOIN}
        WHERE t.tx_type = 'withdrawal' AND t.status IN ('pending','processing') {TX}
    """), base_p).scalar() or 0

    # New clients in period (first_deposit_at in period)
    new_clients = db.execute(text(f"""
        SELECT COUNT(DISTINCT login) FROM clients
        WHERE first_deposit_at IS NOT NULL AND first_deposit_at != ''
        AND first_deposit_at >= :f AND first_deposit_at < :tnext {CL}
    """), base_p).scalar() or 0

    # Total active clients (have balance > 0)
    active_clients = db.execute(text(f"""
        SELECT COUNT(DISTINCT login) FROM clients WHERE balance > 0 {CL}
    """), base_p).scalar() or 0

    # Total unique clients
    total_clients = db.execute(text(f"""
        SELECT COUNT(DISTINCT CASE
            WHEN phone IS NOT NULL AND phone != '' AND phone != '0' THEN phone
            ELSE CAST(login AS TEXT)
        END) FROM clients
        WHERE group_name NOT ILIKE '%retail%' {CL}
    """), base_p).scalar() or 0

    # Clients with no deposit in 14+ days
    no_dep_14 = db.execute(text(f"""
        SELECT COUNT(*) FROM clients
        WHERE balance > 0
        AND (last_deposit_at IS NULL OR last_deposit_at = '' OR last_deposit_at < :d14)
        AND group_name NOT ILIKE '%retail%' {CL}
    """), base_p).scalar() or 0

    # New leads this period (registered but no deposit)
    new_leads = db.execute(text(f"""
        SELECT COUNT(*) FROM clients
        WHERE created_at IS NOT NULL AND created_at >= :f AND created_at < :tnext
        AND total_deposits = 0
        AND group_name NOT ILIKE '%retail%' {CL}
    """), base_p).scalar() or 0

    # IB commission in period (not an agent-level KPI -> only for full-access roles)
    if _agent_ids is None:
        ib_comm = db.execute(text("""
            SELECT COALESCE(SUM(commission_usd), 0) FROM ib_commissions
            WHERE trade_date IS NOT NULL AND trade_date >= :f AND trade_date < :tnext
        """), {"f": p_from, "t": p_to, "tnext": p_to_next}).scalar() or 0
    else:
        ib_comm = 0

    # Total balance across all accounts
    total_balance = db.execute(text(f"""
        SELECT COALESCE(SUM(balance), 0) FROM clients
        WHERE group_name NOT ILIKE '%retail%' {CL}
    """), base_p).scalar() or 0

    # Total EQUITY snapshot at this point in time + the bonus(credit) that sits inside it (ticket #21/#22/#23).
    # equity excluding bonus = equity − the credit/bonus portion carried on funded accounts.
    eq = db.execute(text(f"""
        SELECT COALESCE(SUM(equity), 0) AS total_equity,
               COALESCE(SUM(CASE WHEN equity <> 0 THEN credit ELSE 0 END), 0) AS bonus_in_equity
        FROM clients
        WHERE group_name NOT ILIKE '%retail%' {CL}
    """), base_p).fetchone()
    total_equity     = float(eq[0] or 0)
    bonus_in_equity  = float(eq[1] or 0)
    equity_ex_bonus  = total_equity - bonus_in_equity

    # Last 3 days stats
    dep_3d = db.execute(text(f"""
        SELECT COALESCE(SUM(t.amount),0), COUNT(*) FROM transactions t {TJOIN}
        WHERE t.tx_type='deposit'
        AND t.tx_date >= :d3 {TX}
    """), dict(base_p, d=p_to)).fetchone()

    wth_3d = db.execute(text(f"""
        SELECT COALESCE(SUM(t.amount),0), COUNT(*) FROM transactions t {TJOIN}
        WHERE t.tx_type='withdrawal'
        AND t.tx_date >= :d3 {TX}
    """), dict(base_p, d=p_to)).fetchone()

    bonus_3d = db.execute(text(f"""
        SELECT COALESCE(SUM(t.amount),0), COUNT(*) FROM transactions t {TJOIN}
        WHERE t.tx_type='bonus_deposit'
        AND t.tx_date >= :d3 {TX}
    """), dict(base_p, d=p_to)).fetchone()

    # Today stats
    today_dep = db.execute(text(f"""
        SELECT COALESCE(SUM(t.amount),0) FROM transactions t {TJOIN}
        WHERE t.tx_type='deposit' AND t.tx_date >= :today_s AND t.tx_date < :tom_s {TX}
    """), base_p).scalar() or 0

    flagged_count = db.execute(text(f"""
        SELECT COUNT(DISTINCT t.login) FROM transactions t
        JOIN clients c ON c.login = t.login
        WHERE t.tx_type='withdrawal'
        AND t.tx_date >= :f AND t.tx_date < :tnext
        AND (SELECT COUNT(*) FROM network_edges ne WHERE ne.login_a=t.login OR ne.login_b=t.login) >= 6 {TX}
    """), base_p).scalar() or 0

    # Calls in period (scoped by role)
    if _agent_ids is None:
        calls_count = db.execute(text("""
            SELECT COUNT(*) FROM call_actions
            WHERE created_at >= :f AND created_at < :tnext
        """), {"f": p_from, "t": p_to, "tnext": p_to_next}).scalar() or 0
    else:
        calls_count = db.execute(text("""
            SELECT COUNT(*) FROM call_actions
            WHERE created_at >= :f AND created_at < :tnext
            AND agent_id = ANY(:aids)
        """), {"f": p_from, "t": p_to, "tnext": p_to_next, "aids": _agent_ids}).scalar() or 0

    # ── Whole-year totals (1 Jan – 31 Dec of the current year), regardless of the selected period (ticket #14).
    # Merged dep+wth into one FILTER scan over the same [:yr_start, :yr_next) range. ──
    yr = db.execute(text(f"""
        SELECT COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='deposit'),0)    AS year_dep,
               COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='withdrawal'),0) AS year_wth
        FROM transactions t {TJOIN}
        WHERE t.tx_date >= :yr_start AND t.tx_date < :yr_next {TX}
    """), base_p).fetchone()
    year_dep = yr[0] or 0
    year_wth = yr[1] or 0
    cur_year = int(db.execute(text("SELECT date_part('year', CURRENT_DATE)")).scalar() or 0)

    return {
        "period":          {"from": p_from, "to": p_to, "key": period},
        "year_label":      cur_year,
        "year_deposits":   float(year_dep or 0),
        "year_withdrawals":float(year_wth or 0),
        "year_net":        float((year_dep or 0) - (year_wth or 0)),
        "clients":         total_clients,
        "active_clients":  active_clients,
        "new_clients":     new_clients,
        "new_leads":       new_leads,
        "active_traders":  active_traders,
        "deposits":        float(dep[0] or 0),
        "deposit_count":   dep[1] or 0,
        "withdrawals":     float(wth[0] or 0),
        "withdrawal_count":wth[1] or 0,
        "net_deposit":     float((dep[0] or 0) - (wth[0] or 0)),
        "pending_w":       pending_w,
        "no_deposit_14d":  no_dep_14,
        "total_balance":   float(total_balance or 0),
        "total_equity":    total_equity,
        "equity_ex_bonus": equity_ex_bonus,
        "bonus_in_equity": bonus_in_equity,
        "ib_comm":         float(ib_comm or 0),
        "sales_comm":      0,
        "bonus":           float(bonus or 0),
        "transfer_count":  transfer_count,
        "bonus_count":     bonus_count,
        "flagged_count":   flagged_count,
        "deposit_3d":      float(dep_3d[0] or 0),
        "deposit_3d_count":dep_3d[1] or 0,
        "withdrawal_3d":   float(wth_3d[0] or 0),
        "withdrawal_3d_count":wth_3d[1] or 0,
        "bonus_3d":        float(bonus_3d[0] or 0),
        "bonus_3d_count":  bonus_3d[1] or 0,
        "today_amount":    float(today_dep or 0),
        "calls":           calls_count,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# ROLE SCOPING + TRENDS + LEADERBOARD + FUNNEL  (added for role-aware dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

def _scope_agent_ids(db, user):
    """Return list of agent ids this user may see, or None for 'all' (admin/director).
    Manager => self + ALL descendants (recursive). Delegates to rbac.py."""
    import rbac
    return rbac.scope_agent_ids(db, user)


def _agent_filter(agent_ids, col="c.assigned_agent_id"):
    if agent_ids is None:
        return "", {}
    if not agent_ids:
        return f" AND {col} = -1 ", {}
    return f" AND {col} = ANY(:agent_ids) ", {"agent_ids": agent_ids}


def _period_ts(period: str):
    """Datetime bounds (start, end) for trend/leaderboard/funnel queries."""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":      return today, now
    if period == "yesterday":  return today - timedelta(days=1), today
    if period == "last_7d":    return today - timedelta(days=7), now
    if period == "this_week":  return today - timedelta(days=today.weekday()), now
    if period == "this_month": return today.replace(day=1), now
    if period == "last_month":
        first = today.replace(day=1)
        return (first - timedelta(days=1)).replace(day=1), first
    if period == "last_3m":    return today - timedelta(days=90), now
    if period == "this_year":  return today.replace(month=1, day=1), now
    if period == "last_year":
        return today.replace(year=today.year-1, month=1, day=1), today.replace(month=1, day=1)
    return datetime(2018,1,1), now


def _scope_key(agent_ids):
    """Stable cache-scope token so role-scoped data never leaks between users."""
    return "all" if agent_ids is None else "a:" + ",".join(map(str, sorted(agent_ids)))


@router.get("/trends")
def get_trends(period: str = Query("last_7d"),
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    agent_ids = _scope_agent_ids(db, current_user)
    return cached(f"dash:trends:{period}:{_scope_key(agent_ids)}", 120,
                  lambda: _build_trends(period, db, agent_ids))


def _build_trends(period: str, db: Session, agent_ids):
    start, end = _period_ts(period)
    span = (end - start).days or 1
    bucket = "day" if span <= 60 else "month"
    fmt = "YYYY-MM-DD" if bucket == "day" else "YYYY-MM"
    af, ap = _agent_filter(agent_ids)
    p = {"start": start, "end": end, **ap}

    dep = db.execute(text(f"""
        SELECT to_char(date_trunc('{bucket}', NULLIF(t.tx_date,'')::timestamp), '{fmt}'), COALESCE(SUM(t.amount),0)
        FROM transactions t JOIN clients c ON c.login = t.login
        WHERE t.tx_type='deposit'
          AND NULLIF(t.tx_date,'')::timestamp >= :start AND NULLIF(t.tx_date,'')::timestamp < :end {af}
        GROUP BY 1 ORDER BY 1
    """), p).fetchall()
    wd = db.execute(text(f"""
        SELECT to_char(date_trunc('{bucket}', NULLIF(t.tx_date,'')::timestamp), '{fmt}'), COALESCE(SUM(t.amount),0)
        FROM transactions t JOIN clients c ON c.login = t.login
        WHERE t.tx_type='withdrawal'
          AND NULLIF(t.tx_date,'')::timestamp >= :start AND NULLIF(t.tx_date,'')::timestamp < :end {af}
        GROUP BY 1 ORDER BY 1
    """), p).fetchall()
    dep_map = {r[0]: float(r[1]) for r in dep}
    wd_map  = {r[0]: float(r[1]) for r in wd}
    keys = sorted(set(dep_map) | set(wd_map))
    return {"bucket": bucket, "series": [
        {"date": k, "deposits": dep_map.get(k,0), "withdrawals": wd_map.get(k,0)} for k in keys
    ]}


@router.get("/leaderboard")
def get_leaderboard(period: str = Query("this_month"),
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    agent_ids = _scope_agent_ids(db, current_user)
    return cached(f"dash:leaderboard:{period}:{_scope_key(agent_ids)}", 120,
                  lambda: _build_leaderboard(period, db, agent_ids))


def _build_leaderboard(period: str, db: Session, agent_ids):
    start, end = _period_ts(period)
    extra = ""
    params = {"start": start, "end": end}
    if agent_ids is not None:
        extra = " AND u.id = ANY(:agent_ids) "
        params["agent_ids"] = agent_ids
    rows = db.execute(text(f"""
        SELECT u.id, u.full_name,
               COALESCE(SUM(CASE WHEN t.tx_type='deposit' THEN t.amount ELSE 0 END),0) AS deposits,
               COUNT(DISTINCT CASE WHEN NULLIF(c.first_deposit_at,'') IS NOT NULL
                     AND NULLIF(c.first_deposit_at,'')::timestamp >= :start
                     AND NULLIF(c.first_deposit_at,'')::timestamp < :end THEN c.login END) AS new_clients
        FROM users u
        LEFT JOIN clients c ON c.assigned_agent_id = u.id
        LEFT JOIN transactions t ON t.login = c.login
             AND NULLIF(t.tx_date,'')::timestamp >= :start AND NULLIF(t.tx_date,'')::timestamp < :end
        WHERE u.role='sales_agent' {extra}
        GROUP BY u.id, u.full_name
        ORDER BY deposits DESC
        LIMIT 15
    """), params).fetchall()
    return {"leaderboard": [
        {"agent_id": r[0], "name": r[1], "deposits": float(r[2]), "new_clients": r[3]}
        for r in rows
    ]}


@router.get("/funnel")
def get_funnel(period: str = Query("this_month"),
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    agent_ids = _scope_agent_ids(db, current_user)
    return cached(f"dash:funnel:{period}:{_scope_key(agent_ids)}", 120,
                  lambda: _build_funnel(period, db, agent_ids))


def _build_funnel(period: str, db: Session, agent_ids):
    start, end = _period_ts(period)
    af, ap = _agent_filter(agent_ids, "l.assigned_agent_id")
    p = {"start": start, "end": end, **ap}
    total = db.execute(text(f"""
        SELECT COUNT(*) FROM leads l WHERE l.created_at >= :start AND l.created_at < :end {af}
    """), p).fetchone()[0]
    contacted = db.execute(text(f"""
        SELECT COUNT(*) FROM leads l WHERE l.created_at >= :start AND l.created_at < :end
          AND l.call_attempts > 0 {af}
    """), p).fetchone()[0]
    converted = db.execute(text(f"""
        SELECT COUNT(*) FROM leads l WHERE l.created_at >= :start AND l.created_at < :end
          AND l.converted_login IS NOT NULL {af}
    """), p).fetchone()[0]
    return {"total_leads": total, "contacted": contacted, "converted": converted,
            "conversion_rate": round(converted/total*100,1) if total else 0}


@router.get("/calls")
def get_calls(period: str = Query("this_month"),
              db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    agent_ids = _scope_agent_ids(db, current_user)
    return cached(f"dash:calls:{period}:{_scope_key(agent_ids)}", 120,
                  lambda: _build_calls(period, db, agent_ids))


def _build_calls(period: str, db: Session, agent_ids):
    start, end = _period_ts(period)
    caf, cap = _agent_filter(agent_ids, "agent_id")
    p = {"start": start, "end": end, **cap}
    total = db.execute(text(f"""
        SELECT COUNT(*) FROM call_actions
        WHERE created_at >= :start AND created_at < :end {caf}
    """), p).fetchone()[0]
    return {"calls": total}


# ── Comparison: current vs previous week / month / year (ticket #15) ──
def _compare_pair(gran: str):
    today = date.today()
    if gran == "week":
        cs = today - timedelta(days=today.weekday()); ce = today
        pe = cs - timedelta(days=1); ps = pe - timedelta(days=6)
        return ("This week", cs, ce), ("Last week", ps, pe)
    if gran == "year":
        cs = today.replace(month=1, day=1); ce = today
        y = today.year - 1
        return (str(today.year), cs, ce), (str(y), date(y, 1, 1), date(y, 12, 31))
    # month (default)
    cs = today.replace(day=1); ce = today
    pe = cs - timedelta(days=1); ps = pe.replace(day=1)
    return (cs.strftime("%b %Y"), cs, ce), (ps.strftime("%b %Y"), ps, pe)


@router.get("/compare")
def dashboard_compare(granularity: str = Query("month"),
                      db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    if granularity not in ("week", "month", "year"):
        granularity = "month"
    agent_ids = _scope_agent_ids(db, current_user)
    return cached(f"dash:compare:{granularity}:{_scope_key(agent_ids)}", 120,
                  lambda: _build_compare(granularity, db, agent_ids))


def _build_compare(granularity: str, db: Session, agent_ids):
    if agent_ids is None:
        TJOIN = ""; TX = ""; CL = ""; extra = {}
    else:
        TJOIN = "JOIN clients c ON c.login = t.login"
        TX = " AND c.assigned_agent_id = ANY(:aids) "
        CL = " AND assigned_agent_id = ANY(:aids) "
        extra = {"aids": agent_ids}

    def agg(f, t):
        p = dict(extra, f=f.isoformat(), t=t.isoformat(), tnext=(t + timedelta(days=1)).isoformat())
        dep = db.execute(text(f"""SELECT COALESCE(SUM(t.amount),0) FROM transactions t {TJOIN}
            WHERE t.tx_type='deposit' AND t.tx_date>=:f AND t.tx_date<:tnext {TX}"""), p).scalar() or 0
        wth = db.execute(text(f"""SELECT COALESCE(SUM(t.amount),0) FROM transactions t {TJOIN}
            WHERE t.tx_type='withdrawal' AND t.tx_date>=:f AND t.tx_date<:tnext {TX}"""), p).scalar() or 0
        nc = db.execute(text(f"""SELECT COUNT(DISTINCT login) FROM clients
            WHERE first_deposit_at IS NOT NULL AND first_deposit_at!=''
            AND first_deposit_at>=:f AND first_deposit_at<:tnext {CL}"""), p).scalar() or 0
        at = db.execute(text(f"""SELECT COUNT(DISTINCT t.login) FROM transactions t {TJOIN}
            WHERE t.tx_type='deposit' AND t.tx_date>=:f AND t.tx_date<:tnext {TX}"""), p).scalar() or 0
        return {"deposits": float(dep), "withdrawals": float(wth), "net": float(dep - wth),
                "new_clients": int(nc), "active_traders": int(at)}

    (cl, cf, ct), (pl, pf, pt) = _compare_pair(granularity)
    cur, prev = agg(cf, ct), agg(pf, pt)

    def pct(c, p):
        if p:
            return round((c - p) / abs(p) * 100, 1)
        return 100.0 if c > 0 else 0.0

    metrics = {k: {"current": cur[k], "previous": prev[k], "pct": pct(cur[k], prev[k])} for k in cur}
    return {"granularity": granularity, "current_label": cl, "previous_label": pl, "metrics": metrics}
