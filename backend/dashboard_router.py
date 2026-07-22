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
    # "today" = IRAQ's today (UTC+3), not the UTC box clock — see crm_tz.
    from crm_tz import today_local
    today = today_local()
    if period == "today":
        return today.isoformat(), today.isoformat()
    elif period == "yesterday":
        y = today - timedelta(days=1)
        return y.isoformat(), y.isoformat()
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat()
    elif period == "last_week":
        # Mon..Sun of the previous week (was MISSING — silently fell through to all_time,
        # so the Clients-page "Last week" button showed all-time KPI cards)
        start = today - timedelta(days=today.weekday() + 7)
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    elif period == "last_7_days":
        return (today - timedelta(days=7)).isoformat(), today.isoformat()
    elif period == "last_30_days":
        return (today - timedelta(days=30)).isoformat(), today.isoformat()
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
    return cached(f"dash:kpis:{period}:{date_from}:{date_to}:{scope}", 300,
                  lambda: _build_dashboard_kpis(period, db, _agent_ids, date_from, date_to))


# Genuine client deposit only — exclude internal MT balance adjustments (method='MT5' or an internal
# label) so the KPI cards / tab counts match the Deposits list + Finance (same rule everywhere).
_DEP = (r"t.tx_type='deposit' AND t.amount < 1000000 AND COALESCE(t.method,'') <> 'MT5' "
        r"AND COALESCE(t.method,'') !~* '(deposit\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance"
        r"|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back|credit\s*(in|out)|bonus\s*adjustment)'")
# Real withdrawal only — exclude REJECTED (a rejected withdrawal was reverted/refunded, so it never left).
_WD = "t.tx_type='withdrawal' AND t.amount < 1000000 AND COALESCE(t.status,'') <> 'rejected'"


