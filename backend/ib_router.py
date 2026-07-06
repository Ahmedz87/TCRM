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
import rbac
import ib_challenges
from perf_cache import cached

router = APIRouter(prefix="/ibs", tags=["IBs"])

# commission points: FX pairs + gold (XAU*) earn the IB's level per lot; everything else 1.
_CUR = "USD|EUR|GBP|JPY|AUD|NZD|CAD|CHF|TRY|ZAR|MXN|SGD|HKD|NOK|SEK|DKK|PLN|CNH|CZK|HUF|RUB|INR|THB|CNY"
FX_OR_GOLD = (
    "(d.symbol ILIKE 'XAU%' OR upper(regexp_replace(d.symbol,'[^A-Za-z]','','g')) "
    f"~ '^({_CUR})({_CUR})')"
)
TIER_NAMES = {5: "Bronze", 6: "Silver", 7: "Gold", 8: "Diamond", 9: "Elite", 10: "Master"}


def get_status_thresholds(db):
    """IB status is based on how many of the IB's clients traded in the period.
    Thresholds are configurable (Settings). Defaults: low>=3, active>=5."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_status_config (
            id INT PRIMARY KEY DEFAULT 1,
            low_min INT DEFAULT 3,
            active_min INT DEFAULT 5
        )
    """))
    db.execute(text("INSERT INTO ib_status_config (id, low_min, active_min) VALUES (1,3,5) ON CONFLICT (id) DO NOTHING"))
    db.commit()
    r = db.execute(text("SELECT low_min, active_min FROM ib_status_config WHERE id=1")).fetchone()
    return (r[0] or 3), (r[1] or 5)


def ib_status_for(trading_clients: int, low_min: int, active_min: int) -> str:
    if trading_clients >= active_min: return "active"
    if trading_clients >= low_min:    return "low"
    if trading_clients >= 1:          return "inactive"
    return "super_inactive"


def can_change_ib_level(user) -> bool:
    """Only Zainab may change an IB's level (admin kept as a system failsafe)."""
    role  = (getattr(user, "role", "") or "").lower()
    name  = (getattr(user, "full_name", "") or "").lower()
    email = (getattr(user, "email", "") or "").lower()
    return role == "admin" or "zainab" in name or email.startswith("zainabw")


def period_dates(period: str, date_from: str = "", date_to: str = ""):
    """Return (from_ts, to_ts) for the given period string."""
    now = datetime.now(timezone.utc)
    today = now.date()

    td = __import__('datetime').timedelta
    if period == "today":
        start = today; end = today
    elif period == "yesterday":
        start = today - td(days=1); end = start
    elif period == "last_7_days":
        start = today - td(days=6); end = today
    elif period == "last_30_days":
        start = today - td(days=29); end = today
    elif period == "all_time":
        start = date(2000, 1, 1); end = today
    elif period == "this_week":
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
    country:   str = Query(""),
    city:      str = Query(""),
    ib_level:  int = Query(0),
    sales_agent_id: int = Query(0),
    plugit:    str = Query(""),   # ''|synced|no_plugit_update -> Plugit sync filter
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    p_from, p_to = period_dates(period, date_from, date_to)

    # Role-based visibility scope (drives the SQL filter below AND the cache key so one
    # user's scoped IB list is never served to another). scope_agent_ids -> None = full
    # access (all roles); else a per-user subtree that is deterministic for that user id.
    _scope = rbac.scope_agent_ids(db, current_user)
    scope_key = "all" if _scope is None else f"u{getattr(current_user, 'id', 0)}"

    cache_key = (f"ibs:list:{scope_key}:{period}:{date_from}:{date_to}:{country}:{city}:"
                 f"{ib_level}:{sales_agent_id}:{plugit}:{sort}:{search}:{page}:{page_size}")
    return cached(cache_key, 90, lambda: _build_ibs(
        db, _scope, p_from, p_to, page, page_size, sort, search,
        country, city, ib_level, sales_agent_id, plugit))


