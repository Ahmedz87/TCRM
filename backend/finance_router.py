"""
finance_router.py — Finance Management section (ticket #35)

A back-office finance overview built on REAL data from the existing tables.
Read-only on transactions / clients / trading_accounts, plus a small NEW
finance_expenses table (CREATE TABLE IF NOT EXISTS) the admin can add to for
issuing/recording expense invoices.

Auth = get_current_user (staff/admin) like the other admin routers.

Sections / endpoints:
  GET    /finance/overview        — KPIs: total/available liquidity, deposits,
                                     withdrawals, net, per-method balances,
                                     total client balances + credit.
  GET    /finance/ledger          — paginated recent money movements from
                                     transactions, with type/method/date/search
                                     filters.
  GET    /finance/expenses        — list+filter expense invoices.
  POST   /finance/expenses        — add an expense invoice.
  PATCH  /finance/expenses/{id}   — edit / change status of an expense.
  DELETE /finance/expenses/{id}   — delete an expense.

PERF NOTE: transactions.tx_date is a *character varying* holding an ISO
'YYYY-MM-DD HH:MM:SS' string and is indexed (ix_transactions_tx_date). All date
filtering here uses STRING-RANGE comparisons on that column (tx_date >= :f AND
tx_date < :t_next) — NOT ::date casts — so the index is used and we avoid a full
scan (see CLAUDE.md / reports perf note).

── LIQUIDITY FORMULAS (documented for the desk) ──────────────────────────────
  total_liquidity     = SUM(real deposits) − SUM(withdrawals)
                        = net client funds the platform is holding across the
                          whole history. "Real deposits" excludes internal MT5
                          balance-adjustment rows (method='MT5' and the internal
                          fix/cashback/comp labels) which are not genuine client
                          cash in — same exclusion the Deposits view + Reports use,
                          so the figure reconciles with those screens.
  available_liquidity = total_liquidity − pending_withdrawals
                        = funds not already earmarked to leave (withdrawal rows
                          still in a pending/processing/review state).
These are platform-wide (all-time) cash-flow figures, independent of the period
selector (the period only scopes the deposits/withdrawals KPIs + breakdowns).
"""
import io
import csv as _csv
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta

from database import get_db, SessionLocal
from auth import get_current_user
import models
from dashboard_router import get_period_dates
from reports_router import _previous_period_dates, _pct_change
from perf_cache import cached

router = APIRouter(prefix="/finance", tags=["Finance"])

# ── PERFORMANCE: precomputed all-time per-method deposit/withdrawal rollup ────────
# /finance/overview's slow part is the ALL-TIME aggregation of the 2M-row transactions
# table (total liquidity + the per-method breakdown) — done on every cold load. Those
# figures don't depend on the period selector, so we keep a tiny per-method rollup
# (~20 rows) refreshed at most every 5 min and read it instead of full-scanning. Computes
# EXACTLY the same FILTER aggregation, so the numbers are unchanged.
_FIN_AGG_MAX_AGE = 300          # rebuild at most every 5 minutes
_FIN_AGG_LOCK    = 778802       # advisory-lock key (distinct from client_tx_agg's)

# Internal MT5 balance-adjustment marker — NOT a real deposit (mirrors
# transactions_router / reports_router so all the money screens reconcile).
MT5_ADJUST_METHOD = "MT5"
INTERNAL_LABEL_RE = (
    r"(deposit\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance"
    r"|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back"
    r"|credit\s*(in|out)|bonus\s*adjustment)"
)
# TRUE only for a genuine deposit method (used in WHERE clauses where the row is
# aliased as the table directly, i.e. unqualified column names).
NOT_INTERNAL_SQL = "(method <> :mt5_adj AND method !~* :internal_re)"

# Withdrawal statuses that count as "not yet performed" (still earmarked).
PENDING_STATUSES = (
    "pending", "processing", "requested", "review",
    "pending_admin_review", "on_hold",
)

VALID_PERIODS = (
    "today", "this_week", "this_month", "last_month",
    "this_year", "last_year", "all_time",
)

EXPENSE_CATEGORIES = [
    "Salaries", "Marketing", "Office", "Software", "Banking & PSP fees",
    "Travel", "Legal & Compliance", "Bonuses payout", "Infrastructure", "Other",
]
EXPENSE_STATUSES = ["draft", "issued", "approved", "paid", "void"]


