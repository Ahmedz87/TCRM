# -*- coding: utf-8 -*-
"""
monthly_report_core.py — shared computation for the Monthly / Quarterly / Half-year report.

Extends the legacy hand-maintained "Monthly Report.xlsx" with the months that were never
filled in. All figures are computed FRESH from the live broker_crm DB with documented,
internally-consistent definitions (the historical hand-kept numbers used MT-server snapshots
and are not reproducible from the current reconciled DB — see CLAUDE.md). Definitions:

  reg_accounts  : client accounts whose clients.reg_date falls in the period (all platforms)
  verified      : of those, kyc_status = 'verified'
  kyc_pending   : kyc uploaded but not verified (pending / pending_review / pending_admin_review / docs_needed)
  no_kyc        : no kyc on file (kyc_status NULL or 'exists')
  nda           : New Depositing Accounts — distinct PERSONS (by phone) whose first-ever
                  deposit happened in the period
  dep_clients   : distinct logins that made >=1 deposit in the period
  wd_clients    : distinct logins that made >=1 withdrawal in the period
  deposits      : sum of deposit amounts ($)
  withdrawals   : sum of |withdrawal| amounts ($)
  net           : deposits - withdrawals ($)
  dep_count     : number of deposit transactions
  wd_count      : number of withdrawal transactions
  volume_lots   : traded lots (deals action 0/1, volume/10000)
  markup        : broker markup revenue ($) on those trades (markup_profit/10000)

A period is a half-open [start, end) date range. Month/Quarter/Half rows are all computed
the same way over their own range, so quarter/half person-counts are true distinct counts
(NOT sums of months — that would double-count a person active in two months).
"""
from datetime import date

MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# additive across months; person-distinct fields (nda/dep_clients/wd_clients) are recomputed per range
ADDITIVE = ["reg_accounts", "verified", "kyc_pending", "no_kyc",
            "deposits", "withdrawals", "net", "dep_count", "wd_count",
            "volume_lots", "markup"]
DISTINCT = ["nda", "dep_clients", "wd_clients"]
ALL_FIELDS = ADDITIVE + DISTINCT


# Canonical money filters — kept IDENTICAL to dashboard_router._DEP / _WD so the Monthly Report
# totals equal the Dashboard (single source of truth for "genuine deposit" / "real withdrawal").
_DEP_WHERE = (r"tx_type='deposit' AND amount < 1000000 AND COALESCE(method,'') <> 'MT5' "
              r"AND COALESCE(method,'') !~* '(deposit\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee"
              r"|negative\s*balance|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back"
              r"|credit\s*(in|out)|bonus\s*adjustment)'")
_WD_WHERE = "tx_type='withdrawal' AND amount < 1000000 AND COALESCE(status,'') <> 'rejected'"


