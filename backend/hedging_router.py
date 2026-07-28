"""
hedging_router.py — Hedging (Behavioral Client-Flow) project API (READ-ONLY / analysis only).

Surfaces the Hedging analysis project inside the CRM. This router NEVER writes: no client
account, balance, order, bonus or transaction is created or modified. It only reads `deals`
and reports financial facts (Phase 2 §5 reconstruction) plus the project's phase/data status.

Endpoints (admin analytical tab):
    GET /hedging/status              -> phase + data-availability summary (+ light live counts)
    GET /hedging/account/{login}     -> §5 reconstruction for one account (Table 1 row)
    GET /hedging/accounts            -> capped aggregate list, biggest reconciliation break first

Classification of money movements mirrors build_transactions.py (the CRM's canonical logic),
so figures tie to the existing Finance/Deposits totals. See cbook/ docs for the methodology.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models

# Access is restricted to these staff emails ONLY (case-insensitive) — not all admins.
HEDGING_EMAILS = {"abbask@tnfx.co", "ahmedz@tnfx.co"}


def _require_hedging_access(current_user: models.User = Depends(get_current_user)):
    """Hard email allowlist — 403 for everyone else, including other admins."""
    if (getattr(current_user, "email", "") or "").strip().lower() not in HEDGING_EMAILS:
        raise HTTPException(403, "Not authorized for the Hedging section")
    return current_user


# Router-level dependency => every endpoint below enforces the allowlist.
router = APIRouter(prefix="/hedging", tags=["Hedging (analysis)"],
                   dependencies=[Depends(_require_hedging_access)])

# ── canonical per-deal classification (mirrors build_transactions.py + cbook_cash_movements) ──
# Produces `kind` and `signed_delta` (balance impact) for every money-affecting deal.
_MOVEMENTS_CTE = r"""
mv AS (
    SELECT
        d.login, d.action, d.profit,
        COALESCE(d.commission,0) AS commission,
        COALESCE(d.swap,0)       AS swap,
        COALESCE(d.volume,0)     AS volume,
        d.balance_after, d.deal_time,
        CASE
            WHEN d.action IN (0,1) THEN 'trade'
            WHEN d.action = 2 AND d.comment ILIKE '%transfer%' THEN 'internal_transfer'
            WHEN d.action = 2 AND d.comment ~* 'revert.*withdraw' THEN 'withdrawal_revert'
            WHEN d.action = 2 AND d.comment ~* 'abus' THEN 'abuse_clawback'
            WHEN d.action = 2
                 AND d.comment !~* '(qi ?card|zain\w*|asiapay|asiahawala|usdt|tether|al ?taif|sham|perfect ?money|wallet|advcash|airtm|paymaxis|bridger|ptop|web ?money|cryptomus|payeer|fasapay)'
                 AND (COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'),' - ',2)),''), d.platform) = 'MT5'
                      OR COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'),' - ',2)),''), d.platform)
                         ~* '(deposit\s*[/ ]?\s*fix|withdraw\w*\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back|credit\s*(in|out)|bonus\s*adjustment|\ysync\y)')
                 THEN CASE WHEN d.comment ~* 'negative\s*balance' THEN 'negative_cover' ELSE 'balance_fix' END
            WHEN d.action = 2 AND d.profit > 0 THEN 'deposit'
            WHEN d.action = 2 AND d.profit < 0 THEN 'withdrawal'
            WHEN d.action IN (3,6) AND d.profit > 0 THEN 'bonus_deposit'
            WHEN d.action IN (3,6) AND d.profit < 0 THEN 'bonus_withdrawal'
            ELSE 'unclassified'
        END AS kind,
        CASE WHEN d.action IN (0,1)
             THEN COALESCE(d.profit,0)+COALESCE(d.commission,0)+COALESCE(d.swap,0)
             ELSE COALESCE(d.profit,0) END AS signed_delta
    FROM deals d
    WHERE {where}
      AND COALESCE(d.comment,'') NOT ILIKE 'PP on%'
      AND (d.action IN (0,1) OR (d.action IN (2,3,6) AND d.profit <> 0))
)
"""

# The §5 aggregation selected out of the mv CTE (grouped by login).
_AGG = """
SELECT
    login,
    COALESCE(SUM(profit) FILTER (WHERE kind='deposit'),0)                         AS net_completed_deposits,
    COALESCE(COUNT(*)    FILTER (WHERE kind='deposit'),0)                         AS n_deposits,
    COALESCE(-SUM(profit) FILTER (WHERE kind='withdrawal'),0)
      - COALESCE(SUM(profit) FILTER (WHERE kind='withdrawal_revert'),0)          AS net_completed_withdrawals,
    COALESCE(COUNT(*)    FILTER (WHERE kind='withdrawal'),0)                      AS n_withdrawals,
    COALESCE(SUM(profit) FILTER (WHERE kind='internal_transfer'),0)              AS net_internal_transfers,
    COALESCE(SUM(profit) FILTER (WHERE kind IN ('bonus_deposit','bonus_withdrawal')),0) AS net_bonus_credit,
    COALESCE(SUM(profit) FILTER (WHERE kind IN ('balance_fix','negative_cover')),0)     AS net_balance_fix,
    COALESCE(SUM(profit) FILTER (WHERE kind='abuse_clawback'),0)                 AS net_abuse_clawback,
    COALESCE(SUM(profit)     FILTER (WHERE kind='trade'),0)                       AS realized_gross_pnl,
    COALESCE(SUM(commission) FILTER (WHERE kind='trade'),0)                       AS commission_total,
    COALESCE(SUM(swap)       FILTER (WHERE kind='trade'),0)                       AS swap_total,
    COALESCE(COUNT(*)        FILTER (WHERE kind='trade'),0)                       AS n_trades,
    COALESCE(SUM(volume)     FILTER (WHERE kind='trade'),0)                       AS volume_lots,
    COALESCE(SUM(profit) FILTER (WHERE kind='unclassified'),0)                    AS unclassified_amount,
    ROUND(COALESCE(SUM(signed_delta),0)::numeric, 2)                              AS reconstructed_closing_balance