def _build_dashboard_kpis(period: str, db: Session, _agent_ids, date_from: str = "", date_to: str = ""):
    p_from, p_to = get_period_dates(period)
    # explicit window (from the Transactions date pickers) overrides the period preset
    if date_from: p_from = date_from
    if date_to:   p_to   = date_to
    # index-friendly date boundaries (compare the RAW indexed column to boundary strings;
    # never wrap the column in ::date — that defeats the tx_date/created_at indexes).
    # TIMEZONE (Jul 2026): plain FACE-VALUE calendar-day bounds (crm_tz day_lo/day_hi);
    # only "today" itself comes from Iraq's clock (today_local) — the box runs UTC and
    # date.today() flipped the day 3h late. End-day INCLUSIVE is preserved via `< day_hi`.
    from crm_tz import day_lo, day_hi, today_local
    _today   = today_local()
    p_to_next = day_hi(p_to)
    d3        = day_lo(date.fromisoformat(p_to) - timedelta(days=3))              # last-3-days lower bound
    d14       = day_lo(_today - timedelta(days=14))
    today_s   = day_lo(_today)
    tom_s     = day_hi(_today)
    yr_start  = day_lo(f"{_today.year}-01-01")
    yr_next   = day_lo(f"{_today.year + 1}-01-01")
    p_from    = day_lo(p_from)

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
    # Active traders = accounts that actually TRADED in the period (deals, buy/sell) —
    # the old number was distinct DEPOSITORS mislabeled as traders.
    if _agent_ids is None:
        if period == "all_time" and not date_from and not date_to:
            # PERF: deals has ~17M rows but only ~16k distinct traders — a recursive
            # "skip scan" over ix_deals_login probes one index entry per login
            # (0.5s) instead of COUNT(DISTINCT) over the whole table (11s).
            active_traders = db.execute(text("""
                WITH RECURSIVE t AS (
                  (SELECT login FROM deals WHERE action IN (0,1) ORDER BY login LIMIT 1)
                  UNION ALL
                  SELECT (SELECT d.login FROM deals d
                          WHERE d.login > t.login AND d.action IN (0,1)
                          ORDER BY d.login LIMIT 1)
                  FROM t WHERE t.login IS NOT NULL)
                SELECT count(login) FROM t""")).scalar() or 0
        else:
            # short ranges use the partial (deal_date, login) index
            active_traders = db.execute(text("""
                SELECT COUNT(DISTINCT login) FROM deals
                WHERE action IN (0,1) AND deal_date >= :f AND deal_date < :tnext"""), base_p).scalar() or 0
    else:
        active_traders = db.execute(text("""
            SELECT COUNT(DISTINCT d.login) FROM deals d
            JOIN clients c ON c.login = d.login AND c.assigned_agent_id = ANY(:aids)
            WHERE d.action IN (0,1) AND d.deal_date >= :f AND d.deal_date < :tnext"""), base_p).scalar() or 0

    # Pending withdrawals (all time)
    pending_w = db.execute(text(f"""
        SELECT COUNT(*) FROM transactions t {TJOIN}
        WHERE t.tx_type = 'withdrawal' AND t.status IN ('pending','processing') {TX}
    """), base_p).scalar() or 0

    # ACTIVE CLIENTS in period — PEOPLE with ANY activity: deposit / withdrawal / internal
    # transfer / bonus (transactions) OR a trade (deals) inside the period.
    _CJ = "AND c.assigned_agent_id = ANY(:aids)" if _agent_ids is not None else ""
    active_clients_period = db.execute(text(f"""
        SELECT COUNT(*) FROM customers cu
        WHERE cu.kind='client'
          AND cu.customer_no IN (
            SELECT c.customer_no FROM transactions t JOIN clients c ON c.login = t.login {_CJ}
            WHERE c.customer_no IS NOT NULL AND t.tx_date >= :f AND t.tx_date < :tnext
              AND t.tx_type IN ('deposit','withdrawal','internal_transfer','bonus_deposit','bonus_withdrawal')
            UNION
            SELECT c.customer_no FROM deals d JOIN clients c ON c.login = d.login {_CJ}
            WHERE c.customer_no IS NOT NULL AND d.action IN (0,1)
              AND d.deal_date >= :f AND d.deal_date < :tnext)
          AND cu.customer_no NOT IN (SELECT customer_no FROM clients
                                     WHERE COALESCE(user_archived,FALSE) AND customer_no IS NOT NULL)
    """), base_p).scalar() or 0

    # New clients in period — PEOPLE, not accounts: a person counts when their EARLIEST
    # first-deposit across all their accounts falls in the period (an existing depositor
    # funding a second account is NOT a new client).
    # Constrained to the CLIENTS-page universe (kind='client', not team-archived) so clicking
    # the card shows EXACTLY this many people. A first-deposit person TradeSoft still holds as
    # a lead is excluded here (they're on the Leads page until reclassified).
    new_clients = db.execute(text(f"""
        SELECT COUNT(*) FROM customers cu
        WHERE cu.kind='client'
          AND cu.customer_no IN (
            SELECT customer_no FROM clients
            WHERE customer_no IS NOT NULL AND COALESCE(first_deposit_at,'') <> '' {CL}
            GROUP BY customer_no
            HAVING MIN(first_deposit_at) >= :f AND MIN(first_deposit_at) < :tnext)
          AND cu.customer_no NOT IN (SELECT customer_no FROM clients
                                     WHERE COALESCE(user_archived,FALSE) AND customer_no IS NOT NULL)
    """), base_p).scalar() or 0

    # Total active clients (have balance > 0)
    active_clients = db.execute(text(f"""
        SELECT COUNT(DISTINCT login) FROM clients WHERE balance > 0 {CL}
    """), base_p).scalar() or 0

    # Total unique clients
    # Total clients = PERSONS (customer golden records, kind='client') — the same number as
    # the Clients page. The old distinct-phone count over all 179k account rows gave ~63k.
    if _agent_ids is None:
        total_clients = db.execute(text("SELECT COUNT(*) FROM customers WHERE kind='client'")).scalar() or 0
    else:
        total_clients = db.execute(text("""
            SELECT COUNT(*) FROM customers cu WHERE cu.kind='client'
              AND EXISTS (SELECT 1 FROM clients c WHERE c.customer_no = cu.customer_no
                          AND c.assigned_agent_id = ANY(:aids))"""), base_p).scalar() or 0

    # Clients with no deposit in 14+ days — REAL funded accounts only (was: every row with any
    # balance incl. demo/seed/archived, which exceeded the total client count).
    no_dep_14 = db.execute(text(f"""
        SELECT COUNT(*) FROM clients
        WHERE balance > 0 AND balance < 1000000
        AND NOT COALESCE(is_archived, FALSE)
        AND (last_deposit_at IS NULL OR last_deposit_at = '' OR last_deposit_at < :d14)
        AND group_name NOT ILIKE '%retail%' AND COALESCE(group_name,'') NOT ILIKE '%demo%' {CL}
    """), base_p).scalar() or 0

    # New leads this period — from the LEADS table (was: clients.created_at, i.e. import date)
    if _agent_ids is None:
        new_leads = db.execute(text("""
            SELECT COUNT(*) FROM leads WHERE created_at >= CAST(:f AS timestamptz)
              AND created_at < CAST(:tnext AS timestamptz)"""), base_p).scalar() or 0
    else:
        new_leads = db.execute(text("""
            SELECT COUNT(*) FROM leads WHERE created_at >= CAST(:f AS timestamptz)
              AND created_at < CAST(:tnext AS timestamptz)
              AND assigned_agent_id = ANY(:aids)"""), base_p).scalar() or 0

    # IB commission in period (not an agent-level KPI -> only for full-access roles)
    if _agent_ids is None:
        ib_comm = db.execute(text("""
            SELECT COALESCE(SUM(commission_usd), 0) FROM ib_commissions
            WHERE trade_date IS NOT NULL AND trade_date >= :f AND trade_date < :tnext
        """), {"f": p_from, "t": p_to, "tnext": p_to_next}).scalar() or 0
    else:
        ib_comm = 0

    # Total balance — REAL client money only: funded accounts (a deposit/withdrawal exists),
    # sane value (<$1M), not demo/retail, not archived. The raw SUM over every row counted the
    # TradeSoft demo/seed balances (100k/300k/50M seeds) and showed ~$34 BILLION.
    total_balance = db.execute(text(f"""
        SELECT COALESCE(SUM(c.balance), 0) FROM clients c
        JOIN client_tx_agg a ON a.login = c.login AND (a.dep_sum > 0 OR a.wd_sum > 0)
        WHERE c.balance > 0 AND c.balance < 1000000
        AND NOT COALESCE(c.is_archived, FALSE)
        AND c.group_name NOT ILIKE '%retail%' AND COALESCE(c.group_name,'') NOT ILIKE '%demo%' {CL}
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
        "active_clients_period": active_clients_period,
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
    """Datetime bounds (start, end) for trend/leaderboard/funnel queries.
    Face-value digits (see crm_tz) — only 'today' comes from Iraq's clock, because the
    box runs UTC and plain datetime.now() would flip the day 3h late."""
    now = datetime.now() + timedelta(hours=3)             # Iraq wall clock (box runs UTC)
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
                     AND NULLIF(c.first_deposit_at,'')::timestamp < :end
                     THEN COALESCE(c.customer_no, CAST(c.login AS TEXT)) END) AS new_clients
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
    from crm_tz import today_local
    today = today_local()
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
        from crm_tz import day_lo, day_hi
        p = dict(extra, f=day_lo(f), t=t.isoformat(), tnext=day_hi(t))
        dep = db.execute(text(f"""SELECT COALESCE(SUM(t.amount),0) FROM transactions t {TJOIN}
            WHERE t.tx_type='deposit' AND t.tx_date>=:f AND t.tx_date<:tnext {TX}"""), p).scalar() or 0
        wth = db.execute(text(f"""SELECT COALESCE(SUM(t.amount),0) FROM transactions t {TJOIN}
            WHERE t.tx_type='withdrawal' AND t.tx_date>=:f AND t.tx_date<:tnext {TX}"""), p).scalar() or 0
        # new clients = PEOPLE whose earliest first-deposit falls in the window
        nc = db.execute(text(f"""SELECT COUNT(*) FROM (
              SELECT COALESCE(customer_no, CAST(login AS TEXT)) AS person FROM clients
              WHERE first_deposit_at IS NOT NULL AND first_deposit_at!='' {CL}
              GROUP BY COALESCE(customer_no, CAST(login AS TEXT))
              HAVING MIN(first_deposit_at)>=:f AND MIN(first_deposit_at)<:tnext) x"""), p).scalar() or 0
        at = db.execute(text(f"""SELECT COUNT(DISTINCT d.login) FROM deals d
            {'JOIN clients c ON c.login=d.login AND c.assigned_agent_id = ANY(:aids)' if TX else ''}
            WHERE d.action IN (0,1) AND d.deal_date>=:f AND d.deal_date<:tnext"""), p).scalar() or 0
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


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE DASHBOARD — role-aware front page (auto-refreshes ~20s).  READ-ONLY.
# ═══════════════════════════════════════════════════════════════════════════════
# Every section is independently guarded: a missing table/column returns an EMPTY
# section instead of 500-ing the page. Each except MUST db.rollback() — a failed
# query poisons the SQLAlchemy session for the rest of the request.

# call_actions is ~99.9% 'agent_change' rows (it is an assignment AUDIT log, not a call
# log). These action values are not calls; everything else in there is. The real call
# evidence is dialer_call_logs + call_qa (the PBX/Whisper QA feed) — see _live_won_lost.
_NOT_A_CALL = ("agent_change", "transfer_in", "deposit_rejected")

# last-9-digits phone match — the same convention auto_match.py uses to bridge
# leads<->clients, needed because call_qa keys calls by DIALED NUMBER, not login.
_P9 = r"right(regexp_replace(COALESCE({col},''), '\D', '', 'g'), 9)"

# Periods this endpoint will serve. MEASURED on the live DB: the sales_commission engine costs
# ~2.5s over a day/month, 6.4s over this_year and **79s over all_time** (it re-attributes every
# client+lead, then sums the whole markup rollup). A 20s-refreshing front page must never pay
# that, so the wide windows are not offered here — the Sales Agents page owns year/all-time
# reporting. This is also a GUARD: get_period_dates() falls through to all_time for ANY
# unrecognised string, so without this allowlist a typo'd ?period= would pin a worker for 79s.
_LIVE_PERIODS = ("today", "yesterday", "this_week", "last_week", "last_7_days", "last_30_days",
                 "this_month", "last_month", "this_year", "last_year")


def _live_role(db, user, agent_ids):
    """Map the caller onto the three live-dashboard personas: leads / retention / admin.

    DATA-DRIVEN (desk rule Jul 16 2026): users.team_type is unreliable/mis-tagged, so the
    desk is decided by the agent's OWN BOOK — whoever has more LEADS than clients works the
    "leads" desk; whoever has more CLIENTS than leads is "retention". (e.g. Wael: 5,393 leads
    vs 7 clients -> leads; Aileen: 1 lead vs 3,444 clients -> retention.)
    agent_ids is None => rbac granted full visibility (admin/director + all-access ops roles).
    """
    if agent_ids is None:
        return "admin"
    role = getattr(user, "role", None)
    role = (role.value if hasattr(role, "value") else role) or ""
    if role.lower() in ("super_admin", "admin", "director"):
        return "admin"
    try:
        n_leads = db.execute(text(
            "SELECT COUNT(*) FROM leads l WHERE l.assigned_agent_id = ANY(:a) "
            "AND NOT COALESCE(l.is_archived, FALSE)"), {"a": agent_ids}).scalar() or 0
        n_clients = db.execute(text(
            "SELECT COUNT(DISTINCT COALESCE(c.customer_no, CAST(c.login AS TEXT))) "
            "FROM clients c WHERE c.assigned_agent_id = ANY(:a)"), {"a": agent_ids}).scalar() or 0
    except Exception:
        db.rollback()
        return "retention"
    return "leads" if int(n_leads) > int(n_clients) else "retention"


def _live_commission(db, role, uid, p_from, p_to_next):
    """(commission, nda_ftd, unit_usd) straight from the EXISTING engine — sales_commission.py.
    Never reimplement the commission math here. The unit rate is the same crm_settings key the
    Sales Agents page uses, so the two pages agree.

    The setting is read with a plain SELECT rather than crm_settings.get_float(): that helper
    falls back to ensure() — CREATE TABLE + INSERT + commit — if the table is missing, and this
    endpoint is strictly READ-ONLY. Same key, same 10.0 default, no write path.
    """
    import sales_commission as SC
    try:
        unit = float(db.execute(text("SELECT val FROM crm_settings WHERE key = 'sales_unit_usd'")
                                ).scalar())
    except Exception:
        db.rollback()
        unit = 10.0
    try:
        res = SC.compute(db, p_from, p_to_next, unit, only_aid=(None if role == "admin" else uid))
    except Exception:
        db.rollback()
        return 0.0, 0, unit
    if role == "admin":                       # unscoped => the whole desk's earnings
        return (round(sum(float(v.get("commission") or 0) for v in res.values()), 2),
                int(sum(int(v.get("nda_ftd") or 0) for v in res.values())), unit)
    cc = res.get(uid) or {}
    # SALES are paid the per-NDA unit bonus ('commission' = unit_bonus + any gated markup);
    # RETENTION are paid the markup commission (D2-gated inside the engine).
    val = cc.get("markup_comm") if role == "retention" else cc.get("commission")
    return round(float(val or 0), 2), int(cc.get("nda_ftd") or 0), unit


def _live_markup_rows(db, agent_ids, d_from, d_next):
    """RETENTION/ADMIN: the latest closed trades that generated markup on this user's book.

    PERF: deals is ~16.8M rows. This is bounded by BOTH the period (deal_date range, served by
    the partial index ix_deals_trades_date_login on (deal_date, login) WHERE action IN (0,1))
    and the agent scope, then LIMIT 25 — ~0.15s measured. markup_profit/volume are stored in
    the /10000 scale (same as markup_agg.py's rollup). CREDIT_EXCLUDE keeps the basis identical
    to sales_commission.py's markup_nc (ib_trades.reason='credit' deals don't pay commission).
    """
    af, ap = _agent_filter(agent_ids, "c.assigned_agent_id")
    try:
        rows = db.execute(text(f"""
            SELECT to_timestamp(d.deal_time)              AS ts,
                   c.name                                 AS client,
                   d.login                                AS login,
                   d.symbol                               AS symbol,
                   COALESCE(d.volume,0)/10000.0           AS lots,
                   COALESCE(d.markup_profit,0)/10000.0    AS markup,
                   COALESCE(u.commission_pct,10)          AS pct,
                   d.deal_id                              AS deal_id
            FROM deals d
            JOIN clients c ON c.login = d.login
            LEFT JOIN users u ON u.id = c.assigned_agent_id
            WHERE d.action IN (0,1)
              AND d.deal_date >= :df AND d.deal_date < :dnext
              AND COALESCE(d.markup_profit,0) > 0
              AND NOT EXISTS (SELECT 1 FROM ib_trades cr
                              WHERE cr.deal_id = d.deal_id AND cr.reason = 'credit')
              {af}
            ORDER BY d.deal_time DESC
            LIMIT 25
        """), dict(ap, df=d_from, dnext=d_next)).fetchall()
    except Exception:
        db.rollback()
        return []
    # per-trade paid-to-IB. Trades already in ib_trades (rebuilt ~every 30min) use its
    # eligibility-adjusted commission; trades too NEW for the last rebuild are computed LIVE
    # (lots x commission_rates for the client's IB level+symbol) so a fresh IB-client trade
    # never shows a stale 0. rows are newest-first, so the freshest ones are exactly those the
    # rebuild hasn't reached yet. Non-IB clients stay 0 (nothing to pay). Batched scans (no
    # correlated subqueries: ib_trades has no deal_id index, 25 of them = 25 seq scans of 3M rows).
    in_ibt = {}   # deal_id -> engine eligible commission (present in ib_trades; 0 if not eligible)
    lvl_of = {}   # login   -> IB level (5-10) for clients under an IB
    rate   = {}   # (level, symbol) -> comm_per_lot
    deal_ids = [int(r[7]) for r in rows if r[7] is not None]
    logins   = list({int(r[2]) for r in rows if r[2] is not None})
    if deal_ids:
        try:
            for dr in db.execute(text(
                "SELECT deal_id, COALESCE(SUM(commission) FILTER (WHERE eligible),0) FROM ib_trades "
                "WHERE deal_id = ANY(:ids) GROUP BY deal_id"), {"ids": deal_ids}).fetchall():
                in_ibt[int(dr[0])] = float(dr[1] or 0)
        except Exception:
            db.rollback()
    if logins:
        try:
            for lr in db.execute(text(
                "SELECT c.login, ib.ib_level FROM clients c JOIN ibs ib "
                "ON ib.agent_id = c.agent AND ib.ib_level BETWEEN 5 AND 10 "
                "WHERE c.login = ANY(:lg)"), {"lg": logins}).fetchall():
                lvl_of[int(lr[0])] = int(lr[1])
            if lvl_of:
                for rr in db.execute(text(
                        "SELECT ib_level, symbol, comm_per_lot FROM commission_rates")).fetchall():
                    rate[(int(rr[0]), rr[1])] = float(rr[2] or 0)
        except Exception:
            db.rollback()
    out = []
    for r in rows:
        markup = float(r[5] or 0)
        pct = float(r[6] or 10)
        did = int(r[7]) if r[7] is not None else -1
        if did in in_ibt:
            paid_ib = in_ibt[did]                                   # engine value (eligibility-adjusted)
        else:                                                       # too fresh -> live rate estimate
            _lvl = lvl_of.get(int(r[2]) if r[2] is not None else -1)
            paid_ib = float(r[4] or 0) * rate.get((_lvl, r[3]), 0.0) if _lvl else 0.0
        out.append({
            "time": r[0].isoformat() if r[0] else None,
            "client": r[1] or "", "login": int(r[2] or 0), "symbol": r[3] or "",
            "lots": round(float(r[4] or 0), 2), "markup": round(markup, 2),
            "commission": round(markup * pct / 100.0, 2),   # gross agent share (back-compat)
            "paid_to_ib": round(paid_ib, 2),
            "net": round(max(0.0, markup - paid_ib) * pct / 100.0, 2),
        })
    return out


def _call_evidence_sql(agent_ids):
    """(union-of-call-sources SQL, extra params) — every row is one call to FTD row `f`,
    already restricted to calls that happened BEFORE that client's first deposit.

    CALL EVIDENCE — all three real sources are unioned (verified against the live DB):
      • call_qa         — the PBX/Whisper QA feed, the only source of real call volume (2.6k).
                          client_login is resolved on just ~663/2619 rows, so the rest are
                          matched on the DIALED NUMBER via last-9 phone digits (the same
                          convention auto_match.py uses to bridge leads<->clients).
      • dialer_call_logs— the power-dialer outcomes (764), keyed by login.
      • call_actions    — keyed by login, but ~99.9% of it is 'agent_change' assignment-audit
                          rows; _NOT_A_CALL filters those out so an agent REASSIGNMENT can
                          never be mistaken for a call and fake a "won".
    When scoped to an agent, only THAT agent's calls count (call_qa links via users.extension).
    """
    if agent_ids is None:
        ca_f = dl_f = qa_f = ""
        p = {}
    else:
        ca_f = " AND ca.agent_id = ANY(:call_aids) "
        dl_f = " AND dl.agent_id = ANY(:call_aids) "
        qa_f = (" AND q.agent_ext IN (SELECT extension FROM users "
                "WHERE id = ANY(:call_aids) AND COALESCE(extension,'') <> '') ")
        p = {"call_aids": agent_ids}
    sql = f"""
        SELECT ca.created_at AT TIME ZONE 'UTC' AS ts
          FROM call_actions ca
         WHERE ca.login = f.login
           AND COALESCE(ca.action,'') <> ALL(:notcall)
           AND ca.created_at AT TIME ZONE 'UTC' < f.fda::timestamp {ca_f}
        UNION ALL
        SELECT dl.called_at
          FROM dialer_call_logs dl
         WHERE dl.login = f.login AND dl.called_at < f.fda::timestamp {dl_f}
        UNION ALL
        SELECT q.call_time AT TIME ZONE 'UTC'
          FROM call_qa q
         WHERE (q.client_login = f.login
                OR (length(f.p9) = 9 AND {_P9.format(col='q.customer_number')} = f.p9))
           AND q.call_time AT TIME ZONE 'UTC' < f.fda::timestamp {qa_f}
    """
    return sql, p


def _live_won_lost(db, agent_ids, f_lo, f_hi, unit, limit=25):
    """SALES/ADMIN: clients whose FIRST DEPOSIT landed in the period, split won/lost.
      won  = a call to that customer exists BEFORE clients.first_deposit_at  -> bonus = unit
      lost = the first deposit happened with NO call before it               -> bonus = 0
    Returns (rows[<=limit], won_total, lost_total).

    TWO queries on purpose: the KPI counts must cover EVERY FTD in the period (a capped list
    would make kpis.won/lost describe only the newest 25), while the returned list stays capped
    at `limit`. The count uses EXISTS (short-circuits per row); only the 25 listed rows pay for
    max() to report the actual call time. Both are bounded by period+agent, and _LIVE_PERIODS
    keeps the FTD universe to ~1 month (<=~500 rows) — measured 0.13s (today) / 0.9s (30d).
    """
    af, ap = _agent_filter(agent_ids, "c.assigned_agent_id")
    ev, sp = _call_evidence_sql(agent_ids)
    base = {**ap, **sp, "flo": f_lo, "fhi": f_hi, "notcall": list(_NOT_A_CALL)}
    ftd_cte = f"""
        WITH ftd AS (
            SELECT c.login, c.name, NULLIF(c.first_deposit_at,'') AS fda,
                   {_P9.format(col='c.phone')} AS p9
            FROM clients c
            WHERE c.first_deposit_at >= :flo AND c.first_deposit_at < :fhi
              AND COALESCE(c.first_deposit_at,'') <> ''
              {af}
    """
    # ── KPI counts over the WHOLE period ──
    won_n = lost_n = 0
    try:
        r = db.execute(text(f"""
            {ftd_cte} )
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE EXISTS ({ev})) AS won
            FROM ftd f
        """), base).fetchone()
        won_n, lost_n = int(r[1] or 0), int((r[0] or 0) - (r[1] or 0))
    except Exception:
        db.rollback()
    # ── the capped list (newest FTDs first), with the real call time ──
    try:
        rows = db.execute(text(f"""
            {ftd_cte} ORDER BY c.first_deposit_at DESC LIMIT :lim )
            SELECT f.login, f.name, f.fda,
                   (SELECT max(x.ts) FROM ({ev}) x) AS called_at
            FROM ftd f
            ORDER BY f.fda DESC
        """), {**base, "lim": limit}).fetchall()
    except Exception:
        db.rollback()
        return [], won_n, lost_n
    out = []
    for r in rows:
        won = r[3] is not None
        out.append({
            "login": int(r[0] or 0), "name": r[1] or "",
            "first_deposit_at": (r[2] or "").replace(" ", "T") if r[2] else None,
            "called_at": r[3].isoformat() if r[3] else None,
            "status": "won" if won else "lost",
            "bonus": round(float(unit), 2) if won else 0.0,
        })
    return out, won_n, lost_n


def _live_recent_leads(db, agent_ids, limit=10):
    """SALES/ADMIN: the last N registered leads (ix_leads_created_at) + how stale each is."""
    af, ap = _agent_filter(agent_ids, "l.assigned_agent_id")
    try:
        rows = db.execute(text(f"""
            SELECT l.id, l.full_name, l.source, l.campaign_name, l.country, l.created_at,
                   GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - l.created_at))/60)) AS age_min
            FROM leads l
            WHERE l.created_at IS NOT NULL {af}
            ORDER BY l.created_at DESC
            LIMIT :lim
        """), dict(ap, lim=limit)).fetchall()
    except Exception:
        db.rollback()
        return []
    return [{"id": int(r[0]), "name": r[1] or "", "source": r[2] or "",
             "campaign": r[3] or "", "country": r[4] or "",
             "created_at": r[5].isoformat() if r[5] else None,
             "age_minutes": int(r[6] or 0)} for r in rows]


def _live_kyc(db, agent_ids, limit=10):
    """Leads/clients awaiting or holding KYC approval — pending first, then newest.
    Both tables carry kyc_status, so both are unioned (clients hold ~20k pending, leads ~13)."""
    caf, cap = _agent_filter(agent_ids, "c.assigned_agent_id")
    laf, lap = _agent_filter(agent_ids, "l.assigned_agent_id")
    try:
        rows = db.execute(text(f"""
            WITH k AS (
                SELECT c.id, c.name AS nm, c.kyc_status AS st,
                       COALESCE(c.kyc_ocr_at, c.updated_at) AS sub
                FROM clients c
                WHERE COALESCE(c.kyc_status,'') <> '' AND c.kyc_status <> 'exists' {caf}
                UNION ALL
                SELECT l.id, l.full_name, l.kyc_status,
                       COALESCE(l.kyc_ocr_at, l.updated_at)
                FROM leads l
                WHERE COALESCE(l.kyc_status,'') <> '' AND l.kyc_status <> 'exists' {laf}
            )
            SELECT id, nm, st, sub FROM k
            WHERE st IN ('pending','pending_review','pending_admin_review','docs_needed','verified')
            ORDER BY (st = 'verified'), sub DESC NULLS LAST
            LIMIT :lim
        """), {**cap, **lap, "lim": limit}).fetchall()
    except Exception:
        db.rollback()
        return []
    return [{"id": int(r[0]), "name": r[1] or "", "kyc_status": r[2] or "",
             "submitted_at": r[3].isoformat() if r[3] else None} for r in rows]


def _live_counts(db, agent_ids, pf, dn):
    """Book size, matching the Clients / Leads pages exactly (admin: all, else this user's book):
      clients = PERSONS (customers golden records, kind='client') — NOT the ~179k raw account rows.
      leads   = ACTIVE leads (non-archived, like the Leads page default).
      nda     = is_nda FTDs whose FIRST DEPOSIT falls in [pf, dn) — the desk's "new depositors".
    All three scoped to the caller's assigned agents via clients/leads.assigned_agent_id.
    first_deposit_at is 'YYYY-MM-DD HH:MM:SS' text, so bare 'YYYY-MM-DD' bounds compare lexically."""
    caf, cap = _agent_filter(agent_ids, "c.assigned_agent_id")
    laf, lap = _agent_filter(agent_ids, "l.assigned_agent_id")
    # clients = persons
    try:
        if agent_ids is None:
            n_cl = db.execute(text("SELECT COUNT(*) FROM customers WHERE kind='client'")).scalar() or 0
        else:
            n_cl = db.execute(text("""
                SELECT COUNT(*) FROM customers cu WHERE cu.kind='client'
                  AND EXISTS (SELECT 1 FROM clients c WHERE c.customer_no = cu.customer_no
                              AND c.assigned_agent_id = ANY(:agent_ids))"""), cap).scalar() or 0
    except Exception:
        db.rollback(); n_cl = 0
    # leads = active book
    try:
        n_ld = db.execute(text(f"""
            SELECT COUNT(*) FROM leads l
            WHERE NOT COALESCE(l.is_archived, FALSE) {laf}"""), lap).scalar() or 0
    except Exception:
        db.rollback(); n_ld = 0
    # nda = new depositors this period
    try:
        p = dict(cap); p.update({"pf": pf, "dn": dn})
        n_nda = db.execute(text(f"""
            SELECT COUNT(*) FROM clients c
            WHERE c.is_nda = TRUE
              AND c.first_deposit_at >= :pf AND c.first_deposit_at < :dn {caf}"""), p).scalar() or 0
    except Exception:
        db.rollback(); n_nda = 0
    return int(n_cl), int(n_ld), int(n_nda)


def _live_flows(db, agent_ids, f, tnext):
    """Deposits / withdrawals / net for the period (the dashboard bars). Same _DEP/_WD predicates
    the /kpis endpoint uses so the numbers agree; scoped to the caller's book."""
    if agent_ids is None:
        tj, tx, p = "", "", {"f": f, "tnext": tnext}
    else:
        tj = "JOIN clients c ON c.login = t.login"
        tx = " AND c.assigned_agent_id = ANY(:aids) "
        p = {"f": f, "tnext": tnext, "aids": agent_ids}
    try:
        row = db.execute(text(f"""
            SELECT COALESCE(SUM(t.amount) FILTER (WHERE {_DEP}),0),
                   COALESCE(SUM(t.amount) FILTER (WHERE {_WD}),0)
            FROM transactions t {tj}
            WHERE t.tx_date >= :f AND t.tx_date < :tnext {tx}"""), p).fetchone()
        dep, wd = float(row[0] or 0), float(row[1] or 0)
    except Exception:
        db.rollback(); dep, wd = 0.0, 0.0
    return {"deposits": round(dep, 2), "withdrawals": round(wd, 2), "net": round(dep - wd, 2)}


def _live_markup_totals(db, agent_ids, d_from, d_next, pf, dn):
    """RETENTION/ADMIN period money: total markup on the book, total paid to IBs, and the net
    (markup − paid-to-IB). Two bounded scalar scans (period + scope), cached by the caller."""
    af, ap = _agent_filter(agent_ids, "c.assigned_agent_id")
    markup = paid = 0.0
    try:
        # CREDIT_EXCLUDE: credit-funded trades don't pay markup commission (same rule as
        # sales_commission.py / the IB page), so exclude them from the net-markup basis.
        markup = float(db.execute(text(f"""
            SELECT COALESCE(SUM(d.markup_profit),0)/10000.0
            FROM deals d JOIN clients c ON c.login = d.login
            WHERE d.action IN (0,1) AND d.deal_date >= :df AND d.deal_date < :dn
              AND COALESCE(d.markup_profit,0) > 0
              AND NOT EXISTS (SELECT 1 FROM ib_trades cr WHERE cr.deal_id = d.deal_id AND cr.reason = 'credit')
              {af}"""), dict(ap, df=d_from, dn=d_next)).scalar() or 0)
    except Exception:
        db.rollback()
    try:
        # AUTHORITATIVE IB commission for the period. GOTCHA (fixed Jul 2026): summing
        # ib_trades.commission UNDERCOUNTS the recent excel era — the per-deal excel overlay
        # (excel_trade_commission, keyed by deal_id) could NOT be fed the Jul-2026 Plugit rebates
        # (their TicketID != our deal_id), so those excel-era trades sit at $0 in ib_trades. The
        # complete source is the daily aggregate `excel_commission_daily` (extended to EXCEL_CUTOFF)
        # + the live ib_trades engine AFTER the cutoff — the SAME split get_ib/p_commission uses.
        # excel_commission_daily is per-IB (ext_ib_id), not per-sales-agent, so use it only at ADMIN
        # scope (no agent filter); a scoped team view keeps the per-trade sum (best available).
        EXCEL_CUTOFF = "2026-07-17"   # keep in sync with ib_trades.EXCEL_CUTOFF
        if not af:   # ADMIN / unscoped → daily-excel (<=cutoff) + live ib_trades (>cutoff)
            excd = float(db.execute(text("""
                SELECT COALESCE(SUM(commission),0) FROM excel_commission_daily
                WHERE day >= CAST(:pf AS date) AND day < LEAST(CAST(:dn AS date), CAST(:cut AS date) + 1)"""),
                {"pf": pf[:10], "dn": dn[:10], "cut": EXCEL_CUTOFF}).scalar() or 0)
            livec = float(db.execute(text("""
                SELECT COALESCE(SUM(commission),0) FROM ib_trades
                WHERE eligible AND close_time > CAST(:cut AS date) + 1
                  AND close_time >= CAST(:pf AS date) AND close_time < CAST(:dn AS date)"""),
                {"pf": pf[:10], "dn": dn[:10], "cut": EXCEL_CUTOFF}).scalar() or 0)
            paid = excd + livec
        else:
            paid = float(db.execute(text(f"""
                SELECT COALESCE(SUM(t.commission),0)
                FROM ib_trades t JOIN clients c ON c.login = t.login
                WHERE t.eligible
                  AND t.close_time >= CAST(:pf AS date) AND t.close_time < CAST(:dn AS date) {af}"""),
                dict(ap, pf=pf[:10], dn=dn[:10])).scalar() or 0)
    except Exception:
        db.rollback()
    return {"markup": round(markup, 2), "paid_to_ib": round(paid, 2), "net": round(markup - paid, 2)}


def _live_funnel(db, agent_ids, pf, dn, f_lo, f_hi):
    """RETENTION: leads received + converted in the period, and calls made in the period —
    all scoped to the caller's agents (admin: everyone)."""
    laf, lap = _agent_filter(agent_ids, "l.assigned_agent_id")
    out = {"converted": 0, "calls": 0, "leads_received": 0}
    try:
        # CONVERTED = the lead actually became/matched a client (matched_login), the real signal —
        # leads.status='converted' is barely used (~14 rows total), so it under-reported to ~0.
        r = db.execute(text(f"""
            SELECT COUNT(*) FILTER (WHERE l.created_at >= CAST(:pf AS timestamptz) AND l.created_at < CAST(:dn AS timestamptz)),
                   COUNT(*) FILTER (WHERE l.matched_login IS NOT NULL)
            FROM leads l WHERE NOT COALESCE(l.is_archived,FALSE) {laf}"""),
            dict(lap, pf=pf, dn=dn)).fetchone()
        out["leads_received"] = int(r[0] or 0); out["converted"] = int(r[1] or 0)
    except Exception:
        db.rollback()
    try:
        if agent_ids is None:
            dlf = qaf = ""; cp = {}
        else:
            dlf = " AND dl.agent_id = ANY(:aids) "
            qaf = " AND q.agent_ext IN (SELECT extension FROM users WHERE id = ANY(:aids) AND COALESCE(extension,'') <> '') "
            cp = {"aids": agent_ids}
        out["calls"] = int(db.execute(text(f"""
            SELECT (SELECT COUNT(*) FROM dialer_call_logs dl WHERE dl.called_at >= :flo AND dl.called_at < :fhi {dlf})
                 + (SELECT COUNT(*) FROM call_qa q WHERE q.call_time >= :flo AND q.call_time < :fhi {qaf})"""),
            dict(cp, flo=f_lo, fhi=f_hi)).scalar() or 0)
    except Exception:
        db.rollback()
    return out


def _live_to_call(db, agent_ids, limit=15):
    """RETENTION action list: this agent's funded clients who most need a call — funded-but-not-
    trading (D1 activation) first, then by call_score, then by balance. Returns a `reason` tag so
    the desk knows why. Scoped to the caller's book (admin: everyone)."""
    af, ap = _agent_filter(agent_ids, "c.assigned_agent_id")
    from crm_tz import today_local
    d14 = (today_local() - timedelta(days=14)).isoformat()
    try:
        rows = db.execute(text(f"""
            SELECT c.login, COALESCE(NULLIF(c.name,''), c.full_name_en, '—') AS name,
                   COALESCE(c.balance,0), COALESCE(c.total_deposits,0),
                   COALESCE(c.call_score,0), COALESCE(c.total_trades,0),
                   c.first_deposit_at, c.last_trade_at
            FROM clients c
            WHERE COALESCE(c.balance,0) > 0 AND NOT COALESCE(c.is_archived,FALSE)
              AND COALESCE(c.group_name,'') NOT ILIKE '%demo%' {af}
            ORDER BY
              (CASE WHEN COALESCE(c.total_trades,0)=0 AND c.first_deposit_at IS NOT NULL THEN 0 ELSE 1 END),
              c.call_score DESC NULLS LAST,
              c.balance DESC
            LIMIT :lim"""), dict(ap, lim=limit)).fetchall()
    except Exception:
        db.rollback()
        return []
    out = []
    for r in rows:
        trades = int(r[5] or 0)
        last_trade = str(r[7]) if r[7] else ""
        if trades == 0 and r[6]:
            reason = "activate"        # deposited, never traded — D1 push
        elif last_trade and last_trade < d14:
            reason = "re-engage"       # traded before, gone quiet
        else:
            reason = "follow-up"
        out.append({
            "login": int(r[0] or 0), "name": r[1] or "—",
            "balance": round(float(r[2] or 0), 2), "deposits": round(float(r[3] or 0), 2),
            "call_score": int(r[4] or 0), "trades": trades,
            "first_deposit_at": str(r[6]) if r[6] else None,
            "last_trade_at": str(r[7]) if r[7] else None,
            "reason": reason,
        })
    return out


def _live_active_clients(db, agent_ids, f, tnext):
    """ACTIVE = a client who actually DID something in the period: made a deposit / withdrawal /
    internal transfer (transactions) OR traded (deals, buy/sell). NOT balance>0 (counts dormant
    funded accounts) and NOT mt_last_seen (that's the bridge polling every online account, not a
    login — it over-reports to ~73%). CRM login isn't recorded and MT logins aren't reliably
    logged, so those two activities can't be counted yet."""
    af, ap = _agent_filter(agent_ids, "c.assigned_agent_id")
    try:
        return int(db.execute(text(f"""
            SELECT COUNT(DISTINCT login) FROM (
                SELECT t.login FROM transactions t JOIN clients c ON c.login = t.login
                WHERE t.tx_date >= :f AND t.tx_date < :tnext
                  AND t.tx_type IN ('deposit','withdrawal','internal_transfer') {af}
                UNION
                SELECT d.login FROM deals d JOIN clients c ON c.login = d.login
                WHERE d.deal_date >= :f AND d.deal_date < :tnext AND d.action IN (0,1) {af}
            ) x"""), dict(ap, f=f, tnext=tnext)).scalar() or 0)
    except Exception:
        db.rollback(); return 0


def _live_expenses(db, f, tnext):
    """Company costs booked in Finance Management for the period, split into the itemised
    categories (tech / wages / marketing / office) + everything else as 'other'."""
    out = {"tech": 0.0, "wages": 0.0, "marketing": 0.0, "office": 0.0, "other": 0.0, "total": 0.0}
    try:
        rows = db.execute(text("""
            SELECT LOWER(COALESCE(category,'other')), COALESCE(SUM(amount),0)
            FROM finance_expenses
            WHERE COALESCE(status,'') <> 'void'
              AND exp_date >= :f AND exp_date < :tnext
            GROUP BY 1"""), {"f": f[:10], "tnext": tnext[:10]}).fetchall()
    except Exception:
        db.rollback(); return out
    for cat, amt in rows:
        a = float(amt or 0)
        c = (cat or "")
        if "tech" in c:                                bucket = "tech"
        elif "wage" in c or "salar" in c or "payroll" in c: bucket = "wages"
        elif "market" in c or "ad" == c or "ads" in c: bucket = "marketing"
        elif "office" in c or "rent" in c or "insur" in c or "visa" in c or "operat" in c: bucket = "office"
        else:                                          bucket = "other"
        out[bucket] += a
        out["total"] += a
    return {k: round(v, 2) for k, v in out.items()}


def _live_credit_lost(db, f_lo, f_hi):
    """Credit the company loses on negative accounts: the credit taken back when covering a
    negative (neg_cover_log, credit_before − credit_after) in the period, PLUS the deficit on
    accounts still negative and not yet covered (a current snapshot)."""
    covered = uncovered = 0.0
    try:
        covered = float(db.execute(text("""
            SELECT COALESCE(SUM(GREATEST(COALESCE(credit_before,0)-COALESCE(credit_after,0),0)),0)
            FROM neg_cover_log WHERE created_at >= :flo AND created_at < :fhi"""),
            {"flo": f_lo, "fhi": f_hi}).scalar() or 0)
    except Exception:
        db.rollback()
    try:
        uncovered = float(db.execute(text(
            "SELECT COALESCE(SUM(-balance),0) FROM clients WHERE balance < 0")).scalar() or 0)
    except Exception:
        db.rollback()
    return round(covered + uncovered, 2)


def _live_compare(db, agent_ids, p_from, p_to):
    """Admin: this period vs the SAME-LENGTH immediately-prior window — deposits, withdrawals,
    net, new clients (NDA/FTD), IB commission. Cheap sources only (transactions + clients +
    ib_trades), NO deals scan, so it stays fast at any period width. Returns
    {metric: {current, previous, pct}}."""
    from crm_tz import day_lo, day_hi
    cf = date.fromisoformat(p_from); ct = date.fromisoformat(p_to)
    L = (ct - cf).days + 1
    pt = cf - timedelta(days=1); pf = pt - timedelta(days=L - 1)
    scoped = agent_ids is not None
    tj = "JOIN clients c ON c.login = t.login" if scoped else ""
    ibj = "JOIN clients c ON c.login = cr.login" if scoped else ""
    sc = " AND c.assigned_agent_id = ANY(:aids) " if scoped else ""
    base = {"aids": agent_ids} if scoped else {}

    def window(a, b):
        p = dict(base, f=day_lo(a.isoformat()), tnext=day_hi(b.isoformat()),
                 fs=a.isoformat(), fe=(b + timedelta(days=1)).isoformat())
        o = {"deposits": 0.0, "withdrawals": 0.0, "net": 0.0, "new_clients": 0, "ib_commission": 0.0}
        try:
            r = db.execute(text(f"""SELECT COALESCE(SUM(t.amount) FILTER (WHERE {_DEP}),0),
                    COALESCE(SUM(t.amount) FILTER (WHERE {_WD}),0)
                FROM transactions t {tj} WHERE t.tx_date >= :f AND t.tx_date < :tnext {sc}"""), p).fetchone()
            o["deposits"] = round(float(r[0] or 0), 2); o["withdrawals"] = round(float(r[1] or 0), 2)
            o["net"] = round(o["deposits"] - o["withdrawals"], 2)
        except Exception:
            db.rollback()
        try:
            # new clients = distinct PERSONS whose earliest first-deposit lands in the window
            # (deduped by customer_no/login) — the old dashboard's definition; stable (doesn't
            # flap with the is_nda re-tag) and person-deduped, not raw account rows.
            o["new_clients"] = int(db.execute(text(f"""SELECT COUNT(*) FROM (
                  SELECT COALESCE(NULLIF(c.customer_no,''), CAST(c.login AS TEXT)) AS person
                  FROM clients c
                  WHERE c.first_deposit_at IS NOT NULL AND c.first_deposit_at <> '' {sc}
                  GROUP BY 1
                  HAVING MIN(c.first_deposit_at) >= :fs AND MIN(c.first_deposit_at) < :fe) x"""), p).scalar() or 0)
        except Exception:
            db.rollback()
        try:
            o["ib_commission"] = round(float(db.execute(text(f"""SELECT COALESCE(SUM(cr.commission),0)
                FROM ib_trades cr {ibj}
                WHERE cr.eligible AND cr.close_time >= CAST(:fs AS date) AND cr.close_time < CAST(:fe AS date) {sc}"""), p).scalar() or 0), 2)
        except Exception:
            db.rollback()
        return o

    cur, prev = window(cf, ct), window(pf, pt)

    def pct(c, p):
        return round((c - p) / abs(p) * 100, 1) if p else (100.0 if c > 0 else 0.0)
    return {k: {"current": cur[k], "previous": prev[k], "pct": pct(cur[k], prev[k])} for k in cur}


def _build_live(period, db, agent_ids, role, uid):
    p_from, p_to = get_period_dates(period)
    from crm_tz import day_lo, day_hi
    # sales_commission.py and deals.deal_date compare against PLAIN 'YYYY-MM-DD' day text
    # (deals_login_daily.day / clients.first_deposit_at), so the engine gets bare dates —
    # passing a 'D 00:00:00' bound here would lexically EXCLUDE day 'D' from the rollup.
    d_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    f_lo, f_hi = day_lo(p_from), day_hi(p_to)        # first_deposit_at is 'YYYY-MM-DD HH:MM:SS'

    # The engine is the slow part (~2.5s: it rebuilds its attribution CTEs over clients+leads).
    # Cached longer than the payload so a 20s auto-refresh never pays for it.
    comm, _eng_nda, unit = cached(f"dash:live:comm:{period}:{role}:{uid if role != 'admin' else 'all'}",
                                  120, lambda: _live_commission(db, role, uid, p_from, d_next))

    # nda for the KPI is the DIRECT is_nda period count (the number the desk verifies), not the
    # engine's attributed nda_ftd (which only counts NDAs credited to an agent with a holding).
    n_clients, n_leads, nda = _live_counts(db, agent_ids, p_from, d_next)

    flows = _live_flows(db, agent_ids, f_lo, d_next)
    active_clients = _live_active_clients(db, agent_ids, f_lo, d_next)

    # ── per-role assembly ──
    # RETENTION (client-heavy) + ADMIN get the client-trade commission feed & money totals.
    markup_rows = _live_markup_rows(db, agent_ids, p_from, d_next) if role in ("retention", "admin") else []
    money = _live_markup_totals(db, agent_ids, p_from, d_next, f_lo, d_next) if role in ("retention", "admin") else {"markup": 0.0, "paid_to_ib": 0.0, "net": 0.0}
    to_call = _live_to_call(db, agent_ids) if role in ("retention", "admin") else []

    # RETENTION commission = net markup × the configurable retention rate (crm_settings
    # 'retention_markup_pct', default 15). Change the rate there and the dashboard follows.
    if role == "retention":
        try:
            ret_pct = float(db.execute(text("SELECT val FROM crm_settings WHERE key='retention_markup_pct'")).scalar())
        except Exception:
            db.rollback(); ret_pct = 15.0
        comm = round(money["net"] * ret_pct / 100.0, 2)
    else:
        ret_pct = 15.0

    # ADMIN company-profit inputs. BOTH KPIs also net off the commissions the company pays:
    #   sales_comm = total sales+retention commission (the engine's total)  ·  ib_comm = total IB commission.
    # KPI1 "Net-deposit profit" (RISKY — it's client money that can still be withdrawn) = RED.
    # KPI2 "Markup profit"      (SAFE  — genuinely earned spread revenue)               = GREEN.
    if role == "admin":
        expenses = _live_expenses(db, f_lo, d_next)
        credit_lost = _live_credit_lost(db, f_lo, f_hi)
        sales_comm = float(comm or 0)          # total commission paid to sales+retention agents
        ib_comm = float(money["paid_to_ib"] or 0)
        profit = {
            "net_deposit_profit": round(flows["net"] - expenses["total"] - sales_comm - ib_comm, 2),
            "markup_profit": round(money["markup"] - expenses["total"] - credit_lost - sales_comm - ib_comm, 2),
            "expenses": expenses, "credit_lost": credit_lost,
            "sales_commission": round(sales_comm, 2), "ib_commission": round(ib_comm, 2),
        }
    else:
        profit = {}

    # LEADS (lead-heavy) + ADMIN get the lead funnel, won/lost, live leads and KYC.
    funnel = _live_funnel(db, agent_ids, p_from, d_next, f_lo, f_hi) if role in ("leads", "admin") else {"converted": 0, "calls": 0, "leads_received": 0}
    if role in ("leads", "admin"):
        won_lost, won, lost = _live_won_lost(db, agent_ids, f_lo, f_hi, unit)
        recent_leads = _live_recent_leads(db, agent_ids)
        kyc_leads = _live_kyc(db, agent_ids)
    else:
        won_lost, won, lost, recent_leads, kyc_leads = [], 0, 0, [], []

    # admin analytics: sales ranking + deposit/withdrawal trend charts + period-vs-previous compare.
    # #244: TEAM LEADERS also get the ranking — scoped to their own team via agent_ids — so the
    # dashboard shows their members' names + numbers (it used to be admin-only => empty for them).
    # A team lead here = scoped user whose visible agent set contains more than just themselves.
    if role == "admin":
        ranking = _build_leaderboard(period, db, agent_ids).get("leaderboard", [])
        trends = _build_trends(period, db, agent_ids).get("series", [])
        compare = _live_compare(db, agent_ids, p_from, p_to)
    elif agent_ids is not None and len(agent_ids) > 1:
        ranking = _build_leaderboard(period, db, agent_ids).get("leaderboard", [])
        trends, compare = [], {}
    else:
        ranking, trends, compare = [], [], {}

    return {
        "role": role,
        "agent_id": None if role == "admin" else uid,
        "period": {"from": p_from, "to": p_to, "key": period},
        "kpis": {
            "commission": comm,
            "clients": n_clients,
            "active_clients": active_clients,
            "leads": n_leads,
            "nda": nda,
            # NEW clients/leads acquired in the selected period (admin dashboard headline tiles).
            # new_clients reuses the compare's person-deduped first-deposit-in-window count (no extra query).
            "new_clients": compare.get("new_clients", {}).get("current", 0),
            "new_leads": funnel["leads_received"],
            "won": won,
            "lost": lost,
            # retention money KPIs
            "markup": money["markup"],
            "paid_to_ib": money["paid_to_ib"],
            "net": money["net"],
            "retention_pct": ret_pct,
            # retention funnel KPIs
            "converted": funnel["converted"],
            "calls": funnel["calls"],
            "leads_received": funnel["leads_received"],
        },
        "profit": profit,
        "flows": flows,
        "markup_rows": markup_rows,
        "recent_leads": recent_leads,
        "won_lost": won_lost,
        "kyc_leads": kyc_leads,
        "ranking": ranking,
        "trends": trends,
        "compare": compare,
        "to_call": to_call,
    }


@router.get("/live")
def get_live_dashboard(period: str = Query("today"),
                       db: Session = Depends(get_db),
                       current_user: models.User = Depends(get_current_user)):
    """Role-aware live front page. READ-ONLY (SELECTs only).

    sales     -> recent leads + won/lost (unit bonus per NDA first-deposit)
    retention -> the markup their book is generating right now
    admin     -> everything, unscoped
    period: one of _LIVE_PERIODS (default/fallback 'today'); the resolved window is echoed
    back as `period` so the caller can see what it actually got.
    Cached 15s (under the ~20s client refresh) and keyed by role+scope so one user's
    scoped data is never served to another.
    """
    if period not in _LIVE_PERIODS:          # incl. all_time/this_year — see _LIVE_PERIODS
        period = "today"
    agent_ids = _scope_agent_ids(db, current_user)
    role = _live_role(db, current_user, agent_ids)
    # Cached ~10s to match the client's 10s poll (the slow ~2.5s commission engine is separately
    # cached 120s, so a cache-miss here only recomputes the lighter feed/flow/count queries).
    return cached(f"dash:live:{period}:{role}:{_scope_key(agent_ids)}", 10,
                  lambda: _build_live(period, db, agent_ids, role, current_user.id))