def _build_ibs(db, _scope, p_from, p_to, page, page_size, sort, search,
               country, city, ib_level, sales_agent_id, plugit=""):
    # Show ONE row per PERSON: an IB has an MT4 + an MT5 record sharing ext_ib_id; only the
    # primary (commission-bearing) row is listed, and its clients/volume/accounts are combined
    # across both below. Standalone IBs (no ext_ib_id) are primary too.
    where = "WHERE ib.is_primary IS NOT FALSE"
    params: dict = {"p_from": p_from, "p_to": p_to}
    if search:
        where += " AND (ib.name ILIKE :s OR ib.phone ILIKE :s OR ib.ib_code ILIKE :s OR ib.email ILIKE :s)"
        params["s"] = f"%{search}%"
    if country:
        where += " AND ib.country ILIKE :country"; params["country"] = f"%{country}%"
    if city:
        where += " AND ib.city ILIKE :city"; params["city"] = f"%{city}%"
    if ib_level:
        where += " AND ib.ib_level = :iblevel"; params["iblevel"] = ib_level
    if plugit in ("no_plugit_update", "synced", "null_level", "null", "plugit_only"):
        where += " AND COALESCE(ib.plugit_status,'') = :plugit"; params["plugit"] = plugit
    if sales_agent_id:
        # IBs whose OWN account (clients.login = ib.agent_id) is assigned to this agent
        where += (" AND ib.agent_id IN (SELECT login FROM clients "
                  "WHERE assigned_agent_id = :sa_id)")
        params["sa_id"] = sales_agent_id
    # Role-based visibility: an IB is "yours" if its clients are assigned to you/your team
    if _scope is not None:
        if _scope:
            where += (" AND ib.agent_id IN (SELECT DISTINCT agent FROM clients "
                      "WHERE assigned_agent_id = ANY(:rbac_agent_ids) AND COALESCE(agent,0)<>0)")
            params["rbac_agent_ids"] = _scope
        else:
            where += " AND FALSE"

    sort_col = "total_clients DESC NULLS LAST"
    if sort == "volume":    sort_col = "total_volume DESC NULLS LAST"
    elif sort == "commission": sort_col = "total_commission DESC NULLS LAST"
    elif sort == "unpaid":  sort_col = "unpaid_commission DESC NULLS LAST"
    elif sort == "payoff":  sort_col = "COALESCE(total_payoff,0) DESC"
    elif sort == "net":     sort_col = "(COALESCE(total_commission,0)-COALESCE(total_payoff,0)) DESC"
    elif sort == "name":    sort_col = "ib.name ASC"
    elif sort == "new":     sort_col = "ib.created_at DESC NULLS LAST"
    elif sort == "deposit": sort_col = "total_deposits DESC NULLS LAST"

    low_min, active_min = get_status_thresholds(db)
    params["p_from"], params["p_to"] = p_from, p_to

    total = db.execute(text(f"SELECT COUNT(*) FROM ibs ib {where}"), params).scalar() or 0

    # IB list rows come straight from the small `ibs` table (fast, ~1k rows). The
    # trading-clients status count is computed separately (below) ONLY for the agents
    # on THIS page — NOT via a global join over all ~4M deals, which would time out on
    # a cold cache for period=all_time and blank the whole list (the 504 -> empty bug).
    rows = db.execute(text(f"""
        SELECT
            ib.id, ib.agent_id, ib.ib_code, ib.name, ib.email, ib.phone,
            ib.country, ib.city, ib.ib_level,
            CASE WHEN ib.ext_ib_id IS NULL THEN ib.total_clients
                 ELSE (SELECT COALESCE(SUM(s.total_clients),0)::int FROM ibs s WHERE s.ext_ib_id = ib.ext_ib_id) END AS total_clients,
            ib.active_clients,
            CASE WHEN ib.ext_ib_id IS NULL THEN ib.total_volume
                 ELSE (SELECT COALESCE(SUM(s.total_volume),0) FROM ibs s WHERE s.ext_ib_id = ib.ext_ib_id) END AS total_volume,
            ib.total_commission, ib.unpaid_commission, ib.paid_commission,
            ib.balance, ib.group_name,
            (SELECT COUNT(*) FROM ibs sub WHERE sub.parent_ib_id = ib.id) AS sub_ib_count,
            ib.plugit_status, ib.markup_pips, ib.ext_ib_id, ib.ib_creation_date, ib.is_sub_ib,
            COALESCE(ib.total_payoff,0) AS total_payoff,
            CASE WHEN ib.ext_ib_id IS NULL THEN
                    (CASE WHEN starts_with(COALESCE(ib.group_name,''),'TNFX') THEN 'MT4' ELSE 'MT5' END) || ' #' || ib.agent_id
                 ELSE (SELECT string_agg(DISTINCT
                        (CASE WHEN starts_with(COALESCE(s.group_name,''),'TNFX') THEN 'MT4' ELSE 'MT5' END) || ' #' || s.agent_id, '  ·  ')
                        FROM ibs s WHERE s.ext_ib_id = ib.ext_ib_id AND s.agent_id IS NOT NULL) END AS accounts_str
        FROM ibs ib
        {where}
        ORDER BY {sort_col}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    # Cheap global KPIs (no deals scan) — always returned so the cards never blank.
    kpis = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE ib.is_primary IS NOT FALSE) AS total_ibs,
            COALESCE(SUM(ib.total_clients),0) AS total_clients,
            COALESCE(SUM(ib.total_volume),0) AS total_volume,
            COALESCE(SUM(ib.total_commission),0) AS total_commission,
            COALESCE(SUM(ib.unpaid_commission),0) AS total_unpaid,
            COALESCE(SUM(ib.total_payoff),0) AS total_payoff
        FROM ibs ib
    """)).fetchone()

    # NOTE: per-IB trading_clients (drives the status pill) AND the active/low/inactive
    # tier BREAKDOWN both need a heavy scan over ~4M deals. On this box the deals buffer
    # cache churns under constant bridge writes, so even the top-page agents (the biggest
    # IBs, sorted first) cost ~10s for all_time. So NEITHER is computed here — both are
    # served LAZILY by GET /ibs/status-breakdown (which takes the page's agents) so the
    # list renders instantly and trading_clients/status/tiles fill in a moment later.

    # sales agent assigned to each IB's OWN account (clients.login = ib.agent_id)
    _ib_logins = [r[1] for r in rows if r[1]]
    ib_sales_agent = {}
    if _ib_logins:
        ib_sales_agent = {x[0]: (x[1], x[2]) for x in db.execute(text("""
            SELECT c.login, u.full_name, u.id
            FROM clients c JOIN users u ON u.id = c.assigned_agent_id
            WHERE c.login = ANY(:ids)
        """), {"ids": _ib_logins}).fetchall()}

    return {
        "ibs": [{
            "id":                r[0],
            "agent_id":          r[1],
            "sales_agent":       (ib_sales_agent.get(r[1]) or ("", None))[0],
            "sales_agent_id":    (ib_sales_agent.get(r[1]) or ("", None))[1],
            "ib_code":           r[2] or "",
            "name":              r[3] or "",
            "email":             r[4] or "",
            # RULE: IBs are clients too — always treated as verified (email + phone + KYC).
            "email_verified":    True,
            "phone_verified":    True,
            "kyc":               "verified",
            "phone":             r[5] or "",
            "country":           r[6] or "",
            "city":              r[7] or "",
            "ib_level":          r[8] or 5,
            "tier":              TIER_NAMES.get(r[8] or 5, "Bronze"),
            "total_clients":     r[9] or 0,
            "active_clients":    r[10] or 0,
            "total_volume":      float(r[11] or 0),
            "total_commission":  float(r[12] or 0),
            "unpaid_commission": float(r[13] or 0),
            "paid_commission":   float(r[14] or 0),
            "balance":           float(r[15] or 0),
            "group_name":        r[16] or "",
            "sub_ib_count":      r[17] or 0,
            "plugit_status":     (len(r) > 18 and r[18]) or "",
            "markup_pips":       (len(r) > 19 and r[19]) or None,
            "ext_ib_id":         (len(r) > 20 and r[20]) or None,
            "ib_creation_date":  (r[21].isoformat() if len(r) > 21 and r[21] else None),
            "is_sub_ib":         bool(len(r) > 22 and r[22]),
            "total_payoff":      float((len(r) > 23 and r[23]) or 0),
            "net_commission":    float((r[12] or 0)) - float((len(r) > 23 and r[23]) or 0),
            "accounts_str":      (len(r) > 24 and r[24]) or "",
            "trading_clients":   None,   # loaded lazily via /ibs/status-breakdown
            "status":            None,   # ditto (null -> frontend shows a "…" pill)
        } for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "kpis": {
            "total_ibs":          kpis[0] or 0,
            "total_clients":      kpis[1] or 0,
            "total_volume":       float(kpis[2] or 0),
            "total_commission":   float(kpis[3] or 0),
            "total_unpaid":       float(kpis[4] or 0),
            "total_payoff":       float(kpis[5] or 0),
            # tier counts are loaded lazily via /ibs/status-breakdown (null = "loading")
            "active_ibs":         None,
            "low_ibs":            None,
            "inactive_ibs":       None,
            "super_inactive_ibs": None,
        },
        "thresholds": {"low_min": low_min, "active_min": active_min},
        "period": {"from": p_from, "to": p_to},
    }


@router.get("/status-breakdown")
async def get_ib_status_breakdown(
    period:    str = Query("all_time"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    agents:    str = Query(""),   # CSV of the current page's IB agent_ids -> per-row trading
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Per-IB trading_clients (for the passed `agents`) + active/low/inactive tier counts
    for the period. Split out of GET /ibs so the IB list renders instantly — both need a
    heavy scan over ~4M deals (~10s cold for all_time on this box, whose deals cache churns
    under constant bridge writes) and are loaded lazily by the frontend. Guarded by a
    statement timeout so it degrades to nulls instead of hanging the request."""
    p_from, p_to = period_dates(period, date_from, date_to)
    low_min, active_min = get_status_thresholds(db)
    out = {"active_ibs": None, "low_ibs": None, "inactive_ibs": None, "super_inactive_ibs": None,
           "low_min": low_min, "active_min": active_min, "trading": {}}

    # per-page trading_clients (drives each row's status pill) for just the listed agents
    agent_ids = [int(a) for a in agents.split(",") if a.strip().lstrip("-").isdigit()]
    if agent_ids:
        try:
            db.execute(text("SET statement_timeout = 25000"))
            for a, tc in db.execute(text("""
                SELECT c.agent, COUNT(DISTINCT d.login) AS tc
                FROM deals d JOIN clients c ON c.login = d.login
                WHERE c.agent = ANY(:agents) AND d.action IN (0,1) AND d.volume > 0
                  AND d.deal_date BETWEEN :p_from AND :p_to
                GROUP BY c.agent
            """), {"agents": agent_ids, "p_from": p_from, "p_to": p_to}).fetchall():
                out["trading"][str(a)] = tc
        except Exception:
            db.rollback()
        finally:
            db.execute(text("SET statement_timeout = 0"))

    try:
        db.execute(text("SET statement_timeout = 25000"))
        sb = db.execute(text("""
            WITH trading AS (
                SELECT c.agent AS agent, COUNT(DISTINCT d.login) AS tc
                FROM deals d JOIN clients c ON c.login = d.login
                WHERE COALESCE(c.agent,0) <> 0 AND d.action IN (0,1) AND d.volume > 0
                  AND d.deal_date BETWEEN :p_from AND :p_to
                GROUP BY c.agent
            )
            SELECT
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= :active_min) AS active_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= :low_min AND COALESCE(t.tc,0) < :active_min) AS low_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= 1 AND COALESCE(t.tc,0) < :low_min) AS inactive_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) = 0) AS super_inactive_ibs
            FROM ibs ib LEFT JOIN trading t ON t.agent = ib.agent_id
        """), {"p_from": p_from, "p_to": p_to, "low_min": low_min, "active_min": active_min}).fetchone()
        out.update(active_ibs=sb[0] or 0, low_ibs=sb[1] or 0,
                   inactive_ibs=sb[2] or 0, super_inactive_ibs=sb[3] or 0)
    except Exception:
        db.rollback()  # statement-timeout/error -> leave tiers null (frontend shows "—")
    finally:
        db.execute(text("SET statement_timeout = 0"))
    return out


@router.get("/search")
async def search_ibs(
    q: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Typeahead for the trades IB filter — match by IB name / email / code / login."""
    q = (q or "").strip()
    if len(q) < 1:
        return {"ibs": []}
    rows = db.execute(text("""
        SELECT id, ib_code, name, email, agent_id
        FROM ibs
        WHERE name ILIKE :q OR email ILIKE :q OR ib_code ILIKE :q OR CAST(agent_id AS TEXT) ILIKE :q
        ORDER BY total_clients DESC NULLS LAST
        LIMIT 20
    """), {"q": f"%{q}%"}).fetchall()
    return {"ibs": [{"id": r[0], "ib_code": r[1] or "", "name": r[2] or "",
                     "email": r[3] or "", "agent_id": r[4]} for r in rows]}