FROM mv GROUP BY login
"""


def _row_dict(r):
    d = dict(r._mapping)
    d["realized_net_pnl"] = round(
        float(d["realized_gross_pnl"]) + float(d["commission_total"]) + float(d["swap_total"]), 2)
    d["currency"] = "USD"          # single-currency assumption (FX deferred)
    d["period"] = "ALL"
    return d


# ── Phase / data-availability status (from the cbook/ audit docs) ─────────────
_STATUS = {
    "project": "Hedging — Behavioral Client-Flow",
    "read_only": True,
    "note": "Analysis & classification only. No client account, balance, order or transaction is ever modified.",
    "phases": [
        {"n": 1, "name": "Data Inventory, Feasibility & Quality Audit", "state": "partial"},
        {"n": 2, "name": "Financial Facts, Accounting Logic & Reconciliation", "state": "in_progress",
         "detail": "§5 Client Account Financial Reconstruction is live (this tab). FX deferred (single-currency USD)."},
        {"n": 3, "name": "Client Classification & Behavioral Clustering", "state": "spec_loaded"},
        {"n": 4, "name": "Hedging strategy research & backtesting", "state": "not_started"},
    ],
    "buildable": [
        "Client account financial reconstruction (deposits, withdrawals, transfers, bonuses, realized P&L, balance)",
        "Aggregate client book & reconciliation",
        "Behavioral features from round-trip pairing (hold time, sizing, martingale/grid, sessions, stability)",
        "Linked-account detection (IP/CID/MQID/copy networks)",
    ],
    "blocked": [
        {"item": "Directional features (MFE/MAE, expectancy@horizon) & Reverse Edge", "reason": "no historical price/tick series in the CRM"},
        {"item": "Stop-loss / take-profit discipline", "reason": "no SL/TP fields on deals (maybe recoverable from mt5_raw_data)"},
        {"item": "LP accounts, hedging, real A/B/C book split", "reason": "no LP / routing data exists"},
        {"item": "FX reporting-currency conversion", "reason": "no exchange-rate table"},
        {"item": "Payment-processing costs, CAC/company cash-flow", "reason": "no cost/opex source"},
    ],
}


@router.get("/status")
def status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    out = dict(_STATUS)
    # light, cheap live counts (best-effort; never fail the page)
    try:
        db.execute(text("SET LOCAL statement_timeout = '15s'"))
        row = db.execute(text(
            "SELECT COUNT(*) AS accounts, "
            "COUNT(*) FILTER (WHERE COALESCE(total_deposits,0) > 0) AS funded "
            "FROM clients")).fetchone()
        out["counts"] = {"accounts": row[0] or 0, "funded_accounts": row[1] or 0}
    except Exception as e:
        db.rollback()
        out["counts"] = {"error": str(e)}
    return out


@router.get("/account/{login}")
def account(login: int, db: Session = Depends(get_db),
            current_user: models.User = Depends(get_current_user)):
    """§5 reconstruction for one account. Cheap (login is indexed on deals)."""
    db.execute(text("SET LOCAL statement_timeout = '30s'"))
    cte = _MOVEMENTS_CTE.format(where="d.login = :login")
    row = db.execute(text(f"WITH {cte} {_AGG}"), {"login": login}).fetchone()
    if not row:
        raise HTTPException(404, f"No money-affecting deals found for account {login}")
    rep = db.execute(text(f"""
        WITH {cte}
        SELECT balance_after FROM mv
        WHERE balance_after IS NOT NULL ORDER BY deal_time DESC LIMIT 1
    """), {"login": login}).fetchone()
    d = _row_dict(row)
    d["opening_balance"] = 0.0
    d["reported_closing_balance"] = float(rep[0]) if rep and rep[0] is not None else None
    d["balance_break"] = (round(d["reconstructed_closing_balance"] - d["reported_closing_balance"], 2)
                          if d["reported_closing_balance"] is not None else None)
    # client name/context (read-only)
    c = db.execute(text(
        "SELECT name, country, platform, client_status, balance, equity "
        "FROM clients WHERE login = :login LIMIT 1"), {"login": login}).fetchone()
    if c:
        d["client"] = {"name": c[0], "country": c[1], "platform": c[2],
                       "status": c[3], "live_balance": c[4], "live_equity": c[5]}
        if c[5] is not None and c[4] is not None:
            d["unrealized_pnl"] = round(float(c[5]) - float(c[4]), 2)      # live snapshot UPL
            d["closing_equity"] = round(d["reconstructed_closing_balance"] + d["unrealized_pnl"], 2)
    return d


@router.get("/accounts")
def accounts(limit: int = Query(50, ge=1, le=500),
             min_deposits: float = Query(0.0, ge=0),
             order: str = Query("break", pattern="^(break|deposits|net_pnl)$"),
             db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    """Capped aggregate reconstruction across accounts. Heavier (scans deals) — hard-capped
    and time-limited. Default order = biggest reconciliation break first (audit view)."""
    db.execute(text("SET LOCAL statement_timeout = '120s'"))
    cte = _MOVEMENTS_CTE.format(where="TRUE")
    order_sql = {
        "break":    "ABS(a.reconstructed_closing_balance - COALESCE(rep.reported_closing_balance,0)) DESC",
        "deposits": "a.net_completed_deposits DESC",
        "net_pnl":  "(a.realized_gross_pnl + a.commission_total + a.swap_total) DESC",
    }[order]
    rows = db.execute(text(f"""
        WITH {cte},
        agg AS ({_AGG}),
        rep AS (
            SELECT DISTINCT ON (login) login, balance_after AS reported_closing_balance
            FROM mv WHERE balance_after IS NOT NULL ORDER BY login, deal_time DESC
        )
        SELECT a.*, rep.reported_closing_balance
        FROM agg a LEFT JOIN rep USING (login)
        WHERE a.net_completed_deposits >= :min_deposits
        ORDER BY {order_sql}
        LIMIT :limit
    """), {"min_deposits": min_deposits, "limit": limit}).fetchall()
    out = []
    for r in rows:
        d = _row_dict(r)
        d["reported_closing_balance"] = (float(d["reported_closing_balance"])
                                         if d.get("reported_closing_balance") is not None else None)
        d["balance_break"] = (round(d["reconstructed_closing_balance"] - d["reported_closing_balance"], 2)
                              if d["reported_closing_balance"] is not None else None)
        out.append(d)
    return {"count": len(out), "order": order, "limit": limit, "accounts": out}
