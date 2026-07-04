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
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta

from database import get_db, SessionLocal
from auth import get_current_user
import models
from dashboard_router import get_period_dates
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