def _ensure_finance_agg():
    db = SessionLocal()
    try:
        db.execute(text("SET lock_timeout='4s'"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS finance_method_agg (
                method      TEXT PRIMARY KEY,
                deposits    DOUBLE PRECISION DEFAULT 0,
                withdrawals DOUBLE PRECISION DEFAULT 0,
                dep_cnt     INTEGER DEFAULT 0,
                wd_cnt      INTEGER DEFAULT 0
            )
        """))
        db.execute(text("CREATE TABLE IF NOT EXISTS finance_method_agg_meta (id INT PRIMARY KEY, refreshed_at TIMESTAMPTZ)"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _refresh_finance_agg(db):
    """Rebuild finance_method_agg (all-time per-method dep/wd) if older than _FIN_AGG_MAX_AGE.
    Advisory-locked so only one request rebuilds; DELETE+INSERT in one txn (MVCC-safe)."""
    try:
        row = db.execute(text("SELECT refreshed_at FROM finance_method_agg_meta WHERE id=1")).fetchone()
        from datetime import datetime as _dt, timezone as _tz
        if row and row[0]:
            if (_dt.now(_tz.utc) - row[0]).total_seconds() < _FIN_AGG_MAX_AGE \
               and db.execute(text("SELECT 1 FROM finance_method_agg LIMIT 1")).fetchone():
                return
        if not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _FIN_AGG_LOCK}).scalar():
            return
        try:
            db.execute(text("SET LOCAL idle_in_transaction_session_timeout=0"))
            db.execute(text("DELETE FROM finance_method_agg"))
            # The `method` column has ~130k distinct values (per-row TradeSoft import noise). Keep
            # the top 120 real PSPs by gross volume as themselves and fold the long tail into a single
            # 'Other' row — this keeps the summary table ~121 rows (was 130k → constant 130k-row churn
            # every refresh) WITHOUT changing any total: every transaction is still counted, just the
            # noise tail is aggregated into Other.
            db.execute(text(f"""
                INSERT INTO finance_method_agg (method, deposits, withdrawals, dep_cnt, wd_cnt)
                SELECT CASE WHEN rnk <= 120 THEN method ELSE 'Other' END AS method,
                       SUM(deposits), SUM(withdrawals), SUM(dep_cnt), SUM(wd_cnt)
                FROM (
                  SELECT method, deposits, withdrawals, dep_cnt, wd_cnt,
                         ROW_NUMBER() OVER (ORDER BY (deposits + withdrawals) DESC) AS rnk
                  FROM (
                    SELECT COALESCE(NULLIF(method,''),'Other') AS method,
                           COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit' AND {NOT_INTERNAL_SQL}),0) AS deposits,
                           COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND COALESCE(status,'')<>'rejected'),0) AS withdrawals,
                           COUNT(*) FILTER (WHERE tx_type='deposit' AND {NOT_INTERNAL_SQL}) AS dep_cnt,
                           COUNT(*) FILTER (WHERE tx_type='withdrawal' AND COALESCE(status,'')<>'rejected') AS wd_cnt
                    FROM transactions WHERE tx_type IN ('deposit','withdrawal') GROUP BY 1
                  ) per_method
                ) ranked
                GROUP BY 1
            """), {"mt5_adj": MT5_ADJUST_METHOD, "internal_re": INTERNAL_LABEL_RE})
            db.execute(text("INSERT INTO finance_method_agg_meta (id, refreshed_at) VALUES (1, NOW()) "
                            "ON CONFLICT (id) DO UPDATE SET refreshed_at=NOW()"))
            db.commit()
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _FIN_AGG_LOCK}); db.commit()
    except Exception:
        db.rollback()


_ensure_finance_agg()


# ── Schema bootstrap (additive, idempotent) ──────────────────────────────────
def _ensure_expense_table(db: Session):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS finance_expenses (
            id          SERIAL PRIMARY KEY,
            exp_date    VARCHAR  NOT NULL,           -- 'YYYY-MM-DD'
            payee       VARCHAR  NOT NULL,
            category    VARCHAR  NOT NULL DEFAULT 'Other',
            amount      DOUBLE PRECISION NOT NULL DEFAULT 0,
            currency    VARCHAR  NOT NULL DEFAULT 'USD',
            status      VARCHAR  NOT NULL DEFAULT 'issued',
            note        TEXT,
            invoice_no  VARCHAR,
            created_by  INTEGER,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ
        )
    """))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_finance_expenses_exp_date ON finance_expenses (exp_date)"
    ))
    db.commit()