@router.get("/clients/search")
async def search_ib_clients(
    q: str = Query(""),
    ib_id: int = Query(0),   # 0 = search across all IBs' clients
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Typeahead for the trades client filter — match by client name / email / phone /
    login (account number). Optionally scoped to one IB's clients."""
    q = (q or "").strip()
    if len(q) < 1:
        return {"clients": []}
    where = "(c.name ILIKE :q OR c.email ILIKE :q OR c.phone ILIKE :q OR CAST(c.login AS TEXT) ILIKE :q)"
    params = {"q": f"%{q}%"}
    if ib_id:
        where = "c.agent = (SELECT agent_id FROM ibs WHERE id = :ib) AND " + where
        params["ib"] = ib_id
    rows = db.execute(text(f"""
        SELECT c.login, c.name, c.email, c.phone
        FROM clients c
        WHERE {where}
        ORDER BY c.balance DESC NULLS LAST
        LIMIT 20
    """), params).fetchall()
    return {"clients": [{"login": r[0], "name": r[1] or "", "email": r[2] or "",
                         "phone": r[3] or ""} for r in rows]}


@router.get("/plugit-only")
async def plugit_only(
    search: str = Query(""), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user),
):
    """IBs that exist in the Plugit export but NOT in the CRM (new-tab list)."""
    if not db.execute(text("SELECT to_regclass('public.ib_plugit')")).scalar():
        return {"rows": [], "total": 0}
    w = "WHERE in_crm = FALSE"
    p: dict = {}
    if search:
        w += " AND (name ILIKE :s OR email ILIKE :s OR code ILIKE :s)"; p["s"] = f"%{search}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM ib_plugit {w}"), p).scalar() or 0
    rows = db.execute(text(f"""
        SELECT code, email, name, pips, level FROM ib_plugit {w}
        ORDER BY level DESC NULLS LAST, name LIMIT :lim OFFSET :off
    """), {**p, "lim": page_size, "off": (page-1)*page_size}).fetchall()
    return {"total": total, "page": page, "page_size": page_size,
            "rows": [{"code": r[0], "email": r[1] or "", "name": r[2] or "",
                      "pips": r[3], "level": r[4], "tier": TIER_NAMES.get(r[4] or 0, "")} for r in rows]}


@router.get("/operations")
async def all_ib_operations(
    request_type: str = Query(""),   # ''|Wallet Withdrawal|External Wallet Transfer|Internal Wallet Transfer
    status: str = Query(""),         # ''|Approved|Declined|Pending
    search: str = Query(""),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user),
):
    """All IB payouts (the Withdrawals page): withdrawals + internal/external transfers.
    Every row here originates from an IB, so the frontend colours them as IB withdrawals."""
    if not db.execute(text("SELECT to_regclass('public.ib_operations')")).scalar():
        return {"rows": [], "total": 0, "totals": {}}
    w = "WHERE 1=1"; p: dict = {}
    if request_type: w += " AND o.request_type = :rt"; p["rt"] = request_type
    if status:       w += " AND o.status = :st"; p["st"] = status
    if search:       w += " AND (o.name ILIKE :s OR o.email ILIKE :s OR o.account ILIKE :s)"; p["s"] = f"%{search}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM ib_operations o {w}"), p).scalar() or 0
    tot = db.execute(text(f"""SELECT
        COALESCE(SUM(amount) FILTER (WHERE status='Approved'),0),
        COUNT(*) FILTER (WHERE request_type='Internal Wallet Transfer' AND status='Pending'),
        COUNT(*) FILTER (WHERE status='Pending')
        FROM ib_operations o {w}"""), p).fetchone()
    rows = db.execute(text(f"""
        SELECT o.id, o.ib_id, o.ext_ib_id, o.name, o.email, o.account, o.request_type, o.amount,
               o.payment_type, o.status, o.to_account, o.op_date, o.action_date, o.note
        FROM ib_operations o {w}
        ORDER BY o.op_date DESC NULLS LAST LIMIT :lim OFFSET :off
    """), {**p, "lim": page_size, "off": (page-1)*page_size}).fetchall()
    return {
        "total": total, "page": page, "page_size": page_size,
        "totals": {"approved_amount": float(tot[0] or 0), "pending_transfers": tot[1] or 0, "pending": tot[2] or 0},
        "rows": [{
            "id": r[0], "ib_id": r[1], "ext_ib_id": r[2], "name": r[3] or "", "email": r[4] or "",
            "account": r[5] or "", "request_type": r[6] or "", "amount": float(r[7] or 0),
            "payment_type": r[8] or "", "status": r[9] or "", "to_account": r[10] or "",
            "op_date": r[11].isoformat() if r[11] else None,
            "action_date": r[12].isoformat() if r[12] else None, "note": r[13] or "",
            "is_ib": True,
        } for r in rows],
    }