def _month_bounds(year, month):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def compute_range(execq, start, end):
    """execq(sql, params) -> list of rows (tuples). start/end are date objects (half-open)."""
    sd, ed = start.isoformat(), end.isoformat()
    r = {}

    # registration funnel (reg_date is varchar 'YYYY-MM-DD' -> ISO lexical compare is safe)
    row = execq("""
        SELECT count(*)                                                                    AS reg,
               count(*) FILTER (WHERE kyc_status = 'verified')                             AS ver,
               count(*) FILTER (WHERE kyc_status IN ('pending','pending_review','pending_admin_review','docs_needed')) AS kp,
               count(*) FILTER (WHERE kyc_status IS NULL OR kyc_status = 'exists')         AS nk
        FROM clients
        WHERE reg_date >= :sd AND reg_date < :ed
    """, {"sd": sd, "ed": ed})[0]
    r["reg_accounts"], r["verified"], r["kyc_pending"], r["no_kyc"] = (
        int(row[0]), int(row[1]), int(row[2]), int(row[3]))

    # deposits — GENUINE client deposits only, MUST match dashboard_router._DEP so the Monthly
    # Report equals the Dashboard: exclude internal MT balance adjustments (method='MT5' or an
    # internal-label method) and the >=$1M rows. (_dup / balance_fix / negative_cover are already
    # a different tx_type, so tx_type='deposit' already drops them.)
    row = execq(f"""
        SELECT count(DISTINCT login), coalesce(sum(amount),0), count(*)
        FROM transactions
        WHERE {_DEP_WHERE} AND tx_date >= :sd AND tx_date < :ed
    """, {"sd": sd, "ed": ed})[0]
    r["dep_clients"], r["deposits"], r["dep_count"] = int(row[0]), float(row[1]), int(row[2])

    # withdrawals — REAL withdrawals only (matches dashboard_router._WD): exclude REJECTED ones
    # (a rejected withdrawal was reverted/refunded, so the money never left) and the >=$1M rows.
    row = execq(f"""
        SELECT count(DISTINCT login), coalesce(sum(abs(amount)),0), count(*)
        FROM transactions
        WHERE {_WD_WHERE} AND tx_date >= :sd AND tx_date < :ed
    """, {"sd": sd, "ed": ed})[0]
    r["wd_clients"], r["withdrawals"], r["wd_count"] = int(row[0]), float(row[1]), int(row[2])

    r["net"] = r["deposits"] - r["withdrawals"]

    # NDA — distinct persons whose first-ever deposit lands in [start,end)
    row = execq("""
        WITH d AS (
            SELECT coalesce(c.phone, t.login::text) AS pk, t.tx_date
            FROM transactions t JOIN clients c ON c.login = t.login
            WHERE t.tx_type = 'deposit'
        ),
        fd AS (SELECT pk, min(tx_date) AS f FROM d GROUP BY pk)
        SELECT count(*) FROM fd WHERE f >= :sd AND f < :ed
    """, {"sd": sd, "ed": ed})[0]
    r["nda"] = int(row[0])

    # trading volume + markup revenue (deal_date is varchar 'YYYY-MM-DD')
    row = execq("""
        SELECT coalesce(sum(volume),0)/10000.0, coalesce(sum(markup_profit),0)/10000.0
        FROM deals
        WHERE action IN (0,1) AND deal_date >= :sd AND deal_date < :ed
    """, {"sd": sd, "ed": ed})[0]
    r["volume_lots"], r["markup"] = float(row[0]), float(row[1])

    return r


def build_report(execq, year, through_month, today=None):
    """Build month rows (Jan..through_month of `year`) + quarter + half-year rollups.
    The current calendar month is flagged partial. Returns a JSON-able dict."""
    today = today or date.today()
    months = []
    for m in range(1, through_month + 1):
        s, e = _month_bounds(year, m)
        row = compute_range(execq, s, e)
        row["month"] = f"{year}-{m:02d}"
        row["label"] = f"{year} - {MONTH_ABBR[m]}"
        row["partial"] = (year == today.year and m == today.month)
        months.append(row)

    def rollup(label, m_start, m_end):
        s, _ = _month_bounds(year, m_start)
        _, e = _month_bounds(year, min(m_end, through_month))
        row = compute_range(execq, s, e)
        row["label"] = label
        row["months"] = f"{MONTH_ABBR[m_start]}–{MONTH_ABBR[min(m_end, through_month)]}"
        row["partial"] = (m_end >= today.month and year == today.year)
        return row

    quarters, halves = [], []
    quarter_defs = [("Q1", 1, 3), ("Q2", 4, 6), ("Q3", 7, 9), ("Q4", 10, 12)]
    for name, qs, qe in quarter_defs:
        if qs <= through_month:
            quarters.append(rollup(f"{name} {year}", qs, qe))
    if through_month >= 1:
        halves.append(rollup(f"H1 {year}", 1, 6))
    if through_month >= 7:
        halves.append(rollup(f"H2 {year}", 7, 12))

    return {
        "year": year,
        "through_month": through_month,
        "generated_at": today.isoformat(),
        "fields": ALL_FIELDS,
        "months": months,
        "quarters": quarters,
        "halves": halves,
    }