def _next_day(p_to: str) -> str:
    """Exclusive upper bound for a string-range date filter ('YYYY-MM-DD' -> next day)."""
    try:
        return (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    except Exception:
        return p_to + "~"


# ── Overview KPIs ─────────────────────────────────────────────────────────────
@router.get("/overview")
def finance_overview(
    period: str = Query("this_month"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if period not in VALID_PERIODS:
        period = "this_month"
    # NOT role-scoped: platform-wide finance figures, identical for every staff member
    # (current_user is auth-only). Fixed "all" scope; only `period` varies the result.
    return cached(f"finance:overview:all:{period}", 120,
                  lambda: _build_finance_overview(db, period))


def _build_finance_overview(db, period):
    p_from, p_to = get_period_dates(period)
    p = {
        "f": p_from, "t_next": _next_day(p_to),
        "mt5_adj": MT5_ADJUST_METHOD, "internal_re": INTERNAL_LABEL_RE,
    }

    # ── Period deposits (genuine only) / withdrawals ──
    dep = db.execute(text(f"""
        SELECT COALESCE(SUM(amount),0), COUNT(*)
        FROM transactions
        WHERE tx_type='deposit' AND {NOT_INTERNAL_SQL}
          AND tx_date >= :f AND tx_date < :t_next
    """), p).fetchone()
    wth = db.execute(text("""
        SELECT COALESCE(SUM(amount),0), COUNT(*)
        FROM transactions
        WHERE tx_type='withdrawal' AND COALESCE(status,'')<>'rejected'
          AND tx_date >= :f AND tx_date < :t_next
    """), {"f": p_from, "t_next": _next_day(p_to)}).fetchone()
    deposits = float(dep[0] or 0)
    withdrawals = float(wth[0] or 0)

    # ── ALL-TIME platform cash flow (for liquidity) — read from the precomputed rollup
    # instead of full-scanning 2M rows (refreshed at most every 5 min). ──
    _refresh_finance_agg(db)
    agg = db.execute(text(
        "SELECT COALESCE(SUM(deposits),0), COALESCE(SUM(withdrawals),0) FROM finance_method_agg"
    )).fetchone()
    all_deposits = float(agg[0] or 0)
    all_withdrawals = float(agg[1] or 0)

    # pending (not-yet-performed) withdrawals — earmarked funds
    pend = db.execute(text("""
        SELECT COALESCE(SUM(amount),0), COUNT(*) FROM transactions
        WHERE tx_type='withdrawal' AND LOWER(COALESCE(status,'')) = ANY(:st)
    """), {"st": list(PENDING_STATUSES)}).fetchone()
    pending_withdrawals = float(pend[0] or 0)

    # total_liquidity = net client funds held; available = minus pending withdrawals
    total_liquidity = round(all_deposits - all_withdrawals, 2)
    available_liquidity = round(total_liquidity - pending_withdrawals, 2)

    # ── Client balances snapshot (live equity the platform owes back) ──
    bal = db.execute(text("""
        SELECT COALESCE(SUM(balance),0), COALESCE(SUM(credit),0), COUNT(*)
        FROM trading_accounts
    """)).fetchone()
    client_balance_total = round(float(bal[0] or 0), 2)
    client_credit_total = round(float(bal[1] or 0), 2)

    # ── Payment-method balances (net deposit − withdrawal per method, all-time) ──
    # "QI card / payment-method balances": for each PSP/method, how much net cash
    # has flowed in through it (genuine deposits minus withdrawals paid out on it).
    # read the per-method breakdown straight from the precomputed rollup (refreshed above).
    # The `method` column is polluted with ~130k per-row values (TradeSoft import noise), so we
    # only return the top 60 by net cash — the meaningful PSPs (the long tail is single-tx noise;
    # the liquidity totals above already sum ALL methods, so they're unaffected).
    method_rows = db.execute(text("""
        SELECT method, deposits, withdrawals, (deposits - withdrawals) AS net,
               (dep_cnt + wd_cnt) AS cnt
        FROM finance_method_agg
        WHERE (dep_cnt + wd_cnt) > 0
        ORDER BY net DESC
        LIMIT 60
    """)).fetchall()
    method_label = lambda m: ("Internal / MT5 adjustment"
                              if (m or "").strip().upper() == MT5_ADJUST_METHOD else (m or "Other"))
    payment_methods = [{
        "method": method_label(r[0]),
        "deposits": round(float(r[1] or 0), 2),
        "withdrawals": round(float(r[2] or 0), 2),
        "net": round(float(r[3] or 0), 2),
        "count": int(r[4] or 0),
    } for r in method_rows]

    # ── Expenses recorded in the period (for the net-of-expenses view) ──
    _ensure_expense_table(db)
    exp_period = db.execute(text("""
        SELECT COALESCE(SUM(amount),0), COUNT(*) FROM finance_expenses
        WHERE status <> 'void' AND exp_date >= :f AND exp_date < :t_next
    """), {"f": p_from, "t_next": _next_day(p_to)}).fetchone()
    expenses_period = round(float(exp_period[0] or 0), 2)

    return {
        "period": {"key": period, "from": p_from, "to": p_to},
        "kpis": {
            "total_liquidity": total_liquidity,
            "available_liquidity": available_liquidity,
            "pending_withdrawals": round(pending_withdrawals, 2),
            "pending_withdrawal_count": int(pend[1] or 0),
            "client_balance_total": client_balance_total,
            "client_credit_total": client_credit_total,
            "account_count": int(bal[2] or 0),
            # period-scoped
            "deposits": round(deposits, 2),
            "deposit_count": int(dep[1] or 0),
            "withdrawals": round(withdrawals, 2),
            "withdrawal_count": int(wth[1] or 0),
            "net": round(deposits - withdrawals, 2),
            "expenses_period": expenses_period,
            "expense_count": int(exp_period[1] or 0),
            "net_after_expenses": round(deposits - withdrawals - expenses_period, 2),
            # all-time cash flow (the inputs to the liquidity formula)
            "all_deposits": round(all_deposits, 2),
            "all_withdrawals": round(all_withdrawals, 2),
        },
        "payment_methods": payment_methods,
        "formula": {
            "total_liquidity": "all-time genuine deposits − all-time withdrawals (net client funds held)",
            "available_liquidity": "total liquidity − pending (not-yet-performed) withdrawals",
        },
    }


# ── Ledger (recent money movements) ───────────────────────────────────────────
@router.get("/ledger")
def finance_ledger(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    tx_type: str = Query(""),       # deposit / withdrawal / internal_transfer / bonus_deposit / bonus_withdrawal
    method: str = Query(""),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    where = ["1=1"]
    params: dict = {}
    if tx_type:
        types = [t.strip() for t in tx_type.split(",") if t.strip()]
        if types:
            ph = ",".join(f":ty{i}" for i in range(len(types)))
            where.append(f"t.tx_type IN ({ph})")
            for i, ty in enumerate(types):
                params[f"ty{i}"] = ty
    if method:
        where.append("t.method ILIKE :method")
        params["method"] = f"%{method}%"
    if search:
        where.append("(CAST(t.login AS TEXT) LIKE :s OR c.name ILIKE :s "
                     "OR t.method ILIKE :s OR t.notes ILIKE :s OR t.psp_reference ILIKE :s)")
        params["s"] = f"%{search}%"
    if date_from:
        where.append("t.tx_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("t.tx_date < :date_to_next")
        params["date_to_next"] = _next_day(date_to)

    where_sql = "WHERE " + " AND ".join(where)

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        {where_sql}
    """), params).scalar() or 0

    sum_row = db.execute(text(f"""
        SELECT
          COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='deposit'),0),
          COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='withdrawal'),0)
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        {where_sql}
    """), params).fetchone()

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = db.execute(text(f"""
        SELECT t.id, t.deal_id, t.login, t.tx_type, t.amount, t.method,
               t.currency, t.status, t.tx_date, t.notes, t.psp_reference,
               c.name AS client_name
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        {where_sql}
        ORDER BY t.tx_date DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    items = [{
        "id": r[0],
        "ref_id": r[1],                       # transactions has no ref_id col; deal_id is the reference
        "login": r[2],
        "tx_type": r[3],
        "amount": float(r[4] or 0),
        "method": r[5] or "",
        "currency": r[6] or "USD",
        "status": r[7] or "approved",
        "tx_date": str(r[8]) if r[8] else "",
        "notes": r[9] or "",
        "psp_reference": r[10] or "",
        "client_name": r[11] or (f"#{r[2]}" if r[2] else ""),
    } for r in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "totals": {
            "deposits": round(float(sum_row[0] or 0), 2),
            "withdrawals": round(float(sum_row[1] or 0), 2),
        },
    }


# ── Expenses / invoices ───────────────────────────────────────────────────────
class ExpenseIn(BaseModel):
    exp_date:   str
    payee:      str
    category:   Optional[str] = "Other"
    amount:     float = 0
    currency:   Optional[str] = "USD"
    status:     Optional[str] = "issued"
    note:       Optional[str] = ""
    invoice_no: Optional[str] = ""


class ExpensePatch(BaseModel):
    exp_date:   Optional[str] = None
    payee:      Optional[str] = None
    category:   Optional[str] = None
    amount:     Optional[float] = None
    currency:   Optional[str] = None
    status:     Optional[str] = None
    note:       Optional[str] = None
    invoice_no: Optional[str] = None


@router.get("/expenses")
def list_expenses(
    status: str = Query(""),
    category: str = Query(""),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_expense_table(db)
    where = ["1=1"]
    params: dict = {}
    if status:
        where.append("status = :status")
        params["status"] = status
    if category:
        where.append("category = :category")
        params["category"] = category
    if search:
        where.append("(payee ILIKE :s OR note ILIKE :s OR invoice_no ILIKE :s)")
        params["s"] = f"%{search}%"
    if date_from:
        where.append("exp_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("exp_date < :date_to_next")
        params["date_to_next"] = _next_day(date_to)
    where_sql = "WHERE " + " AND ".join(where)

    rows = db.execute(text(f"""
        SELECT id, exp_date, payee, category, amount, currency, status, note,
               invoice_no, created_at
        FROM finance_expenses
        {where_sql}
        ORDER BY exp_date DESC, id DESC
        LIMIT 1000
    """), params).fetchall()

    tot = db.execute(text(f"""
        SELECT COALESCE(SUM(amount) FILTER (WHERE status<>'void'),0),
               COALESCE(SUM(amount) FILTER (WHERE status='paid'),0),
               COUNT(*)
        FROM finance_expenses {where_sql}
    """), params).fetchone()

    items = [{
        "id": r[0], "exp_date": r[1], "payee": r[2], "category": r[3],
        "amount": float(r[4] or 0), "currency": r[5] or "USD", "status": r[6] or "issued",
        "note": r[7] or "", "invoice_no": r[8] or "",
        "created_at": str(r[9]) if r[9] else "",
    } for r in rows]
    return {
        "items": items,
        "total_amount": round(float(tot[0] or 0), 2),
        "paid_amount": round(float(tot[1] or 0), 2),
        "count": int(tot[2] or 0),
        "categories": EXPENSE_CATEGORIES,
        "statuses": EXPENSE_STATUSES,
    }


@router.post("/expenses")
def add_expense(
    body: ExpenseIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_expense_table(db)
    if not body.payee or not body.payee.strip():
        raise HTTPException(status_code=400, detail="Payee is required")
    if not body.exp_date:
        raise HTTPException(status_code=400, detail="Date is required")
    new_id = db.execute(text("""
        INSERT INTO finance_expenses
          (exp_date, payee, category, amount, currency, status, note, invoice_no, created_by)
        VALUES (:exp_date, :payee, :category, :amount, :currency, :status, :note, :invoice_no, :created_by)
        RETURNING id
    """), {
        "exp_date": body.exp_date.strip(),
        "payee": body.payee.strip(),
        "category": (body.category or "Other").strip(),
        "amount": float(body.amount or 0),
        "currency": (body.currency or "USD").strip(),
        "status": (body.status or "issued").strip(),
        "note": (body.note or "").strip(),
        "invoice_no": (body.invoice_no or "").strip(),
        "created_by": getattr(current_user, "id", None),
    }).scalar()
    db.commit()
    return {"id": new_id, "message": "Expense added"}


@router.patch("/expenses/{exp_id}")
def patch_expense(
    exp_id: int,
    body: ExpensePatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_expense_table(db)
    fields = body.dict(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets, params = [], {"id": exp_id}
    for k, v in fields.items():
        sets.append(f"{k} = :{k}")
        params[k] = v.strip() if isinstance(v, str) else v
    sets.append("updated_at = NOW()")
    res = db.execute(text(f"""
        UPDATE finance_expenses SET {', '.join(sets)} WHERE id = :id RETURNING id
    """), params).scalar()
    if not res:
        db.rollback()
        raise HTTPException(status_code=404, detail="Expense not found")
    db.commit()
    return {"id": exp_id, "message": "Expense updated"}


@router.delete("/expenses/{exp_id}")
def delete_expense(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_expense_table(db)
    res = db.execute(text(
        "DELETE FROM finance_expenses WHERE id = :id RETURNING id"
    ), {"id": exp_id}).scalar()
    db.commit()
    if not res:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"id": exp_id, "message": "Expense deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# P&L / INCOME STATEMENT
# ══════════════════════════════════════════════════════════════════════════════
# A broker income statement built on the SAME established revenue metric the rest of
# the app uses:
#   Revenue  = spread/markup revenue = SUM(deals.markup_profit)/10000 on trades
#              (action 0/1), period-bounded on the indexed deal_date string range
#              (mirrors reports_router / dashboard_router / sales_agents).
#   less IB commissions paid  = SUM(ib_commissions.commission_usd) in the period
#              (money rebated to introducing brokers — a direct cost of revenue).
#   = GROSS PROFIT
#   less Operating expenses    = finance_expenses (status<>void) in the period,
#              broken down by category (Salaries, Marketing, PSP fees, …).
#   = NET PROFIT
# Deposits / withdrawals / net client flow are carried as a CASH-FLOW memo block —
# they are client money movements, not P&L lines, but the desk wants them alongside.
# Every figure is period-bounded and a previous-comparable-period delta is attached.

def _pnl_window(db, p_from, p_to):
    """All P&L figures for one [p_from, p_to] window. Read-only."""
    t_next = _next_day(p_to)
    p = {"f": p_from, "t_next": t_next,
         "mt5_adj": MT5_ADJUST_METHOD, "internal_re": INTERNAL_LABEL_RE}

    markup = db.execute(text("""
        SELECT COALESCE(SUM(d.markup_profit),0)/10000.0
        FROM deals d
        WHERE d.action IN (0,1)
          AND d.deal_date >= :f AND d.deal_date < :t_next
    """), p).scalar() or 0

    ib_cost = db.execute(text("""
        SELECT COALESCE(SUM(commission_usd),0) FROM ib_commissions
        WHERE trade_date IS NOT NULL
          AND trade_date >= :f AND trade_date < :t_next
    """), p).scalar() or 0

    dep = db.execute(text(f"""
        SELECT COALESCE(SUM(amount),0), COUNT(*) FROM transactions
        WHERE tx_type='deposit' AND {NOT_INTERNAL_SQL}
          AND tx_date >= :f AND tx_date < :t_next
    """), p).fetchone()
    wth = db.execute(text("""
        SELECT COALESCE(SUM(amount),0), COUNT(*) FROM transactions
        WHERE tx_type='withdrawal' AND COALESCE(status,'')<>'rejected'
          AND tx_date >= :f AND tx_date < :t_next
    """), {"f": p_from, "t_next": t_next}).fetchone()

    _ensure_expense_table(db)
    exp_rows = db.execute(text("""
        SELECT category, COALESCE(SUM(amount),0), COUNT(*) FROM finance_expenses
        WHERE status <> 'void' AND exp_date >= :f AND exp_date < :t_next
        GROUP BY category ORDER BY 2 DESC
    """), {"f": p_from, "t_next": t_next}).fetchall()

    markup_revenue = round(float(markup or 0), 2)
    ib_commission = round(float(ib_cost or 0), 2)
    deposits = round(float(dep[0] or 0), 2)
    withdrawals = round(float(wth[0] or 0), 2)
    expense_by_cat = [{"category": r[0] or "Other",
                       "amount": round(float(r[1] or 0), 2),
                       "count": int(r[2] or 0)} for r in exp_rows]
    operating_expenses = round(sum(c["amount"] for c in expense_by_cat), 2)
    gross_profit = round(markup_revenue - ib_commission, 2)
    net_profit = round(gross_profit - operating_expenses, 2)

    return {
        "markup_revenue": markup_revenue,
        "ib_commission": ib_commission,
        "gross_profit": gross_profit,
        "operating_expenses": operating_expenses,
        "net_profit": net_profit,
        "expense_by_category": expense_by_cat,
        # cash-flow memo (not P&L lines)
        "deposits": deposits,
        "deposit_count": int(dep[1] or 0),
        "withdrawals": withdrawals,
        "withdrawal_count": int(wth[1] or 0),
        "net_client_flow": round(deposits - withdrawals, 2),
    }


@router.get("/pnl")
def finance_pnl(
    period: str = Query("this_month"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if period not in VALID_PERIODS:
        period = "this_month"
    return cached(f"finance:pnl:all:{period}", 120,
                  lambda: _build_pnl(db, period))


def _build_pnl(db, period):
    p_from, p_to = get_period_dates(period)
    cur = _pnl_window(db, p_from, p_to)
    pp_from, pp_to = _previous_period_dates(period, p_from, p_to)
    prev = _pnl_window(db, pp_from, pp_to) if pp_from else None

    COMPARE_KEYS = [
        "markup_revenue", "ib_commission", "gross_profit",
        "operating_expenses", "net_profit",
        "deposits", "withdrawals", "net_client_flow",
    ]
    lines = {}
    for k in COMPARE_KEYS:
        c = cur[k]
        pv = prev[k] if prev else None
        lines[k] = {"current": c, "previous": pv, "pct_change": _pct_change(c, pv)}

    margin = round(cur["net_profit"] / cur["markup_revenue"] * 100, 1) if cur["markup_revenue"] else None

    return {
        "period": {"key": period, "from": p_from, "to": p_to,
                   "prev_from": pp_from, "prev_to": pp_to},
        "lines": lines,
        "expense_by_category": cur["expense_by_category"],
        "counts": {"deposit": cur["deposit_count"], "withdrawal": cur["withdrawal_count"]},
        "net_margin_pct": margin,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MONTHLY TRENDS (for the charts)
# ══════════════════════════════════════════════════════════════════════════════
def _last_n_months(n: int):
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out.reverse()
    return out


@router.get("/trends")
def finance_trends(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return cached(f"finance:trends:all:{months}", 300,
                  lambda: _build_trends(db, months))


def _build_trends(db, months):
    keys = _last_n_months(months)
    m0 = keys[0]                 # 'YYYY-MM' inclusive lower bound
    m0_date = m0 + "-01"         # for the date-string columns
    base = {k: {"month": k, "deposits": 0.0, "withdrawals": 0.0, "net": 0.0,
                "markup_revenue": 0.0, "ib_commission": 0.0,
                "expenses": 0.0, "profit": 0.0} for k in keys}

    # transactions: genuine deposits + withdrawals by tx_month (indexed)
    for r in db.execute(text(f"""
        SELECT tx_month,
               COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit' AND {NOT_INTERNAL_SQL}),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND COALESCE(status,'')<>'rejected'),0)
        FROM transactions
        WHERE tx_month >= :m0 AND tx_type IN ('deposit','withdrawal')
        GROUP BY tx_month
    """), {"m0": m0, "mt5_adj": MT5_ADJUST_METHOD, "internal_re": INTERNAL_LABEL_RE}).fetchall():
        if r[0] in base:
            base[r[0]]["deposits"] = round(float(r[1] or 0), 2)
            base[r[0]]["withdrawals"] = round(float(r[2] or 0), 2)

    # markup revenue by deal_month (indexed), trades only
    for r in db.execute(text("""
        SELECT deal_month, COALESCE(SUM(markup_profit),0)/10000.0
        FROM deals WHERE action IN (0,1) AND deal_month >= :m0
        GROUP BY deal_month
    """), {"m0": m0}).fetchall():
        if r[0] in base:
            base[r[0]]["markup_revenue"] = round(float(r[1] or 0), 2)

    # IB commission cost by month (trade_date 'YYYY-MM-DD')
    for r in db.execute(text("""
        SELECT substr(trade_date,1,7), COALESCE(SUM(commission_usd),0)
        FROM ib_commissions WHERE trade_date >= :m0d
        GROUP BY 1
    """), {"m0d": m0_date}).fetchall():
        if r[0] in base:
            base[r[0]]["ib_commission"] = round(float(r[1] or 0), 2)

    # operating expenses by month
    _ensure_expense_table(db)
    for r in db.execute(text("""
        SELECT substr(exp_date,1,7), COALESCE(SUM(amount),0)
        FROM finance_expenses WHERE status<>'void' AND exp_date >= :m0d
        GROUP BY 1
    """), {"m0d": m0_date}).fetchall():
        if r[0] in base:
            base[r[0]]["expenses"] = round(float(r[1] or 0), 2)

    series = []
    for k in keys:
        row = base[k]
        row["net"] = round(row["deposits"] - row["withdrawals"], 2)
        row["profit"] = round(row["markup_revenue"] - row["ib_commission"] - row["expenses"], 2)
        series.append(row)

    totals = {
        "deposits": round(sum(r["deposits"] for r in series), 2),
        "withdrawals": round(sum(r["withdrawals"] for r in series), 2),
        "markup_revenue": round(sum(r["markup_revenue"] for r in series), 2),
        "ib_commission": round(sum(r["ib_commission"] for r in series), 2),
        "expenses": round(sum(r["expenses"] for r in series), 2),
        "profit": round(sum(r["profit"] for r in series), 2),
    }
    return {"series": series, "totals": totals, "months": months}


# ── Per-method net cash, broken down month by month, ranked high → low ─────────
# The Overview "payment-method balances" table, but pivoted across the last N months
# instead of a single all-time column. Net per (method, month) = genuine deposits −
# non-rejected withdrawals through that method that month. The `method` column carries
# ~130k noise values, so we keep the top `top` methods by total net over the window as
# themselves and fold the long tail into a single 'Other' row (the totals are unchanged).
@router.get("/method-trends")
def finance_method_trends(
    months: int = Query(12, ge=1, le=36),
    top: int = Query(25, ge=5, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return cached(f"finance:method-trends:all:{months}:{top}", 300,
                  lambda: _build_method_trends(db, months, top))


def _build_method_trends(db, months, top):
    keys = _last_n_months(months)
    m0 = keys[0]
    rows = db.execute(text(f"""
        SELECT COALESCE(NULLIF(method,''),'Other') AS method, tx_month,
               COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit' AND {NOT_INTERNAL_SQL}),0)
             - COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND COALESCE(status,'')<>'rejected'),0) AS net,
               COUNT(*) AS cnt
        FROM transactions
        WHERE tx_type IN ('deposit','withdrawal') AND tx_month >= :m0
        GROUP BY 1, 2
    """), {"m0": m0, "mt5_adj": MT5_ADJUST_METHOD, "internal_re": INTERNAL_LABEL_RE}).fetchall()

    # accumulate per method: {month: net}, total net, total count
    acc: dict = {}
    for method, tx_month, net, cnt in rows:
        if tx_month not in keys:      # ignore any stray month outside the window
            continue
        d = acc.setdefault(method, {"monthly": {}, "total": 0.0, "count": 0})
        d["monthly"][tx_month] = round(float(net or 0), 2)
        d["total"] += float(net or 0)
        d["count"] += int(cnt or 0)

    ranked = sorted(acc.items(), key=lambda kv: kv[1]["total"], reverse=True)
    head, tail = ranked[:top], ranked[top:]

    label = lambda m: ("Internal / MT5 adjustment"
                       if (m or "").strip().upper() == MT5_ADJUST_METHOD else (m or "Other"))

    def pack(method, d):
        return {
            "method": method, "method_label": label(method),
            "total": round(d["total"], 2), "count": d["count"],
            "monthly": {k: round(d["monthly"].get(k, 0.0), 2) for k in keys},
        }

    out = [pack(m, d) for m, d in head]
    if tail:
        folded = {"monthly": {k: 0.0 for k in keys}, "total": 0.0, "count": 0}
        for _m, d in tail:
            folded["total"] += d["total"]; folded["count"] += d["count"]
            for k in keys:
                folded["monthly"][k] += d["monthly"].get(k, 0.0)
        out.append({
            "method": "__other__", "method_label": f"Other ({len(tail)} methods)",
            "total": round(folded["total"], 2), "count": folded["count"],
            "monthly": {k: round(folded["monthly"][k], 2) for k in keys},
        })

    col_totals = {k: round(sum(r["monthly"][k] for r in out), 2) for k in keys}
    return {
        "months": keys,
        "methods": out,
        "column_totals": col_totals,
        "grand_total": round(sum(r["total"] for r in out), 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PSP RECONCILIATION
# ══════════════════════════════════════════════════════════════════════════════
# The desk enters what each PSP's own statement says it is holding for us; we show it
# next to the internal net (genuine deposits − withdrawals through that method, from
# the precomputed finance_method_agg rollup) and the variance. A non-zero variance is
# what to chase with the provider. Statements persist in finance_psp_statements.
def _ensure_recon_table(db: Session):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS finance_psp_statements (
            method            TEXT PRIMARY KEY,
            statement_balance DOUBLE PRECISION DEFAULT 0,
            statement_date    VARCHAR,
            note              TEXT,
            updated_by        INTEGER,
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    db.commit()


@router.get("/reconciliation")
def finance_reconciliation(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_recon_table(db)
    _refresh_finance_agg(db)
    rows = db.execute(text("""
        SELECT a.method, a.deposits, a.withdrawals, (a.deposits - a.withdrawals) AS net,
               (a.dep_cnt + a.wd_cnt) AS cnt,
               s.statement_balance, s.statement_date, s.note, s.updated_at
        FROM finance_method_agg a
        LEFT JOIN finance_psp_statements s ON s.method = a.method
        WHERE (a.dep_cnt + a.wd_cnt) > 0
        ORDER BY net DESC
        LIMIT 80
    """)).fetchall()
    label = lambda m: ("Internal / MT5 adjustment"
                       if (m or "").strip().upper() == MT5_ADJUST_METHOD else (m or "Other"))
    items, matched, total_variance = [], 0, 0.0
    for r in rows:
        net = round(float(r[3] or 0), 2)
        has_stmt = r[5] is not None
        stmt = round(float(r[5] or 0), 2) if has_stmt else None
        variance = round(stmt - net, 2) if has_stmt else None
        if has_stmt:
            if abs(variance) < 0.01:
                matched += 1
            total_variance += variance
        items.append({
            "method": r[0], "method_label": label(r[0]),
            "deposits": round(float(r[1] or 0), 2),
            "withdrawals": round(float(r[2] or 0), 2),
            "net": net, "count": int(r[4] or 0),
            "statement_balance": stmt, "statement_date": r[6] or "",
            "note": r[7] or "", "updated_at": str(r[8]) if r[8] else "",
            "variance": variance,
            "reconciled": has_stmt and abs(variance) < 0.01,
        })
    reconciled_cnt = sum(1 for i in items if i["statement_balance"] is not None)
    return {
        "items": items,
        "summary": {
            "methods": len(items),
            "with_statement": reconciled_cnt,
            "matched": matched,
            "total_variance": round(total_variance, 2),
        },
    }


class ReconIn(BaseModel):
    method:            str
    statement_balance: float = 0
    statement_date:    Optional[str] = ""
    note:              Optional[str] = ""


@router.post("/reconciliation")
def set_reconciliation(
    body: ReconIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_recon_table(db)
    if not body.method or not body.method.strip():
        raise HTTPException(status_code=400, detail="Method is required")
    db.execute(text("""
        INSERT INTO finance_psp_statements
            (method, statement_balance, statement_date, note, updated_by, updated_at)
        VALUES (:method, :bal, :sdate, :note, :uid, NOW())
        ON CONFLICT (method) DO UPDATE SET
            statement_balance = EXCLUDED.statement_balance,
            statement_date    = EXCLUDED.statement_date,
            note              = EXCLUDED.note,
            updated_by        = EXCLUDED.updated_by,
            updated_at        = NOW()
    """), {
        "method": body.method.strip(),
        "bal": float(body.statement_balance or 0),
        "sdate": (body.statement_date or "").strip(),
        "note": (body.note or "").strip(),
        "uid": getattr(current_user, "id", None),
    })
    db.commit()
    return {"method": body.method.strip(), "message": "Statement saved"}


@router.delete("/reconciliation/{method}")
def clear_reconciliation(
    method: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_recon_table(db)
    db.execute(text("DELETE FROM finance_psp_statements WHERE method = :m"), {"m": method})
    db.commit()
    return {"method": method, "message": "Statement cleared"}


# ══════════════════════════════════════════════════════════════════════════════
# CSV EXPORTS
# ══════════════════════════════════════════════════════════════════════════════
def _csv_response(header, rows, filename):
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ledger.csv")
def export_ledger_csv(
    tx_type: str = Query(""),
    method: str = Query(""),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    where = ["1=1"]
    params: dict = {}
    if tx_type:
        types = [t.strip() for t in tx_type.split(",") if t.strip()]
        if types:
            ph = ",".join(f":ty{i}" for i in range(len(types)))
            where.append(f"t.tx_type IN ({ph})")
            for i, ty in enumerate(types):
                params[f"ty{i}"] = ty
    if method:
        where.append("t.method ILIKE :method")
        params["method"] = f"%{method}%"
    if search:
        where.append("(CAST(t.login AS TEXT) LIKE :s OR c.name ILIKE :s "
                     "OR t.method ILIKE :s OR t.notes ILIKE :s OR t.psp_reference ILIKE :s)")
        params["s"] = f"%{search}%"
    if date_from:
        where.append("t.tx_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("t.tx_date < :date_to_next")
        params["date_to_next"] = _next_day(date_to)
    where_sql = "WHERE " + " AND ".join(where)
    rows = db.execute(text(f"""
        SELECT t.tx_date, t.login, c.name, t.tx_type, t.amount, t.currency,
               t.method, t.status, COALESCE(t.psp_reference, CAST(t.deal_id AS TEXT))
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        {where_sql}
        ORDER BY t.tx_date DESC NULLS LAST
        LIMIT 100000
    """), params).fetchall()
    out = [[str(r[0] or ""), r[1], r[2] or "", r[3] or "", float(r[4] or 0),
            r[5] or "USD", r[6] or "", r[7] or "", r[8] or ""] for r in rows]
    return _csv_response(
        ["Date", "Login", "Client", "Type", "Amount", "Currency", "Method", "Status", "Reference"],
        out, "finance_ledger.csv")


@router.get("/expenses.csv")
def export_expenses_csv(
    status: str = Query(""),
    category: str = Query(""),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_expense_table(db)
    where = ["1=1"]
    params: dict = {}
    if status:
        where.append("status = :status"); params["status"] = status
    if category:
        where.append("category = :category"); params["category"] = category
    if search:
        where.append("(payee ILIKE :s OR note ILIKE :s OR invoice_no ILIKE :s)")
        params["s"] = f"%{search}%"
    if date_from:
        where.append("exp_date >= :date_from"); params["date_from"] = date_from
    if date_to:
        where.append("exp_date < :date_to_next"); params["date_to_next"] = _next_day(date_to)
    where_sql = "WHERE " + " AND ".join(where)
    rows = db.execute(text(f"""
        SELECT exp_date, payee, category, amount, currency, status, invoice_no, note
        FROM finance_expenses {where_sql}
        ORDER BY exp_date DESC, id DESC LIMIT 100000
    """), params).fetchall()
    out = [[r[0] or "", r[1] or "", r[2] or "", float(r[3] or 0), r[4] or "USD",
            r[5] or "", r[6] or "", r[7] or ""] for r in rows]
    return _csv_response(
        ["Date", "Payee", "Category", "Amount", "Currency", "Status", "Invoice #", "Note"],
        out, "finance_expenses.csv")


@router.get("/methods.csv")
def export_methods_csv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _refresh_finance_agg(db)
    rows = db.execute(text("""
        SELECT method, deposits, withdrawals, (deposits - withdrawals) AS net,
               (dep_cnt + wd_cnt) AS cnt
        FROM finance_method_agg WHERE (dep_cnt + wd_cnt) > 0 ORDER BY net DESC
    """)).fetchall()
    out = [[r[0] or "Other", float(r[1] or 0), float(r[2] or 0),
            float(r[3] or 0), int(r[4] or 0)] for r in rows]
    return _csv_response(
        ["Method / PSP", "Deposits", "Withdrawals", "Net", "Txns"],
        out, "finance_payment_methods.csv")


@router.get("/pnl.csv")
def export_pnl_csv(
    period: str = Query("this_month"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if period not in VALID_PERIODS:
        period = "this_month"
    d = _build_pnl(db, period)
    L = d["lines"]
    g = lambda k: L[k]["current"]
    out = [
        ["Spread / markup revenue", g("markup_revenue")],
        ["less IB commissions paid", -g("ib_commission")],
        ["Gross profit", g("gross_profit")],
    ]
    for c in d["expense_by_category"]:
        out.append([f"  {c['category']}", -c["amount"]])
    out.append(["Operating expenses (total)", -g("operating_expenses")])
    out.append(["NET PROFIT", g("net_profit")])
    out.append(["", ""])
    out.append(["Deposits (cash-flow memo)", g("deposits")])
    out.append(["Withdrawals (cash-flow memo)", -g("withdrawals")])
    out.append(["Net client flow", g("net_client_flow")])
    return _csv_response(
        ["Line", f"Amount ({d['period']['from']}..{d['period']['to']})"],
        out, f"finance_pnl_{period}.csv")