@router.get("/settings/status-thresholds")
async def get_ib_status_thresholds(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    low_min, active_min = get_status_thresholds(db)
    return {"low_min": low_min, "active_min": active_min}


@router.post("/settings/status-thresholds")
async def set_ib_status_thresholds(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_status_thresholds(db)
    low = max(1, int(data.get("low_min", 3)))
    act = max(low, int(data.get("active_min", 5)))
    db.execute(text("UPDATE ib_status_config SET low_min=:l, active_min=:a WHERE id=1"), {"l": low, "a": act})
    db.commit()
    return {"ok": True, "low_min": low, "active_min": act}


@router.post("/{ib_id}/action")
async def ib_action(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Action taken after a call (like the client page) + management actions."""
    db.execute(text("""
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS last_outcome    VARCHAR;
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS last_contact_at TIMESTAMPTZ;
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS follow_up_at     TIMESTAMPTZ;
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS target           DOUBLE PRECISION;
    """))
    db.commit()
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    act = data.get("action", "")

    if act in ("connected_done", "no_answer", "call_later", "not_interested"):
        follow = None
        if act == "no_answer":      follow = "NOW() + interval '2 hours'"
        elif act == "connected_done": follow = "NOW() + interval '14 days'"
        elif act == "call_later":
            days = int(data.get("days", 0)); hours = int(data.get("hours", 0))
            follow = f"NOW() + interval '{days} days' + interval '{hours} hours'"
        fexpr = follow or "NULL"
        db.execute(text(f"UPDATE ibs SET last_outcome=:o, last_contact_at=NOW(), follow_up_at={fexpr} WHERE id=:id"),
                   {"o": act, "id": ib_id})
        db.commit()
        return {"ok": True, "outcome": act}

    # only Zainab may change an IB's LEVEL (everyone can SEE promote/demote in the menu)
    if act in ("promote", "demote") and not can_change_ib_level(current_user):
        raise HTTPException(status_code=403, detail="Only Zainab can change an IB level.")

    if act == "promote":
        new = min(10, (ib.ib_level or 5) + 1)
        db.execute(text("UPDATE ibs SET ib_level=:l WHERE id=:id"), {"l": new, "id": ib_id})
        db.commit()
        return {"ok": True, "ib_level": new, "tier": TIER_NAMES.get(new, "Bronze")}
    if act == "demote":
        new = max(5, (ib.ib_level or 5) - 1)
        db.execute(text("UPDATE ibs SET ib_level=:l WHERE id=:id"), {"l": new, "id": ib_id})
        db.commit()
        return {"ok": True, "ib_level": new, "tier": TIER_NAMES.get(new, "Bronze")}
    if act == "set_target":
        db.execute(text("UPDATE ibs SET target=:t WHERE id=:id"), {"t": float(data.get("target", 0)), "id": ib_id})
        db.commit()
        return {"ok": True, "target": float(data.get("target", 0))}
    return {"ok": False, "error": "unknown action"}


@router.get("/{ib_id}")
async def get_ib(
    ib_id: int,
    period:    str = Query("this_month"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    country:   str = Query(""),
    city:      str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")

    p_from, p_to = period_dates(period, date_from, date_to)
    # index-friendly end bound: end-day-INCLUSIVE -> raw col < (to + 1 day)
    p_to_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    level = ib.ib_level or 5
    agent = ib.agent_id
    base = {"agent": agent, "p_from": p_from, "p_to": p_to, "p_to_next": p_to_next, "level": level}

    # period trading: volume (lots) + commission (lots * points), from real deals
    # NEW MODEL: commission = lots * comm_per_lot from the per-(level,symbol) rate table
    pk = db.execute(text("""
        SELECT COALESCE(SUM(d.volume/10000.0),0) AS lots,
               COALESCE(SUM((d.volume/10000.0) * r.comm_per_lot),0) AS commission,
               COUNT(DISTINCT d.login) AS active_traders
        FROM deals d
        JOIN clients c ON c.login = d.login
        JOIN commission_rates r ON r.ib_level = :level AND r.symbol = d.symbol
        WHERE c.agent = :agent AND d.entry = 1 AND d.action IN (0,1) AND d.volume > 0
          AND d.deal_date >= :p_from AND d.deal_date < :p_to_next
    """), base).fetchone()

    # period money: deposits + withdrawals, from real transactions
    pm = db.execute(text("""
        SELECT COALESCE(SUM(CASE WHEN t.tx_type='deposit'    THEN t.amount ELSE 0 END),0) AS dep,
               COALESCE(SUM(CASE WHEN t.tx_type='withdrawal' THEN t.amount ELSE 0 END),0) AS wd,
               COUNT(DISTINCT t.login) AS active_dep
        FROM transactions t JOIN clients c ON c.login = t.login
        WHERE c.agent = :agent
          AND t.tx_date >= :p_from AND t.tx_date < :p_to_next
    """), base).fetchone()

    new_clients = db.execute(text("""
        SELECT COUNT(*) FROM clients c WHERE c.agent = :agent
          AND c.reg_date >= :p_from AND c.reg_date < :p_to_next
    """), base).scalar() or 0
    leads_count    = db.execute(text("SELECT COUNT(*) FROM clients WHERE agent = :agent"), base).scalar() or 0
    # RULE: every client is treated as verified, so verified count == client count.
    verified_leads = db.execute(text("SELECT COUNT(*) FROM clients WHERE agent = :agent"), base).scalar() or 0
    ftd_count      = db.execute(text("""SELECT COUNT(DISTINCT c.login) FROM clients c
        JOIN transactions t ON t.login=c.login AND t.tx_type='deposit' WHERE c.agent = :agent"""), base).scalar() or 0
    sub_ibs = db.query(models.IB).filter(models.IB.parent_ib_id == ib_id).all()

    # clients list with REAL deposits/withdrawals (transactions), country/city filter, campaign
    # exclude the IB's OWN account from its own client list (login = agent) — an IB is not its own client
    cwhere, cparams = "c.agent = :agent AND c.login <> c.agent", {"agent": agent, "level": level}
    if country:
        cwhere += " AND c.country ILIKE :country"; cparams["country"] = f"%{country}%"
    if city:
        cwhere += " AND c.city ILIKE :city"; cparams["city"] = f"%{city}%"
    client_rows = db.execute(text(f"""
        SELECT c.login, c.name, c.phone, c.country, c.city, c.balance, c.kyc_status,
               COALESCE(NULLIF(c.reg_date,''), c.created_at::text, td.first_dep::text) AS reg_date, c.utm_campaign,
               COALESCE(td.dep,0) AS dep, COALESCE(td.wd,0) AS wd,
               COALESCE(tv.lots,0) AS volume, tv.first_trade,
               dm.method AS top_method,
               GREATEST(COALESCE(net.cid_cnt,0),0) AS cid_cnt,
               GREATEST(COALESCE(net.ip_cnt,0),0)  AS ip_cnt,
               c.assigned_agent_id AS sales_agent_id,
               COALESCE(acct.account_number, c.login) AS account_number,
               COALESCE(tv.commission,0) AS commission,
               c.email, td.first_dep,
               c.customer_no, c.email_verified, c.phone_verified
        FROM clients c
        LEFT JOIN (
            SELECT login,
                   SUM(CASE WHEN tx_type='deposit'    THEN amount ELSE 0 END) AS dep,
                   SUM(CASE WHEN tx_type='withdrawal' THEN amount ELSE 0 END) AS wd,
                   MIN(CASE WHEN tx_type='deposit' THEN tx_date END) AS first_dep
            FROM transactions GROUP BY login
        ) td ON td.login = c.login
        LEFT JOIN LATERAL (
            -- all-time lots + first trade + commission this client earned the IB
            -- (commission model: eligible opening trades, rate per IB level & symbol)
            SELECT SUM(CASE WHEN {FX_OR_GOLD} THEN d.volume/10000.0 ELSE 0 END) AS lots,
                   MIN(NULLIF(d.deal_date,'')) AS first_trade,
                   COALESCE(SUM(CASE WHEN d.entry = 1 THEN (d.volume/10000.0) * r.comm_per_lot ELSE 0 END),0) AS commission
            FROM deals d
            LEFT JOIN commission_rates r ON r.ib_level = :level AND r.symbol = d.symbol
            WHERE d.login = c.login AND d.action IN (0,1) AND d.volume > 0
        ) tv ON TRUE
        LEFT JOIN LATERAL (
            SELECT t.method FROM transactions t
            WHERE t.login = c.login AND t.tx_type='deposit' AND COALESCE(t.method,'') <> ''
            GROUP BY t.method ORDER BY COUNT(*) DESC LIMIT 1
        ) dm ON TRUE
        LEFT JOIN LATERAL (
            SELECT
              (SELECT COUNT(DISTINCT b.login) FROM account_identifiers b WHERE b.identifier_type='cid'
                 AND b.identifier_value IN (SELECT identifier_value FROM account_identifiers
                                            WHERE login=c.login AND identifier_type='cid')) - 1 AS cid_cnt,
              (SELECT COUNT(DISTINCT b.login) FROM account_identifiers b WHERE b.identifier_type='ip'
                 AND b.identifier_value IN (SELECT identifier_value FROM account_identifiers
                                            WHERE login=c.login AND identifier_type='ip')) - 1 AS ip_cnt
        ) net ON TRUE
        LEFT JOIN LATERAL (
            -- #101 (Zainab): the trading-account number = the person's primary login,
            -- defined exactly like the Clients list (#73): the HIGHEST POSITIVE-balance
            -- login among the same phone+platform siblings, else the highest-balance one.
            -- NOTE: written WITHOUT a CASE in the WHERE so the ix_clients_phone_platform index
            -- is actually used (the CASE form seq-scanned clients per row -> ~10s/IB). A client
            -- with null/empty/'0' phone matches no sibling here, so the outer
            -- COALESCE(acct.account_number, c.login) falls back to its own login (same result).
            SELECT COALESCE(
                (array_agg(s.login ORDER BY s.balance DESC NULLS LAST)
                    FILTER (WHERE s.balance > 0))[1],
                (array_agg(s.login ORDER BY s.balance DESC NULLS LAST))[1]
            ) AS account_number
            FROM clients s
            WHERE c.phone IS NOT NULL AND c.phone <> '' AND c.phone <> '0'
              AND s.phone = c.phone AND COALESCE(s.platform,'MT5') = COALESCE(c.platform,'MT5')
        ) acct ON TRUE
        WHERE {cwhere}
        ORDER BY COALESCE(td.dep,0) DESC
        LIMIT 300
    """), cparams).fetchall()

    # per-client commission breakdown for the period (from deals)
    comm_rows = db.execute(text("""
        SELECT c.login, c.name,
               SUM(d.volume/10000.0) AS lots,
               SUM((d.volume/10000.0) * r.comm_per_lot) AS comm
        FROM deals d
        JOIN clients c ON c.login = d.login
        JOIN commission_rates r ON r.ib_level = :level AND r.symbol = d.symbol
        WHERE c.agent = :agent AND d.entry = 1 AND d.action IN (0,1) AND d.volume > 0
          AND d.deal_date >= :p_from AND d.deal_date < :p_to_next
        GROUP BY c.login, c.name ORDER BY comm DESC LIMIT 200
    """), base).fetchall()

    # abuse flags for this IB's clients (from the abuse engine's per-account table)
    ib_flags = {}
    _cl = [r[0] for r in client_rows if r and r[0]]
    if _cl and db.execute(text("SELECT to_regclass('public.abuse_account_flags')")).scalar():
        ib_flags = {a[0]: {"type": a[1], "severity": a[2], "hot": a[3]} for a in db.execute(text(
            "SELECT login, abuse_type, severity, hot FROM abuse_account_flags WHERE login = ANY(:l)"),
            {"l": _cl}).fetchall()}

    # sales-agent names (clients.assigned_agent_id -> users.full_name) for the Sales agent column
    _sa_ids = list({r[16] for r in client_rows if len(r) > 16 and r[16]})
    sales_agent_map = {}
    if _sa_ids:
        sales_agent_map = {u[0]: u[1] for u in db.execute(text(
            "SELECT id, full_name FROM users WHERE id = ANY(:ids)"), {"ids": _sa_ids}).fetchall()}
    _ABUSE_LBL = {'margin_partner': 'Margin-Out', 'bonus_ring': 'Bonus Ring',
                  'bonus_cashout': 'Bonus Cash-Out', 'chip_dump': 'Chip Dump',
                  'swap_carry': 'Swap Carry', 'toxic_arb': 'Toxic'}

    # The IB's real account manager = the sales agent assigned to the IB's OWN client
    # account (clients.login = ib.agent_id). Falls back to that agent's manager if none.
    manager = None
    mrow = db.execute(text("""
        SELECT u.full_name, u.title, u.role, u.email, u.phone, u.avatar_url, u.extension, u.department
        FROM clients c JOIN users u ON u.id = c.assigned_agent_id
        WHERE c.login = :agent LIMIT 1
    """), {"agent": agent}).fetchone()
    if mrow:
        _ROLE_LBL = {"sales_agent": "Sales Agent", "sales_manager": "Sales Manager",
                     "retention_agent": "Retention Agent", "admin": "Administrator",
                     "sales_director": "Sales Director"}
        manager = {
            "name": mrow[0] or "", "title": mrow[1] or _ROLE_LBL.get(mrow[2] or "", "Account Manager"),
            "role": mrow[2] or "", "email": mrow[3] or "", "phone": mrow[4] or "",
            "avatar_url": mrow[5] or "", "extension": mrow[6] or "", "department": mrow[7] or "",
        }

    # Both MT accounts of this IB (person) — fetch the ACTUAL MT accounts from clients that sit in
    # an IB group: MT5 = IB\IB-N, MT4 = TNFX-IB-N. Linked by email / customer_no / this login, so we
    # surface the MT4 account even when it isn't a separate ibs row.
    acct_rows = db.execute(text("""
        SELECT DISTINCT c.login, COALESCE(c.platform,'MT5') AS platform, c.group_name
        FROM clients c
        WHERE c.group_name ~ '^(TNFX-IB-|IB.IB-)'
          AND (
            (COALESCE(:em,'') <> '' AND LOWER(c.email) = LOWER(:em))
            OR (c.customer_no IS NOT NULL AND c.customer_no = (SELECT customer_no FROM clients WHERE login = :agent LIMIT 1))
            OR c.login = :agent
          )
    """), {"em": ib.email, "agent": agent}).fetchall()
    accounts = sorted(
        [{"account": a[0], "platform": a[1], "group": a[2],
          "ib_level": (int(a[2].split("-")[-1]) if a[2] and a[2].split("-")[-1].isdigit() else None)}
         for a in acct_rows],
        key=lambda x: (x["platform"] != "MT4", x["account"]))
    if not accounts:
        accounts = [{"account": agent, "platform": "MT5", "group": ib.group_name or "", "ib_level": level}]
    # master IB (parent)
    master = None
    if getattr(ib, "parent_ib_id", None):
        m = db.execute(text("SELECT id, agent_id, name, ext_ib_id FROM ibs WHERE id=:p"), {"p": ib.parent_ib_id}).fetchone()
        if m: master = {"id": m[0], "agent_id": m[1], "name": m[2] or "", "ext_ib_id": m[3]}

    return {
        "id":                ib.id,
        "ext_ib_id":         getattr(ib, "ext_ib_id", None),
        "ib_creation_date":  (ib.ib_creation_date.isoformat() if getattr(ib, "ib_creation_date", None) else None),
        "is_sub_ib":         bool(getattr(ib, "is_sub_ib", False)),
        "master_ib":         master,
        "accounts":          accounts,
        "manager":           manager,
        "agent_id":          agent,
        "ib_code":           ib.ib_code or "",
        "name":              ib.name or "",
        "email":             ib.email or "",
        # RULE: IBs are clients too — always treated as verified (email + phone + KYC).
        "email_verified":    True,
        "phone_verified":    True,
        "kyc":               "verified",
        "phone":             ib.phone or "",
        "country":           ib.country or "",
        "city":              ib.city or "",
        "ib_level":          level,
        "tier":              TIER_NAMES.get(level, "Bronze"),
        "group_name":        ib.group_name or "",
        "balance":           float(ib.balance or 0),
        "total_clients":     ib.total_clients or 0,
        "active_clients":    ib.active_clients or 0,
        "total_volume":      float(ib.total_volume or 0),
        "total_commission":  float(ib.total_commission or 0),
        "unpaid_commission": float(ib.unpaid_commission or 0),
        "paid_commission":   float(ib.paid_commission or 0),
        "total_payoff":      float(getattr(ib, "total_payoff", 0) or 0),
        "net_commission":    float(ib.total_commission or 0) - float(getattr(ib, "total_payoff", 0) or 0),
        "commission_excel":    float(getattr(ib, "commission_excel", 0) or 0),
        "commission_computed": float(getattr(ib, "commission_computed", 0) or 0),
        "commission_source":   getattr(ib, "commission_source", None) or "",
        "period": {
            "from":           p_from,
            "to":             p_to,
            "commission":     float(pk[1] or 0),
            "volume":         float(pk[0] or 0),
            "deposits":       float(pm[0] or 0),
            "withdrawals":    float(pm[1] or 0),
            "new_clients":    new_clients,
            "active_clients": max(pk[2] or 0, pm[2] or 0),
        },
        "funnel": {
            "clicks":         0,
            "leads":          leads_count,
            "verified_leads": verified_leads,
            "ftd":            ftd_count,
            "sub_ibs":        len(sub_ibs),
        },
        "clients": [{
            "login":       r[0],
            "name":        r[1] or "",
            "account_number": r[17] if len(r) > 17 and r[17] else r[0],
            "phone":       r[2] or "",
            "country":     r[3] or "",
            "city":        r[4] or "",
            "balance":     float(r[5] or 0),
            "kyc":         "verified",   # RULE: clients are always approved KYC
            "reg_date":    str(r[7])[:10] if r[7] else "",
            "campaign":    r[8] or "",
            "total_dep":   float(r[9] or 0),
            "total_with":  float(r[10] or 0),
            "volume":      float(r[11] or 0),
            "first_trade": str(r[12])[:10] if r[12] else "",
            "deposit_method": r[13] or "",
            "commission":  float(r[18] or 0),   # commission this client earned the IB (all-time)
            "email":       (len(r) > 19 and r[19]) or "",
            "first_deposit": str(r[20])[:10] if (len(r) > 20 and r[20]) else "",
            "customer_no": (len(r) > 21 and r[21]) or "",
            "email_verified": True,   # RULE: clients are always verified
            "phone_verified": True,
            "network_score": min(10, round((min(100, (r[14] or 0)*50 + (r[15] or 0)*35))/10)),
            "abuse_flag":  _ABUSE_LBL.get((ib_flags.get(r[0]) or {}).get("type"), "") if ib_flags.get(r[0]) else "",
            "abuse_severity": (ib_flags.get(r[0]) or {}).get("severity", ""),
            "abuse_hot":   bool((ib_flags.get(r[0]) or {}).get("hot")),
            "sales_agent": sales_agent_map.get(r[16] if len(r) > 16 else None, ""),
        } for r in client_rows],
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
            "client_login":   r[0],
            "client_name":    r[1] or f"#{r[0]}",
            "lots":           float(r[2] or 0),
            "pts_per_lot":    level,
            "commission_usd": float(r[3] or 0),
            "status":         "unpaid",
        } for r in comm_rows],
        "referral_links": [],
    }


@router.get("/{ib_id}/operations")
def ib_operations(ib_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """This IB's payout operations (withdrawals + internal/external transfers) for the IB profile."""
    if not db.execute(text("SELECT to_regclass('public.ib_operations')")).scalar():
        return {"operations": [], "summary": {}}
    rows = db.execute(text("""
        SELECT request_type, amount, payment_type, status, to_account, op_date, action_date, note, account
        FROM ib_operations WHERE ib_id = :id ORDER BY op_date DESC NULLS LAST LIMIT 500
    """), {"id": ib_id}).fetchall()
    summ = db.execute(text("""
        SELECT COALESCE(SUM(amount) FILTER (WHERE status='Approved'),0) AS paid_out,
               COALESCE(SUM(amount) FILTER (WHERE status='Approved' AND request_type='Wallet Withdrawal'),0) AS withdrawn,
               COALESCE(SUM(amount) FILTER (WHERE status='Approved' AND request_type LIKE '%Transfer'),0) AS transferred,
               COUNT(*) FILTER (WHERE status='Pending') AS pending
        FROM ib_operations WHERE ib_id = :id
    """), {"id": ib_id}).fetchone()
    return {
        "summary": {"paid_out": float(summ[0] or 0), "withdrawn": float(summ[1] or 0),
                    "transferred": float(summ[2] or 0), "pending": summ[3] or 0},
        "operations": [{
            "request_type": r[0] or "", "amount": float(r[1] or 0), "payment_type": r[2] or "",
            "status": r[3] or "", "to_account": r[4] or "", "account": r[8] or "",
            "op_date": r[5].isoformat() if r[5] else None,
            "action_date": r[6].isoformat() if r[6] else None, "note": r[7] or "",
        } for r in rows],
    }


@router.post("/{ib_id}/operations")
def create_ib_operation(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """IB requests a payout from the portal: withdrawal or internal transfer (-> his trading acct).
    Creates a Pending row that shows up on the admin Withdrawals page for approval."""
    db.execute(text("""CREATE TABLE IF NOT EXISTS ib_operations(id SERIAL PRIMARY KEY, ext_ib_id INTEGER,
        ib_id INTEGER, account VARCHAR, name VARCHAR, email VARCHAR, request_type VARCHAR, amount DOUBLE PRECISION,
        converted_amount DOUBLE PRECISION, payment_type VARCHAR, status VARCHAR, to_account VARCHAR,
        referral_id VARCHAR, comment TEXT, op_date TIMESTAMPTZ, action_date TIMESTAMPTZ, order_id VARCHAR, note TEXT)"""))
    ib = db.execute(text("SELECT ext_ib_id, name, email FROM ibs WHERE id=:id"), {"id": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    kind = (data.get("kind") or "").lower()
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    rtype = "Internal Wallet Transfer" if kind == "transfer" else "Wallet Withdrawal"
    db.execute(text("""INSERT INTO ib_operations(ext_ib_id, ib_id, name, email, request_type, amount, converted_amount,
        payment_type, status, to_account, comment, op_date, note)
        VALUES(:ext,:id,:nm,:em,:rt,:amt,:amt,:pm,'Pending',:to,:cm,NOW(),:nt)"""),
        {"ext": ib[0], "id": ib_id, "nm": ib[1], "em": ib[2], "rt": rtype, "amt": amount,
         "pm": (data.get("payment_type") or ("Transfer" if kind == "transfer" else "USDt")),
         "to": (data.get("to_account") or ""), "cm": data.get("comment") or "",
         "nt": "requested from portal"})
    db.commit()
    return {"ok": True, "request_type": rtype, "amount": amount, "status": "Pending"}


@router.get("/{ib_id}/promotions")
def ib_promotions(ib_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """This IB's level-promotion history (detected from the broker Commission Report:
    a per-lot commission-rate step-up on gold/majors == a level promotion on that date)."""
    if not db.execute(text("SELECT to_regclass('public.ib_promotions')")).scalar():
        return {"promotions": []}
    rows = db.execute(text("""
        SELECT promo_date, from_level, to_level, note, source, created_at
        FROM ib_promotions WHERE ib_id = :id ORDER BY promo_date ASC
    """), {"id": ib_id}).fetchall()
    return {"promotions": [{
        "date": r[0].isoformat() if r[0] else None,
        "from_level": r[1], "to_level": r[2], "note": r[3] or "",
        "source": r[4] or "", "detected_at": r[5].isoformat() if r[5] else None,
    } for r in rows]}


@router.get("/{ib_id}/trades")
def ib_trades_list(
    ib_id: int,
    client_login: int = None, country: str = None, city: str = None,
    platform: str = None, account_type: str = None, campaign: str = None,
    f_ib_id: int = None,             # narrow the all-IBs view to a single selected IB
    period: str = "this_month", date_from: str = None, date_to: str = None,
    view: str = "eligible",          # eligible | short | credit | all
    group_by: str = None,            # day | week | month | year -> aggregated buckets
    page: int = 1, page_size: int = 100,
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user),
):
    """Per-trade list for an IB's clients (the IB 'Trades' / 'Credit Trades' tab).
    Filterable by client / country / city / platform / account-type / period; the `view`
    splits eligible (paid), short (<5min, unpaid) and credit (bonus, unpaid) trades."""
    p_from, p_to = period_dates(period, date_from, date_to)
    # index-friendly end bound: end-day-INCLUSIVE -> raw col < (to + 1 day)
    p_to_next = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    where = ["t.close_time >= :pf AND t.close_time < :ptn"]
    params = {"pf": p_from, "pt": p_to, "ptn": p_to_next}
    if ib_id and ib_id > 0:                # ib_id <= 0  ->  ALL IBs (admin-wide view)
        where.insert(0, "t.ib_id = :ib"); params["ib"] = ib_id
    elif f_ib_id:                          # all-IBs view narrowed to one selected IB
        where.insert(0, "t.ib_id = :fib"); params["fib"] = f_ib_id
    if client_login: where.append("t.login = :cl"); params["cl"] = client_login
    if country:      where.append("t.country = :co"); params["co"] = country
    if city:         where.append("t.city = :ci"); params["ci"] = city
    if platform:     where.append("t.platform = :pl"); params["pl"] = platform
    if account_type: where.append("t.account_type = :at"); params["at"] = account_type
    if campaign:     where.append("EXISTS (SELECT 1 FROM clients c WHERE c.login = t.login AND c.utm_campaign ILIKE :camp)"); params["camp"] = f"%{campaign}%"
    if view == "eligible":  where.append("t.eligible = TRUE")
    elif view == "short":   where.append("t.eligible = FALSE AND t.reason LIKE 'short%'")
    elif view == "credit":  where.append("t.reason = 'credit'")
    w = " AND ".join(where)

    # Display granularity: aggregate into time buckets instead of per-trade rows.
    groups = None
    _UNIT = {"day": "day", "week": "week", "month": "month", "year": "year"}.get((group_by or "").lower())
    if _UNIT:
        grows = db.execute(text(f"""
            SELECT date_trunc('{_UNIT}', t.close_time::timestamp) AS bucket,
                   COUNT(*) AS trades, COALESCE(SUM(t.lots),0) AS lots,
                   COALESCE(SUM(t.commission),0) AS commission, COALESCE(SUM(t.profit),0) AS profit
            FROM ib_trades t WHERE {w}
            GROUP BY 1 ORDER BY 1 DESC LIMIT 500
        """), params).fetchall()
        groups = [{"bucket": str(g[0])[:10], "trades": g[1], "lots": float(g[2] or 0),
                   "commission": float(g[3] or 0), "profit": float(g[4] or 0)} for g in grows]

    tot = db.execute(text(f"""SELECT COUNT(*), COALESCE(SUM(lots),0), COALESCE(SUM(commission),0),
                              COALESCE(SUM(profit),0), COALESCE(SUM(lots*comm_per_lot),0)
                              FROM ib_trades t WHERE {w}"""), params).fetchone()
    rows = db.execute(text(f"""
        SELECT t.login, t.client_name, t.country, t.city, t.platform, t.account_type, t.symbol, t.direction,
               t.open_time, t.close_time, t.hold_sec, t.lots, t.open_price, t.close_price, t.profit, t.commission, t.eligible, t.reason,
               t.deal_id, ib.ib_code, ib.name AS ib_name
        FROM ib_trades t
        LEFT JOIN ibs ib ON ib.id = t.ib_id
        WHERE {w}
        ORDER BY t.close_time DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """), {**params, "lim": page_size, "off": (page - 1) * page_size}).fetchall()
    ibf = "ib_id=:ib AND" if (ib_id and ib_id > 0) else ""
    opts = db.execute(text(f"""SELECT
        ARRAY(SELECT DISTINCT country FROM ib_trades WHERE {ibf} COALESCE(country,'')<>'' ORDER BY 1),
        ARRAY(SELECT DISTINCT city FROM ib_trades WHERE {ibf} COALESCE(city,'')<>'' ORDER BY 1),
        ARRAY(SELECT DISTINCT account_type FROM ib_trades {('WHERE ib_id=:ib') if (ib_id and ib_id>0) else ''} ORDER BY 1),
        ARRAY(SELECT DISTINCT platform FROM ib_trades {('WHERE ib_id=:ib') if (ib_id and ib_id>0) else ''} ORDER BY 1)
    """), ({"ib": ib_id} if (ib_id and ib_id > 0) else {})).fetchone()
    # campaign options (only for a specific IB — else far too many)
    camp_opts = []
    if ib_id and ib_id > 0:
        camp_opts = [c[0] for c in db.execute(text("""
            SELECT DISTINCT utm_campaign FROM clients
            WHERE agent = (SELECT agent_id FROM ibs WHERE id = :ib) AND COALESCE(utm_campaign,'') <> ''
            ORDER BY 1 LIMIT 100
        """), {"ib": ib_id}).fetchall()]
    return {
        "totals": {"trades": tot[0], "lots": float(tot[1] or 0), "commission": float(tot[2] or 0),
                   "profit": float(tot[3] or 0), "potential": float(tot[4] or 0)},
        "filters": {"countries": list(opts[0] or []), "cities": list(opts[1] or []),
                    "account_types": list(opts[2] or []), "platforms": list(opts[3] or []),
                    "campaigns": camp_opts},
        "groups": groups,
        "page": page, "page_size": page_size,
        "trades": [{
            "deal_id": r[18],
            "ib_code": r[19] or "", "ib_name": r[20] or "",
            "login": r[0], "client": r[1], "country": r[2], "city": r[3], "platform": r[4],
            "account_type": r[5], "symbol": r[6], "direction": r[7],
            "open_time": str(r[8]) if r[8] else None, "close_time": str(r[9]) if r[9] else None,
            "hold_min": round(r[10] / 60.0, 1) if r[10] is not None else None,
            "lots": float(r[11] or 0), "open_price": r[12], "close_price": r[13],
            "profit": float(r[14] or 0), "commission": float(r[15] or 0),
            "eligible": r[16], "reason": r[17],
        } for r in rows],
    }


# ─── Challenges (career path + weekly) ──────────────────────────────────────────
@router.get("/{ib_id}/challenges")
def get_challenges(ib_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return ib_challenges.list_all(db, ib_id)


@router.post("/{ib_id}/challenges/accept")
def accept_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        return ib_challenges.accept(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ib_id}/challenges/claim")
def claim_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        return ib_challenges.claim(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ib_id}/challenges/rechallenge")
def rechallenge_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        return ib_challenges.rechallenge(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ib_id}/challenges/claim-weekly")
def claim_weekly_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        return ib_challenges.claim_weekly(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Campaigns (create + referral links) ────────────────────────────────────────
def _ensure_campaign_table(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_campaigns (
            id         SERIAL PRIMARY KEY,
            ib_id      INTEGER NOT NULL,
            name       VARCHAR NOT NULL,
            platform   VARCHAR,
            website    VARCHAR,
            ref_code   VARCHAR UNIQUE NOT NULL,
            clicks     INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """))
    db.commit()


def _ref_link(ref_code: str) -> str:
    return f"https://my1.tnfx.co/register?ref={ref_code}"


@router.get("/{ib_id}/referral-links")
def ib_referral_links(ib_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """The IB's EXISTING (Plugit) referral links — imported so they keep working."""
    if not db.execute(text("SELECT to_regclass('public.ib_referral_links')")).scalar():
        return {"links": []}
    rows = db.execute(text("""
        SELECT banner, referrer_id, campaign_code, custom_link, clicks
        FROM ib_referral_links WHERE ib_id = :ib ORDER BY id
    """), {"ib": ib_id}).fetchall()
    return {"links": [{"banner": r[0] or "", "referrer_id": r[1] or "", "campaign_code": r[2] or "",
                       "custom_link": r[3] or "", "clicks": r[4] or 0, "source": "plugit"} for r in rows]}


@router.get("/{ib_id}/campaigns")
def list_campaigns(ib_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _ensure_campaign_table(db)
    rows = db.execute(text("""
        SELECT id, name, platform, website, ref_code, clicks, created_at
        FROM ib_campaigns WHERE ib_id = :ib ORDER BY created_at DESC
    """), {"ib": ib_id}).fetchall()
    return {"campaigns": [{
        "id": r[0], "name": r[1], "platform": r[2] or "", "website": r[3] or "",
        "ref_code": r[4], "ref_link": _ref_link(r[4]), "clicks": r[5] or 0,
        "created_at": r[6].isoformat() if r[6] else None,
    } for r in rows]}


@router.post("/{ib_id}/campaigns")
def create_campaign(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _ensure_campaign_table(db)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required")
    ib = db.execute(text("SELECT ib_code FROM ibs WHERE id = :id"), {"id": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    # ref_code = IB code (sans 'IB') + short slug from name + a uniquifier
    import re, secrets
    base = (ib[0] or "").replace("IB", "")
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:8] or "camp"
    ref_code = f"{base}-{slug}-{secrets.token_hex(2)}"
    db.execute(text("""
        INSERT INTO ib_campaigns (ib_id, name, platform, website, ref_code)
        VALUES (:ib, :n, :p, :w, :rc)
    """), {"ib": ib_id, "n": name, "p": (data.get("platform") or "").strip(),
           "w": (data.get("website") or "").strip(), "rc": ref_code})
    db.commit()
    return {"ok": True, "ref_code": ref_code, "ref_link": _ref_link(ref_code)}


class PayCommissionRequest(BaseModel):
    ib_id: int
    amount: Optional[float] = None  # None = pay all unpaid


_PAY_ROLES = {"super_admin", "admin", "director", "accountant"}

@router.post("/pay-commission")
async def pay_commission(
    data: PayCommissionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Paying commission moves money on the books — restrict to admin/finance roles.
    if (current_user.role or "").lower() not in _PAY_ROLES:
        raise HTTPException(status_code=403, detail="You don't have permission to pay commissions.")
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


class SetLevelRequest(BaseModel):
    ib_level: Optional[int] = None
    level: Optional[int] = None     # accept either key name


@router.post("/{ib_id}/level")
async def set_ib_level(
    ib_id: int,
    data: SetLevelRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Quick inline level change from the IB Admin list (tickets #59 / #53).
    Sets ibs.ib_level directly. Validates the IB-5..IB-10 (Bronze..Master) range."""
    if not can_change_ib_level(current_user):
        raise HTTPException(status_code=403, detail="Only Zainab can change an IB level.")
    new_level = data.ib_level if data.ib_level is not None else data.level
    if new_level is None:
        raise HTTPException(status_code=400, detail="ib_level is required")
    try:
        new_level = int(new_level)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ib_level must be a number")
    if new_level < 5 or new_level > 10:
        raise HTTPException(status_code=400, detail="Level must be between IB-5 (Bronze) and IB-10 (Master)")
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    ib.ib_level = new_level
    db.commit()
    return {
        "ok": True,
        "id": ib_id,
        "name": ib.name or "",
        "ib_level": new_level,
        "tier": TIER_NAMES.get(new_level, "Bronze"),
    }


class PromoteIBRequest(BaseModel):
    ib_id: int
    new_level: int


@router.post("/promote")
async def promote_ib(
    data: PromoteIBRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not can_change_ib_level(current_user):
        raise HTTPException(status_code=403, detail="Only Zainab can change an IB level.")
    if data.new_level < 5 or data.new_level > 10:
        raise HTTPException(status_code=400, detail="Level must be between 5 and 10")
    ib = db.query(models.IB).filter(models.IB.id == data.ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    ib.ib_level = data.new_level
    db.commit()
    return {"message": f"{ib.name} promoted to level {data.new_level}"}


# ── Create / add a new IB (ticket #12: the "+ Add IB" button did nothing) ──
@router.post("")
@router.post("/")
def create_ib(payload: dict, db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    """Create an IB from an MT login (agent_id). Auto-fills name/contact from that
    client account when available; the form fields override."""
    try:
        agent_id = int(payload.get("agent_id") or payload.get("login") or 0)
    except (TypeError, ValueError):
        agent_id = 0
    if not agent_id:
        raise HTTPException(status_code=400, detail="Enter the IB's trading account login")

    # don't double-create for the same login
    exists = db.execute(text("SELECT id FROM ibs WHERE agent_id=:a"), {"a": agent_id}).fetchone()
    if exists:
        raise HTTPException(status_code=409, detail=f"An IB already exists for login {agent_id} (#{exists[0]})")

    # pull details from the client account if it exists
    c = db.execute(text("""
        SELECT name, email, phone, country, city, group_name FROM clients WHERE login=:a LIMIT 1
    """), {"a": agent_id}).fetchone()

    def pick(key, idx):
        v = (payload.get(key) or "").strip() if isinstance(payload.get(key), str) else payload.get(key)
        return v or (c[idx] if c else None)

    name = (payload.get("name") or "").strip() or (c[0] if c else None)
    if not name:
        raise HTTPException(status_code=400, detail="Name is required (account not found — enter it manually)")
    try:
        level = int(payload.get("ib_level") or 5)
    except (TypeError, ValueError):
        level = 5
    level = max(5, min(10, level))

    ib_code = f"IB{agent_id}"
    new_id = db.execute(text("""
        INSERT INTO ibs (agent_id, ib_code, name, email, phone, country, city, ib_level,
                         status, kyc_status, total_clients, active_clients, unique_ftds,
                         total_volume, net_deposits, total_commission, unpaid_commission,
                         paid_commission, balance, referral_link, created_at, updated_at)
        VALUES (:a,:code,:n,:e,:p,:co,:ci,:lvl,'active','pending',0,0,0,0,0,0,0,0,0,
                :link, NOW(), NOW())
        RETURNING id
    """), {"a": agent_id, "code": ib_code, "n": name,
           "e": pick("email", 1), "p": pick("phone", 2),
           "co": pick("country", 3), "ci": pick("city", 4), "lvl": level,
           "link": f"https://my1.tnfx.co/r/{ib_code}"}).scalar()

    # ── Ticket #12(a): auto-link this IB's existing referred clients. ──
    # IB→clients linkage is via clients.agent (the MT agent login) = ibs.agent_id.
    # We additively stamp the denormalized clients.ib_id on the matching rows only.
    linked = db.execute(text("""
        UPDATE clients SET ib_id = :ib_id
        WHERE agent = :agent_id AND ib_id IS DISTINCT FROM :ib_id
    """), {"ib_id": new_id, "agent_id": agent_id}).rowcount
    db.commit()

    return {
        "ok": True,
        "id": new_id,
        "linked_clients": linked,
        # Ticket #12(b): setting the IB up as an agent on the MT server is a gated
        # MT-provisioning action — NOT performed here; flag it for separate approval.
        "mt_agent_setup": "pending_approval",
        "message": (f"IB '{name}' (login {agent_id}) created; "
                    f"linked {linked} existing referred client(s). "
                    f"MT-server agent setup needs separate approval."),
    }
