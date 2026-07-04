"""
reports_router.py — Performance / KPI report (ticket #45)

A dedicated company-performance report: KPIs for the SELECTED period AND the
PREVIOUS comparable period, each with {current, previous, pct_change}, plus a
per-payment-method withdrawal breakdown and a deposits-by-type breakdown for
the selected period, and the inputs for a client-side CSV export.

Reuses dashboard_router.get_period_dates for the period bounds. Read-only.
Auth = get_current_user (staff/admin) like the other admin routers.

NOTE on the 'MT5' method: in build_transactions.py method='MT5' is NOT a payment
provider — it marks an internal MT5 balance adjustment / zeroing (see
transactions_router.MT5_ADJUST_METHOD). Those are excluded from the deposit
figures here so the report matches the client Deposits view.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, timedelta

from database import get_db
from auth import get_current_user
import models
from dashboard_router import get_period_dates
from perf_cache import cached

router = APIRouter(prefix="/reports", tags=["Reports"])

# Internal MT5 balance-adjustment marker — NOT a real deposit (see transactions_router).
MT5_ADJUST_METHOD = "MT5"

VALID_PERIODS = (
    "today", "this_week", "this_month", "last_month",
    "this_year", "last_year", "all_time",
)


def _previous_period_dates(period: str, p_from: str, p_to: str):
    """Bounds of the PREVIOUS comparable period for a given selected period.

    - today      -> yesterday
    - this_week  -> last week (full Mon..Sun before this week's start)
    - this_month -> last month
    - last_month -> the month before last
    - this_year  -> same span last year (Jan 1 .. same MM-DD a year ago)
    - last_year  -> the year before
    - all_time   -> no previous (returns None, None)
    """
    today = date.today()
    if period == "today":
        y = today - timedelta(days=1)
        return y.isoformat(), y.isoformat()
    if period == "this_week":
        start = today - timedelta(days=today.weekday())   # this Monday
        pe = start - timedelta(days=1)                     # last Sunday
        ps = pe - timedelta(days=6)                        # last Monday
        return ps.isoformat(), pe.isoformat()
    if period == "this_month":
        return get_period_dates("last_month")
    if period == "last_month":
        first_this = today.replace(day=1)
        end_last = first_this - timedelta(days=1)
        start_last = end_last.replace(day=1)
        prev_end = start_last - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return prev_start.isoformat(), prev_end.isoformat()
    if period == "this_year":
        py = today.year - 1
        # same span last year: Jan 1 .. the same month/day a year ago
        try:
            same_day = today.replace(year=py)
        except ValueError:  # Feb 29
            same_day = today.replace(year=py, day=28)
        return f"{py}-01-01", same_day.isoformat()
    if period == "last_year":
        py = today.year - 2
        return f"{py}-01-01", f"{py}-12-31"
    return None, None  # all_time -> no comparison


def _pct_change(cur: float, prev):
    if prev is None:
        return None
    if prev:
        return round((cur - prev) / abs(prev) * 100, 1)
    return 100.0 if cur > 0 else 0.0


def _compute_kpis(db: Session, p_from: str, p_to: str):
    """All numeric KPIs for one [p_from, p_to] window. Read-only."""
    from datetime import date as _date, timedelta as _td
    # exclusive upper bound (day after p_to) for the fast deal_date string-range markup query
    try:
        t_next = (_date.fromisoformat(p_to) + _td(days=1)).isoformat()
    except Exception:
        t_next = p_to + "~"
    p = {"f": p_from, "t": p_to, "t_next": t_next, "mt5": MT5_ADJUST_METHOD}

    # Deposits (exclude internal MT5 adjustments — not real deposits).
    # tx_date is VARCHAR 'YYYY-MM-DD HH:MM:SS'; compare the raw column to ISO 'YYYY-MM-DD'
    # bounds so the ix_transactions_tx_date index is used (a ::date cast forced a full
    # 2M-row scan). End bound is EXCLUSIVE next-day (:t_next) = the old inclusive `<= :t`.
    dep = db.execute(text("""
        SELECT COALESCE(SUM(amount),0), COUNT(*)
        FROM transactions
        WHERE tx_type='deposit' AND method <> :mt5
          AND tx_date >= :f AND tx_date < :t_next
    """), p).fetchone()

    # Withdrawals
    wth = db.execute(text("""
        SELECT COALESCE(SUM(amount),0), COUNT(*)
        FROM transactions
        WHERE tx_type='withdrawal'
          AND tx_date >= :f AND tx_date < :t_next
    """), p).fetchone()

    deposits = float(dep[0] or 0)
    withdrawals = float(wth[0] or 0)

    # New clients (first_deposit_at in period). VARCHAR ISO date → raw string-range compare.
    new_clients = db.execute(text("""
        SELECT COUNT(DISTINCT login) FROM clients
        WHERE first_deposit_at IS NOT NULL AND first_deposit_at != ''
          AND first_deposit_at >= :f AND first_deposit_at < :t_next
    """), p).scalar() or 0

    # Active traders (distinct logins that DEPOSITED in period, real deposits only)
    active_traders = db.execute(text("""
        SELECT COUNT(DISTINCT login) FROM transactions
        WHERE tx_type='deposit' AND method <> :mt5
          AND tx_date >= :f AND tx_date < :t_next
    """), p).scalar() or 0

    # IB commission in period. trade_date is VARCHAR ISO → raw string-range compare (index).
    ib_comm = db.execute(text("""
        SELECT COALESCE(SUM(commission_usd),0) FROM ib_commissions
        WHERE trade_date IS NOT NULL
          AND trade_date >= :f AND trade_date < :t_next
    """), p).scalar() or 0

    # Markup revenue (SUM(deals.markup_profit)/10000) — period-bounded. Uses a STRING range on the
    # ISO 'YYYY-MM-DD' deal_date so the deal_date index is used (a ::date cast here forced a full
    # 4M-row scan = ~26s; this is ~0.05s/day, ~4s/year).
    markup = db.execute(text("""
        SELECT COALESCE(SUM(d.markup_profit),0)/10000.0
        FROM deals d
        WHERE d.action IN (0,1)
          AND d.deal_date >= :f AND d.deal_date < :t_next
    """), p).scalar() or 0

    return {
        "deposits":        deposits,
        "deposit_count":   int(dep[1] or 0),
        "withdrawals":     withdrawals,
        "withdrawal_count": int(wth[1] or 0),
        "net":             round(deposits - withdrawals, 2),
        "new_clients":     int(new_clients),
        "active_traders":  int(active_traders),
        "ib_commission":   float(ib_comm or 0),
        "markup_revenue":  round(float(markup or 0), 2),
    }


@router.get("/kpi")
def reports_kpi(
    period: str = Query("this_month"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if period not in VALID_PERIODS:
        period = "this_month"
    # NOT role-scoped: company-wide performance KPIs, identical for every staff member
    # (current_user is auth-only). Fixed "all" scope; only `period` varies the result.
    return cached(f"reports:kpi:all:{period}", 120,
                  lambda: _build_reports_kpi(db, period))


def _build_reports_kpi(db, period):
    p_from, p_to = get_period_dates(period)
    pp_from, pp_to = _previous_period_dates(period, p_from, p_to)

    cur = _compute_kpis(db, p_from, p_to)
    prev = _compute_kpis(db, pp_from, pp_to) if pp_from else None

    # total clients is a snapshot (not period-bounded) — same definition both sides
    total_clients = db.execute(text("""
        SELECT COUNT(DISTINCT CASE
            WHEN phone IS NOT NULL AND phone != '' AND phone != '0' THEN phone
            ELSE CAST(login AS TEXT) END)
        FROM clients WHERE group_name NOT ILIKE '%retail%'
    """)).scalar() or 0

    # the KPIs surfaced as {current, previous, pct_change}; total_clients has no
    # previous (it's a live snapshot).
    KPI_KEYS = [
        "deposits", "withdrawals", "net", "new_clients",
        "active_traders", "ib_commission", "markup_revenue",
    ]
    kpis = {}
    for k in KPI_KEYS:
        c = cur[k]
        pv = prev[k] if prev else None
        kpis[k] = {"current": c, "previous": pv, "pct_change": _pct_change(c, pv)}
    # counts carried alongside the money figures (for the CSV / labels)
    kpis["deposit_count"] = {
        "current": cur["deposit_count"],
        "previous": prev["deposit_count"] if prev else None,
        "pct_change": _pct_change(cur["deposit_count"], prev["deposit_count"] if prev else None),
    }
    kpis["withdrawal_count"] = {
        "current": cur["withdrawal_count"],
        "previous": prev["withdrawal_count"] if prev else None,
        "pct_change": _pct_change(cur["withdrawal_count"], prev["withdrawal_count"] if prev else None),
    }
    kpis["total_clients"] = {"current": int(total_clients), "previous": None, "pct_change": None}

    # next-day exclusive bound for the index-friendly string-range tx_date filters below
    try:
        t_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    except Exception:
        t_next = p_to + "~"

    # ── Per-method withdrawal breakdown (selected period) ──
    wd_rows = db.execute(text("""
        SELECT COALESCE(NULLIF(method,''),'Other') AS method,
               COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS val
        FROM transactions
        WHERE tx_type='withdrawal'
          AND tx_date >= :f AND tx_date < :t_next
        GROUP BY 1 ORDER BY val DESC
    """), {"f": p_from, "t_next": t_next}).fetchall()
    withdrawals_by_method = [
        {"method": r[0], "count": int(r[1] or 0), "value": round(float(r[2] or 0), 2)}
        for r in wd_rows
    ]

    # ── Deposits-by-type breakdown (selected period; excludes internal MT5 adj.) ──
    dep_rows = db.execute(text("""
        SELECT COALESCE(NULLIF(method,''),'Other') AS method,
               COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS val
        FROM transactions
        WHERE tx_type='deposit' AND method <> :mt5
          AND tx_date >= :f AND tx_date < :t_next
        GROUP BY 1 ORDER BY val DESC
    """), {"f": p_from, "t_next": t_next, "mt5": MT5_ADJUST_METHOD}).fetchall()
    deposits_by_type = [
        {"method": r[0], "count": int(r[1] or 0), "value": round(float(r[2] or 0), 2)}
        for r in dep_rows
    ]

    return {
        "period": {"key": period, "from": p_from, "to": p_to},
        "previous_period": (
            {"from": pp_from, "to": pp_to} if pp_from else None
        ),
        "kpis": kpis,
        "withdrawals_by_method": withdrawals_by_method,
        "deposits_by_type": deposits_by_type,
    }
