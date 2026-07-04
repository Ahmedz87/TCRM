"""
ib_router.py — IB Admin pages
Covers:
- IB list with KPIs and period selector
- IB profile with 5 tabs: Clients, Leads, Commission, Sub-IBs, Referral links
- Commission payment
- IB level promotion
- Sub-IB detection (IB who referred another IB)
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

router = APIRouter(prefix="/ibs", tags=["IBs"])


def period_dates(period: str, date_from: str = "", date_to: str = ""):
    """Return (from_ts, to_ts) for the given period string."""
    now = datetime.now(timezone.utc)
    today = now.date()

    if period == "this_week":
        start = today - __import__('datetime').timedelta(days=today.weekday())
        end = today
    elif period == "last_week":
        start = today - __import__('datetime').timedelta(days=today.weekday() + 7)
        end = start + __import__('datetime').timedelta(days=6)
    elif period == "this_month":
        start = today.replace(day=1)
        end = today
    elif period == "last_month":
        first_this = today.replace(day=1)
        end = first_this - __import__('datetime').timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this_year":
        start = today.replace(month=1, day=1)
        end = today
    elif period == "last_year":
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(year=today.year - 1, month=12, day=31)
    elif period == "custom" and date_from and date_to:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    else:
        start = today.replace(day=1)
        end = today

    return start.isoformat(), end.isoformat()


@router.get("")
async def get_ibs(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort:      str = Query("clients"),
    search:    str = Query(""),
    period:    str = Query("this_month"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    p_from, p_to = period_dates(period, date_from, date_to)
    # index-friendly end bound: end-day-INCLUSIVE -> raw col < (to + 1 day)
    p_to_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()

    where = "WHERE 1=1"
    params: dict = {"p_from": p_from, "p_to": p_to, "p_to_next": p_to_next}
    if search:
        where += " AND (ib.name ILIKE :s OR ib.phone ILIKE :s OR ib.ib_code ILIKE :s OR ib.email ILIKE :s)"
        params["s"] = f"%{search}%"

    sort_col = "total_clients DESC"
    if sort == "volume":    sort_col = "total_volume DESC"
    elif sort == "commission": sort_col = "total_commission DESC"
    elif sort == "unpaid":  sort_col = "unpaid_commission DESC"
    elif sort == "name":    sort_col = "ib.name ASC"

    total = db.execute(text(f"SELECT COUNT(*) FROM ibs ib {where}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT
            ib.id,
            ib.agent_id,
            ib.ib_code,
            ib.name,
            ib.email,
            ib.phone,
            ib.country,
            ib.city,
            ib.ib_level,
            ib.total_clients,
            ib.active_clients,
            ib.total_volume,
            ib.total_commission,
            ib.unpaid_commission,
            ib.paid_commission,
            ib.balance,
            ib.group_name,
            -- Sub-IBs count
            (SELECT COUNT(*) FROM ibs sub WHERE sub.parent_ib_id = ib.id) as sub_ib_count,
            -- Period commission
            (SELECT COALESCE(SUM(ic.commission_usd),0) FROM ib_commissions ic
             WHERE ic.ib_id = ib.id AND ic.trade_date >= :p_from AND ic.trade_date < :p_to_next) as period_commission,
            -- Period volume
            (SELECT COALESCE(SUM(ic.volume),0) FROM ib_commissions ic
             WHERE ic.ib_id = ib.id AND ic.trade_date >= :p_from AND ic.trade_date < :p_to_next) as period_volume
        FROM ibs ib
        {where}
        ORDER BY {sort_col}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    # Global KPIs for the period
    kpis = db.execute(text("""
        SELECT
            COUNT(DISTINCT ib.id) as total_ibs,
            COALESCE(SUM(ib.total_clients),0) as total_clients,
            COALESCE(SUM(ic.commission_usd),0) as period_commission,
            COALESCE(SUM(ic.volume),0) as period_volume,
            (SELECT COALESCE(SUM(unpaid_commission),0) FROM ibs) as total_unpaid,
            (SELECT COUNT(*) FROM ibs WHERE parent_ib_id IS NOT NULL) as total_sub_ibs
        FROM ibs ib
        LEFT JOIN ib_commissions ic ON ic.ib_id = ib.id
            AND ic.trade_date >= :p_from
            AND ic.trade_date < :p_to_next
    """), {"p_from": p_from, "p_to": p_to, "p_to_next": p_to_next}).fetchone()

    return {
        "ibs": [{
            "id":                r[0],
            "agent_id":          r[1],
            "ib_code":           r[2] or "",
            "name":              r[3] or "",
            "email":             r[4] or "",
            "phone":             r[5] or "",
            "country":           r[6] or "",
            "city":              r[7] or "",
            "ib_level":          r[8] or 5,
            "total_clients":     r[9] or 0,
            "active_clients":    r[10] or 0,
            "total_volume":      float(r[11] or 0),
            "total_commission":  float(r[12] or 0),
            "unpaid_commission": float(r[13] or 0),
            "paid_commission":   float(r[14] or 0),
            "balance":           float(r[15] or 0),
            "group_name":        r[16] or "",
            "sub_ib_count":      r[17] or 0,
            "period_commission": float(r[18] or 0),
            "period_volume":     float(r[19] or 0),
            "status":            "active" if (r[15] or 0) > 0 or (r[9] or 0) > 0 else "inactive",
        } for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "kpis": {
            "total_ibs":         kpis[0] or 0,
            "total_clients":     kpis[1] or 0,
            "period_commission": float(kpis[2] or 0),
            "period_volume":     float(kpis[3] or 0),
            "total_unpaid":      float(kpis[4] or 0),
            "total_sub_ibs":     kpis[5] or 0,
        },
        "period": {"from": p_from, "to": p_to},
    }


@router.get("/{ib_id}")
async def get_ib(
    ib_id: int,
    period:    str = Query("this_month"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")

    p_from, p_to = period_dates(period, date_from, date_to)
    p_to_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    params = {"ib_id": ib_id, "agent_id": ib.agent_id, "p_from": p_from, "p_to": p_to, "p_to_next": p_to_next}

    # Period KPIs
    period_kpis = db.execute(text("""
        SELECT
            COALESCE(SUM(ic.commission_usd),0) as commission,
            COALESCE(SUM(ic.volume),0) as volume,
            COUNT(DISTINCT ic.client_login) as active_clients
        FROM ib_commissions ic
        WHERE ic.ib_id = :ib_id
        AND ic.trade_date >= :p_from
        AND ic.trade_date < :p_to_next
    """), params).fetchone()

    # Funnel KPIs — clicks, leads, verified, FTD
    funnel = db.execute(text("""
        SELECT
            COALESCE(SUM(rl.clicks),0) as total_clicks
        FROM referral_links rl
        WHERE rl.ib_id = :ib_id
    """), {"ib_id": ib_id}).fetchone()
    total_clicks = funnel[0] if funnel else 0

    # Leads (registered via this IB)
    leads_count = db.execute(text("""
        SELECT COUNT(*) FROM clients c
        WHERE c.agent = :agent_id
    """), {"agent_id": ib.agent_id}).scalar() or 0

    verified_leads = db.execute(text("""
        SELECT COUNT(*) FROM clients c
        WHERE c.agent = :agent_id AND c.kyc_status = 'verified'
    """), {"agent_id": ib.agent_id}).scalar() or 0

    ftd_count = db.execute(text("""
        SELECT COUNT(DISTINCT c.login) FROM clients c
        JOIN transactions t ON t.login = c.login AND t.tx_type = 'deposit'
        WHERE c.agent = :agent_id
    """), {"agent_id": ib.agent_id}).scalar() or 0

    # Sub-IBs
    sub_ibs = db.query(models.IB).filter(models.IB.parent_ib_id == ib_id).all()

    # Referral links
    ref_links = []
    try:
        links = db.execute(text("""
            SELECT id, name, url, clicks, status, created_at
            FROM referral_links WHERE ib_id = :ib_id
        """), {"ib_id": ib_id}).fetchall()
        ref_links = [{"id": l[0], "name": l[1], "url": l[2], "clicks": l[3], "status": l[4], "created_at": str(l[5])} for l in links]
    except:
        ref_links = []

    # Clients list
    clients = db.query(models.Client).filter(
        models.Client.agent == ib.agent_id
    ).order_by(models.Client.total_deposits.desc()).limit(100).all()

    # Commission details for period
    commissions = db.execute(text("""
        SELECT
            ic.id, ic.client_login, c.name as client_name,
            ic.symbol, ic.volume, ic.pts_per_lot,
            ic.commission_native, ic.quote_currency,
            ic.fx_rate, ic.commission_usd,
            ic.commission_type, ic.trade_date, ic.status
        FROM ib_commissions ic
        LEFT JOIN clients c ON c.login = ic.client_login
        WHERE ic.ib_id = :ib_id
        AND ic.trade_date >= :p_from
        AND ic.trade_date < :p_to_next
        ORDER BY ic.trade_date DESC
        LIMIT 200
    """), params).fetchall()

    return {
        "id":                ib.id,
        "agent_id":          ib.agent_id,
        "ib_code":           ib.ib_code or "",
        "name":              ib.name or "",
        "email":             ib.email or "",
        "phone":             ib.phone or "",
        "country":           ib.country or "",
        "city":              ib.city or "",
        "ib_level":          ib.ib_level or 5,
        "group_name":        ib.group_name or "",
        "balance":           float(ib.balance or 0),
        "total_clients":     ib.total_clients or 0,
        "active_clients":    ib.active_clients or 0,
        "total_volume":      float(ib.total_volume or 0),
        "total_commission":  float(ib.total_commission or 0),
        "unpaid_commission": float(ib.unpaid_commission or 0),
        "paid_commission":   float(ib.paid_commission or 0),
        "period": {
            "from":        p_from,
            "to":          p_to,
            "commission":  float(period_kpis[0] or 0),
            "volume":      float(period_kpis[1] or 0),
            "active_clients": period_kpis[2] or 0,
        },
        "funnel": {
            "clicks":         total_clicks,
            "leads":          leads_count,
            "verified_leads": verified_leads,
            "ftd":            ftd_count,
            "sub_ibs":        len(sub_ibs),
        },
        "clients": [{
            "login":       c.login,
            "name":        c.name or "",
            "phone":       c.phone or "",
            "country":     c.country or "",
            "balance":     float(c.balance or 0),
            "total_dep":   float(c.total_deposits or 0),
            "total_with":  float(c.total_withdrawals or 0),
            "kyc":         c.kyc_status or "pending",
            "reg_date":    str(c.reg_date) if c.reg_date else "",
        } for c in clients],
        "sub_ibs": [{
            "id":           s.id,
            "agent_id":     s.agent_id,
            "ib_code":      s.ib_code or "",
            "name":         s.name or "",
            "ib_level":     s.ib_level or 5,
            "total_clients":s.total_clients or 0,
            "total_volume": float(s.total_volume or 0),
            "total_commission": float(s.total_commission or 0),
            "unpaid_commission": float(s.unpaid_commission or 0),
            "balance":      float(s.balance or 0),
            "status":       "active" if (s.total_clients or 0) > 0 else "inactive",
        } for s in sub_ibs],
        "commissions": [{
            "id":           r[0],
            "client_login": r[1],
            "client_name":  r[2] or f"#{r[1]}",
            "symbol":       r[3] or "",
            "volume":       float(r[4] or 0),
            "pts_per_lot":  float(r[5] or 0),
            "commission_native": float(r[6] or 0),
            "quote_currency": r[7] or "USD",
            "fx_rate":      float(r[8] or 1),
            "commission_usd": float(r[9] or 0),
            "commission_type": r[10] or "direct",
            "trade_date":   str(r[11]) if r[11] else "",
            "status":       r[12] or "unpaid",
        } for r in commissions],
        "referral_links": ref_links,
    }


class PayCommissionRequest(BaseModel):
    ib_id: int
    amount: Optional[float] = None  # None = pay all unpaid


@router.post("/pay-commission")
async def pay_commission(
    data: PayCommissionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ib = db.query(models.IB).filter(models.IB.id == data.ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")

    amount = data.amount or ib.unpaid_commission
    ib.unpaid_commission = max(0, (ib.unpaid_commission or 0) - amount)
    ib.paid_commission   = (ib.paid_commission or 0) + amount

    # Mark commission records as paid
    db.execute(text("""
        UPDATE ib_commissions SET status = 'paid'
        WHERE ib_id = :ib_id AND status = 'unpaid'
    """), {"ib_id": data.ib_id})
    db.commit()
    return {"message": f"Paid ${amount:.2f} to {ib.name}", "remaining": ib.unpaid_commission}


class PromoteIBRequest(BaseModel):
    ib_id: int
    new_level: int


@router.post("/promote")
async def promote_ib(
    data: PromoteIBRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if data.new_level < 5 or data.new_level > 10:
        raise HTTPException(status_code=400, detail="Level must be between 5 and 10")
    ib = db.query(models.IB).filter(models.IB.id == data.ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    ib.ib_level = data.new_level
    db.commit()
    return {"message": f"{ib.name} promoted to level {data.new_level}"}
