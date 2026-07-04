"""
transactions_router.py — Full transaction history with filtering, sorting, review actions
Auto payments: USDT, Ovadraft, Visa/Master (instant approved)
Manual payments: Qi card, ZainCash, AsiaPay, Bank wire (require admin review)
Withdrawals with network ≥6/10 auto-flagged as pending
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, date, timedelta
from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/transactions", tags=["Transactions"])

AUTO_METHODS = {'usdt', 'ovadraft', 'visa/master', 'visa', 'master', 'mastercard'}


class ActionRequest(BaseModel):
    deal_id:  int
    action:   str   # approve / reject / risk
    note:     Optional[str] = ""


@router.get("")
async def get_transactions(
    page:       int   = Query(1, ge=1),
    page_size:  int   = Query(20, ge=1, le=500),
    tx_type:    str   = Query("deposit"),
    sort:       str   = Query("date"),
    sort_dir:   str   = Query("desc"),
    search:     str   = Query(""),
    method:     str   = Query(""),
    status:     str   = Query(""),
    agent:      str   = Query(""),
    ib:         str   = Query(""),
    date_from:  str   = Query(""),
    date_to:    str   = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Map tx_type to DB types
    type_map = {
        "deposit":           ["deposit"],
        "withdrawal":        ["withdrawal"],
        "internal_transfer": ["internal_transfer"],
        "bonus":             ["bonus_deposit", "bonus_withdrawal"],
    }
    types = type_map.get(tx_type, ["deposit"])

    types_str = "','".join(types)
    where_parts = [f"t.tx_type IN ('{types_str}')"]
    params: dict = {}

    if search:
        where_parts.append("(CAST(t.login AS TEXT) LIKE :s OR c.name ILIKE :s OR t.method ILIKE :s OR t.notes ILIKE :s)")
        params["s"] = f"%{search}%"
    if method:
        where_parts.append("t.method ILIKE :method")
        params["method"] = f"%{method}%"
    if status:
        where_parts.append("t.status = :status")
        params["status"] = status
    if agent:
        where_parts.append("u.full_name ILIKE :agent")
        params["agent"] = f"%{agent}%"
    if ib:
        where_parts.append("ib.name ILIKE :ib")
        params["ib"] = f"%{ib}%"
    if date_from:
        # index-friendly: raw column compared to a date string (no ::date cast)
        where_parts.append("t.tx_date >= :date_from")
        params["date_from"] = date_from[:10]
    if date_to:
        # end-day-INCLUSIVE: old `::date <= :date_to` covered all of day date_to.
        # equivalent index-friendly bound = raw column < (date_to + 1 day).
        where_parts.append("t.tx_date < :date_to_next")
        params["date_to_next"] = (
            datetime.strptime(date_to[:10], "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()

    where = "WHERE " + " AND ".join(where_parts)

    sort_col = {
        "date":   "t.tx_date",
        "amount": "t.amount",
    }.get(sort, "t.tx_date")
    sort_dir_sql = "DESC" if sort_dir == "desc" else "ASC"

    # Total count
    count_sql = f"""
        SELECT COUNT(*)
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        LEFT JOIN client_assignments ca ON ca.login = t.login
        LEFT JOIN users u ON u.id = ca.agent_id
        LEFT JOIN ibs ib ON ib.agent_id = c.agent
        {where}
    """
    total = db.execute(text(count_sql), params).scalar() or 0

    # Main query
    query_sql = f"""
        SELECT
            t.id,
            t.deal_id,
            t.login,
            t.tx_type,
            t.amount,
            t.method,
            t.status,
            t.tx_date,
            t.notes,
            c.name       as client_name,
            c.agent      as agent_id,
            c.total_deposits as total_deposits,
            c.total_withdrawals as total_withdrawals,
            c.balance    as balance,
            c.equity     as equity,
            c.group_name as group_name,
            u.full_name  as agent_name,
            ib.name      as ib_name,
            ib.ib_code   as ib_code,
            -- Network score
            (SELECT COUNT(*) FROM network_edges ne
             WHERE ne.login_a = t.login OR ne.login_b = t.login) as network_score,
            -- Total tx count for this client
            (SELECT COUNT(*) FROM transactions t2
             WHERE t2.login = t.login AND t2.tx_type IN ('deposit','withdrawal')) as tx_count
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        LEFT JOIN client_assignments ca ON ca.login = t.login
        LEFT JOIN users u ON u.id = ca.agent_id
        LEFT JOIN ibs ib ON ib.agent_id = c.agent
        {where}
        ORDER BY {sort_col} {sort_dir_sql}
        LIMIT :limit OFFSET :offset
    """
    params["limit"]  = page_size
    params["offset"] = (page - 1) * page_size

    rows = db.execute(text(query_sql), params).fetchall()

    # Extract wallet type and ID from notes
    def parse_wallet(method: str, notes: str) -> tuple:
        if not notes:
            return method or "", ""
        # notes format: "Deposit - Qi card - 07810 1234 5678 — Samer Aziz"
        parts = [p.strip() for p in (notes or "").split("-")]
        wallet_id = " — ".join(parts[2:]).strip() if len(parts) > 2 else ""
        return method or "", wallet_id

    def get_abuse_flag(net_score: int, tx_type: str, amount: float) -> str:
        if tx_type != "withdrawal":
            return ""
        if net_score >= 7:
            return "High network risk"
        return ""

    transactions = []
    for r in rows:
        wallet_type, wallet_id = parse_wallet(r[5], r[8])
        net_score = min(10, (r[19] or 0) // 10)
        abuse_flag = get_abuse_flag(net_score, r[3], float(r[4] or 0))

        transactions.append({
            "id":               r[0],
            "deal_id":          r[1],
            "login":            r[2],
            "tx_type":          r[3],
            "amount":           float(r[4] or 0),
            "method":           r[5] or "",
            "status":           r[6] or "approved",
            "tx_date":          r[7].isoformat() if r[7] else "",
            "notes":            r[8] or "",
            "client_name":      r[9] or f"#{r[2]}",
            "total_deposits":   float(r[11] or 0),
            "total_withdrawals":float(r[12] or 0),
            "balance":          float(r[13] or 0),
            "equity":           float(r[14] or 0),
            "group":            r[15] or "",
            "leverage":         "1:100",
            "agent_name":       r[16] or "",
            "ib_name":          r[17] or "",
            "ib_code":          r[18] or "",
            "network_score":    net_score,
            "tx_count":         r[20] or 0,
            "wallet_type":      wallet_type,
            "wallet_id":        wallet_id,
            "abuse_flag":       abuse_flag,
        })

    # KPIs — "today" computed in Python so the FILTER compares the raw column to
    # date strings (index-friendly, identical result to ::date = CURRENT_DATE).
    _today = date.today()
    params["kpi_today"] = _today.isoformat()
    params["kpi_today_next"] = (_today + timedelta(days=1)).isoformat()
    kpi_sql = f"""
        SELECT
            COALESCE(SUM(t.amount),0) as total_amount,
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE t.status IN ('pending','processing')) as pending_count,
            COALESCE(AVG(t.amount),0) as avg_amount,
            COALESCE(SUM(t.amount) FILTER (WHERE t.tx_date >= :kpi_today AND t.tx_date < :kpi_today_next),0) as today_amount,
            COUNT(*) FILTER (WHERE t.tx_type = 'deposit') as deposit_count,
            COUNT(*) FILTER (WHERE t.tx_type = 'withdrawal') as withdrawal_count,
            COUNT(*) FILTER (WHERE t.tx_type = 'internal_transfer') as transfer_count,
            COUNT(*) FILTER (WHERE t.tx_type IN ('bonus_deposit','bonus_withdrawal')) as bonus_count
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        LEFT JOIN client_assignments ca ON ca.login = t.login
        LEFT JOIN users u ON u.id = ca.agent_id
        LEFT JOIN ibs ib ON ib.agent_id = c.agent
        {where}
    """
    krow = db.execute(text(kpi_sql), params).fetchone()

    return {
        "transactions": transactions,
        "total":        total,
        "page":         page,
        "page_size":    page_size,
        "kpis": {
            "total_amount":      float(krow[0] or 0),
            "total_count":       krow[1] or 0,
            "pending_count":     krow[2] or 0,
            "avg_amount":        float(krow[3] or 0),
            "today_amount":      float(krow[4] or 0),
            "deposit_count":     krow[5] or 0,
            "withdrawal_count":  krow[6] or 0,
            "transfer_count":    krow[7] or 0,
            "bonus_count":       krow[8] or 0,
            "flagged_count":     0,
        },
    }


@router.post("/action")
async def transaction_action(
    data: ActionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    tx = db.query(models.Transaction).filter(models.Transaction.deal_id == data.deal_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if data.action == "approve":
        tx.status = "approved"
        # TODO: trigger MT5 credit via bridge
    elif data.action == "reject":
        tx.status = "rejected"
    elif data.action == "risk":
        tx.status = "pending"
        tx.notes  = (tx.notes or "") + f" | Sent to risk: {data.note}"

    if data.note and data.action != "risk":
        tx.notes = (tx.notes or "") + f" | Review note: {data.note}"

    db.commit()
    return {"message": f"Transaction {data.action}d successfully"}
