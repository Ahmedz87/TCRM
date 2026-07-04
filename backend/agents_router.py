"""
agents_router.py — Sales-team overview (Sales Agents page).
Includes sales agents + sales managers + team leaders (role sales_agent/sales_manager
or title 'Team Leader'), excluding Narmeen (a sales director). Each row shows the
agent's lifetime book plus PERIOD activity:
  - clients / leads / verified_leads / ibs  = lifetime book
  - new_clients / new_ibs                   = registered in the selected period (clients.reg_date)
  - deposits / withdrawals                  = transactions in the period
  - commission                              = markup revenue their clients generated in the period
                                              ($ = SUM(deals.markup_profit)/10000; the per-lot markup)
Lead metrics come via the matched client (leads have no agent of their own yet).
Period uses the same options as IB Admin (today … last_year).
"""
from datetime import date as _date, timedelta as _td
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
from ib_router import period_dates
from perf_cache import cached
import models

router = APIRouter(prefix="/agents", tags=["Sales Agents"])

# Index-friendly date filters. reg_date / tx_date / deal_date / trade_date are VARCHAR
# holding ISO 'YYYY-MM-DD[ HH:MM:SS]'; created_at is a real timestamp. Comparing the raw
# column to 'YYYY-MM-DD' string/date bounds keeps the column un-wrapped so its btree index
# is used (a ::date cast forced a full scan of the huge deals/transactions tables).
# The regex guard is preserved so only well-formed ISO rows match (identical to the old
# CASE...substring::date which yielded NULL — and thus no match — for malformed values).
# End bound is EXCLUSIVE next-day so the old inclusive `<= :p_to` semantics are preserved.
def _next_day(d: str) -> str:
    """The day AFTER ISO date string d (exclusive upper bound)."""
    try:
        return (_date.fromisoformat(d) + _td(days=1)).isoformat()
    except Exception:
        return d + "~"

# In-period predicate for a VARCHAR ISO date column (period = [:p_from, :p_to] inclusive).
# Uses :p_from and :p_to_next (added to params by callers). Regex guard kept for identical results.
def _range(col: str) -> str:
    return (f"({col} ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' "
            f"AND {col} >= :p_from AND {col} < :p_to_next)")

_REG_DATE_IN = _range("c.reg_date")
_TX_DATE_IN  = _range("t.tx_date")

# who counts as sales team
_TEAM_WHERE = ("((u.role IN ('sales_agent','sales_manager') OR u.title ILIKE '%team leader%') "
               "AND u.full_name NOT ILIKE '%narmeen%')")


@router.get("")
def list_agents(
    search: str = Query(""),
    sort: str = Query("clients"),
    sort_dir: str = Query("desc"),   # 'asc' | 'desc' — per-column up/down sorting
    group: str = Query(""),          # '', 'sales', 'retention', 'team_leader'
    period: str = Query("this_month"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    team: int = Query(0),            # team-leader id: show that TL + their reports only
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # NOT role-scoped: the Sales Agents overview returns the SAME team-wide data for every
    # staff member (current_user is used for auth only; _TEAM_WHERE is a fixed predicate and
    # nothing in the query filters by the caller). Hence a fixed "all" scope in the key.
    cache_key = (f"agents:list:all:{period}:{date_from}:{date_to}:"
                 f"{group}:{sort}:{sort_dir}:{search}:t{team}")
    return cached(cache_key, 90, lambda: _build_agents(
        db, period, date_from, date_to, search, sort, group, team, sort_dir))


def _build_agents(db, period, date_from, date_to, search, sort, group, team=0, sort_dir="desc"):
    p_from, p_to = period_dates(period, date_from, date_to)
    params: dict = {"p_from": p_from, "p_to": p_to, "p_to_next": _next_day(p_to)}

    where = _TEAM_WHERE
    if search:
        where += " AND (u.full_name ILIKE :s OR u.email ILIKE :s)"; params["s"] = f"%{search}%"
    if group == "sales":
        where += " AND u.team_type = 'sales'"
    elif group == "retention":
        where += " AND u.team_type = 'retention'"
    elif group == "team_leader":
        where += " AND (u.title ILIKE '%team leader%' OR u.team_type = 'lead')"
    if team:
        # one team = that team leader + everyone who reports to them
        where += " AND (u.id = :team OR u.manager_id = :team)"; params["team"] = team

    sort_col = {
        "clients": "clients DESC", "new_clients": "new_clients DESC", "leads": "leads DESC",
        "verified": "verified_leads DESC", "ibs": "ibs DESC", "new_ibs": "new_ibs DESC",
        "deposits": "deposits DESC", "withdrawals": "withdrawals DESC",
        "commission": "commission DESC", "net": "net DESC", "name": "name ASC",
    }.get(sort, "clients DESC")

    rows = db.execute(text(f"""
        WITH ag AS (
            SELECT u.id, u.full_name, u.role, u.title, u.team_type, u.is_active,
                   COALESCE(u.commission_pct,10) AS commission_pct, COALESCE(u.sales_target,0) AS sales_target
            FROM users u WHERE {where}
        ),
        cl AS (
            -- count UNIQUE PEOPLE (customer_no), same grain as the Clients list — NOT raw account rows
            SELECT c.assigned_agent_id AS aid,
                   COUNT(DISTINCT c.customer_no) AS clients,
                   COUNT(DISTINCT c.customer_no) FILTER (WHERE COALESCE(c.total_deposits,0) > 0) AS depositors,
                   COUNT(DISTINCT c.customer_no) FILTER (WHERE {_REG_DATE_IN}) AS new_clients
            FROM clients c WHERE c.assigned_agent_id IS NOT NULL GROUP BY c.assigned_agent_id
        ),
        ld AS (
            -- REAL lead book per agent (leads.assigned_agent_id), not clients-who-were-leads
            SELECT l.assigned_agent_id AS aid,
                   COUNT(*) AS leads,
                   COUNT(*) FILTER (WHERE l.kyc_status='verified') AS verified_leads
            FROM leads l WHERE l.assigned_agent_id IS NOT NULL GROUP BY l.assigned_agent_id
        ),
        ib AS (
            SELECT c.assigned_agent_id AS aid,
                   COUNT(DISTINCT i.id) AS ibs,
                   COUNT(DISTINCT i.id) FILTER (WHERE {_REG_DATE_IN}) AS new_ibs
            FROM ibs i JOIN clients c ON c.login = i.agent_id
            WHERE c.assigned_agent_id IS NOT NULL GROUP BY c.assigned_agent_id
        ),
        mn AS (
            SELECT c.assigned_agent_id AS aid,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='deposit'),0) AS dep,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='withdrawal' AND COALESCE(t.status,'')<>'rejected'),0) AS wd
            FROM clients c JOIN transactions t ON t.login = c.login
            WHERE c.assigned_agent_id IS NOT NULL AND {_TX_DATE_IN}
            GROUP BY c.assigned_agent_id
        ),
        comm AS (
            SELECT c.assigned_agent_id AS aid,
                   COALESCE(SUM(d.markup_profit),0)/10000.0 AS commission
            FROM clients c JOIN deals d ON d.login = c.login
            WHERE c.assigned_agent_id IS NOT NULL AND d.action IN (0,1)
              AND d.deal_date <> '' AND d.deal_date >= :p_from AND d.deal_date < :p_to_next
            GROUP BY c.assigned_agent_id
        ),
        ibc AS (
            SELECT c.assigned_agent_id AS aid,
                   COALESCE(SUM(ic.commission_usd),0) AS ib_comm
            FROM clients c JOIN ib_commissions ic ON ic.client_login = c.login
            WHERE c.assigned_agent_id IS NOT NULL
              AND ic.trade_date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
              AND ic.trade_date >= :p_from AND ic.trade_date < :p_to_next
            GROUP BY c.assigned_agent_id
        )
        SELECT ag.id, ag.full_name, ag.role, ag.title, ag.team_type, ag.is_active,
               ag.commission_pct, ag.sales_target, COALESCE(ibc.ib_comm,0) AS ib_comm,
               COALESCE(cl.clients,0)        AS clients,
               COALESCE(cl.new_clients,0)    AS new_clients,
               COALESCE(ld.leads,0)          AS leads,
               COALESCE(ld.verified_leads,0) AS verified_leads,
               COALESCE(cl.depositors,0)     AS depositors,
               COALESCE(ib.ibs,0)            AS ibs,
               COALESCE(ib.new_ibs,0)        AS new_ibs,
               COALESCE(mn.dep,0)            AS deposits,
               COALESCE(mn.wd,0)             AS withdrawals,
               COALESCE(comm.commission,0)   AS commission,
               COALESCE(mn.dep,0) - COALESCE(mn.wd,0) AS net
        FROM ag
        LEFT JOIN cl   ON cl.aid   = ag.id
        LEFT JOIN ld   ON ld.aid   = ag.id
        LEFT JOIN ib   ON ib.aid   = ag.id
        LEFT JOIN mn   ON mn.aid   = ag.id
        LEFT JOIN comm ON comm.aid = ag.id
        LEFT JOIN ibc  ON ibc.aid  = ag.id
        ORDER BY {sort_col} NULLS LAST
    """), params).fetchall()

    def role_label(role, title, team_type):
        if title and 'team leader' in title.lower(): return 'Team Leader'
        if team_type == 'lead':       return 'Team Leader'
        if team_type == 'retention':  return 'Retention'      # role may say sales_agent, but team_type is the truth
        if team_type == 'sales':      return 'Sales Agent'
        if role == 'sales_manager':   return 'Sales Manager'
        if role == 'sales_agent':     return 'Sales Agent'
        return title or role or '—'

    agents = []
    for r in rows:
        pct      = float(r[6] or 10)
        ib_comm  = float(r[8] or 0)
        markup   = float(r[18] or 0)       # company markup from his clients
        net_comm = markup - ib_comm        # net after paying IBs
        agents.append({
            "id": r[0], "name": r[1] or "—", "role": role_label(r[2], r[3], r[4]),
            "title": r[3] or "", "team": r[4] or "", "is_active": bool(r[5]),
            "commission_pct": pct, "sales_target": float(r[7] or 0),
            "clients": r[9], "new_clients": r[10], "leads": r[11], "verified_leads": r[12],
            "depositors": r[13], "ibs": r[14], "new_ibs": r[15],
            "deposits": float(r[16]), "withdrawals": float(r[17]),
            "commission": markup, "net": float(r[19]),
            "ib_commission": ib_comm,
            "net_commission": net_comm,
            "sales_commission": net_comm * pct / 100.0,
        })

    # sort in Python so EVERY column (incl. the computed ones) is sortable both directions
    _sk = {
        "name": lambda a: (a["name"] or "").lower(), "clients": lambda a: a["clients"],
        "new_clients": lambda a: a["new_clients"], "leads": lambda a: a["leads"],
        "verified": lambda a: a["verified_leads"], "ibs": lambda a: a["ibs"],
        "new_ibs": lambda a: a["new_ibs"], "deposits": lambda a: a["deposits"],
        "withdrawals": lambda a: a["withdrawals"], "commission": lambda a: a["commission"],
        "ib_commission": lambda a: a["ib_commission"], "net_commission": lambda a: a["net_commission"],
        "sales_commission": lambda a: a["sales_commission"], "net": lambda a: a["net"],
    }
    keyf = _sk.get(sort, _sk["clients"])
    agents.sort(key=keyf, reverse=(str(sort_dir).lower() != "asc"))

    # team-leader list for the "filter by team" dropdown (always the full set, regardless of filter)
    team_rows = db.execute(text(
        "SELECT id, full_name FROM users WHERE (title ILIKE '%team leader%' OR role='sales_manager') "
        "AND COALESCE(is_active, TRUE) ORDER BY full_name")).fetchall()

    return {
        "agents": agents,
        "teams": [{"id": t[0], "name": t[1]} for t in team_rows],
        "period": {"from": p_from, "to": p_to},
        "kpis": {
            "total_agents": len(agents),
            "total_clients": sum(a["clients"] for a in agents),
            "new_clients": sum(a["new_clients"] for a in agents),
            "total_ibs": sum(a["ibs"] for a in agents),
            "total_deposits": sum(a["deposits"] for a in agents),
            "total_withdrawals": sum(a["withdrawals"] for a in agents),
            "total_commission": sum(a["commission"] for a in agents),
            "total_ib_commission": sum(a["ib_commission"] for a in agents),
            "total_net_commission": sum(a["net_commission"] for a in agents),
            "total_sales_commission": sum(a["sales_commission"] for a in agents),
        },
    }


@router.get("/{agent_id}")
def agent_detail(agent_id: int, period: str = Query("this_month"),
                 date_from: str = Query(""), date_to: str = Query(""),
                 db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p_from, p_to = period_dates(period, date_from, date_to)
    P = {"id": agent_id, "p_from": p_from, "p_to": p_to, "p_to_next": _next_day(p_to)}
    u = db.execute(text("""
        SELECT full_name, role, title, team_type, COALESCE(commission_pct,10), COALESCE(sales_target,0),
               extension, department, email
        FROM users WHERE id=:id
    """), {"id": agent_id}).fetchone()
    if not u:
        return {"error": "agent not found"}

    def scalar(sql, extra=None):
        return db.execute(text(sql), {**P, **(extra or {})}).scalar() or 0

    # book + period activity
    clients   = scalar("SELECT COUNT(*) FROM clients WHERE assigned_agent_id=:id")
    depositors= scalar("SELECT COUNT(*) FROM clients WHERE assigned_agent_id=:id AND COALESCE(total_deposits,0)>0")
    new_clients = scalar(f"SELECT COUNT(*) FROM clients c WHERE c.assigned_agent_id=:id AND {_REG_DATE_IN}")
    own_clients = scalar("SELECT COUNT(*) FROM clients WHERE assigned_agent_id=:id AND matched_lead_id IS NOT NULL")
    leads     = scalar("SELECT COUNT(*) FROM clients WHERE assigned_agent_id=:id AND matched_lead_id IS NOT NULL")
    verified_leads = scalar("SELECT COUNT(*) FROM clients WHERE assigned_agent_id=:id AND matched_lead_id IS NOT NULL AND kyc_status='verified'")
    own_leads = scalar("SELECT COUNT(*) FROM leads WHERE assigned_agent_id=:id")
    ibs       = scalar("SELECT COUNT(DISTINCT i.id) FROM ibs i JOIN clients c ON c.login=i.agent_id WHERE c.assigned_agent_id=:id")
    active_ibs= scalar("""SELECT COUNT(DISTINCT i.id) FROM ibs i JOIN clients c ON c.login=i.agent_id
                          WHERE c.assigned_agent_id=:id AND EXISTS (
                            SELECT 1 FROM deals d JOIN clients cc ON cc.login=d.login
                            WHERE cc.agent=i.agent_id AND d.action IN (0,1)
                            AND d.deal_date <> '' AND d.deal_date >= :p_from AND d.deal_date < :p_to_next)""")
    calls     = scalar("SELECT COUNT(*) FROM call_actions WHERE agent_id=:id AND created_at >= :p_from AND created_at < :p_to_next")
    deposits  = scalar(f"SELECT COALESCE(SUM(t.amount),0) FROM clients c JOIN transactions t ON t.login=c.login WHERE c.assigned_agent_id=:id AND t.tx_type='deposit' AND {_TX_DATE_IN}")
    withdrawals = scalar(f"SELECT COALESCE(SUM(t.amount),0) FROM clients c JOIN transactions t ON t.login=c.login WHERE c.assigned_agent_id=:id AND t.tx_type='withdrawal' AND COALESCE(t.status,'')<>'rejected' AND {_TX_DATE_IN}")
    markup    = float(scalar("""SELECT COALESCE(SUM(d.markup_profit),0)/10000.0 FROM clients c JOIN deals d ON d.login=c.login
                          WHERE c.assigned_agent_id=:id AND d.action IN (0,1) AND d.deal_date <> '' AND d.deal_date >= :p_from AND d.deal_date < :p_to_next"""))
    ib_comm   = float(scalar("""SELECT COALESCE(SUM(ic.commission_usd),0) FROM clients c JOIN ib_commissions ic ON ic.client_login=c.login
                          WHERE c.assigned_agent_id=:id AND ic.trade_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                          AND ic.trade_date >= :p_from AND ic.trade_date < :p_to_next"""))
    lots      = float(scalar("""SELECT COALESCE(SUM(d.volume),0)/10000.0 FROM clients c JOIN deals d ON d.login=c.login
                          WHERE c.assigned_agent_id=:id AND d.action IN (0,1) AND d.deal_date <> '' AND d.deal_date >= :p_from AND d.deal_date < :p_to_next"""))
    pct = float(u[4] or 10); target = float(u[5] or 0)
    net_comm = markup - ib_comm
    sales_comm = net_comm * pct / 100.0

    # top clients by company markup profit (this period)
    top = db.execute(text("""
        SELECT c.login, MIN(c.name), COALESCE(SUM(d.markup_profit),0)/10000.0 AS markup,
               COALESCE(SUM(d.volume),0)/10000.0 AS lots, COUNT(*) AS trades
        FROM clients c JOIN deals d ON d.login=c.login
        WHERE c.assigned_agent_id=:id AND d.action IN (0,1)
          AND d.deal_date <> '' AND d.deal_date >= :p_from AND d.deal_date < :p_to_next
        GROUP BY c.login ORDER BY markup DESC LIMIT 25
    """), P).fetchall()

    return {
        "id": agent_id, "name": u[0], "role": u[1], "title": u[2] or "", "team_type": u[3] or "",
        "department": u[7] or "", "email": u[8] or "", "extension": u[6] or "",
        "period": {"from": p_from, "to": p_to},
        "commission_pct": pct, "sales_target": target,
        "kpis": {
            "clients": clients, "active_traders": depositors, "new_clients": new_clients,
            "own_clients": own_clients, "leads": leads, "verified_leads": verified_leads,
            "own_leads": own_leads, "ibs": ibs, "active_ibs": active_ibs, "calls": calls,
            "deposits": float(deposits), "withdrawals": float(withdrawals),
            "net_deposit": float(deposits) - float(withdrawals), "lots": lots,
            "markup": markup, "ib_commission": ib_comm, "net_commission": net_comm,
            "sales_commission": sales_comm,
            "target": target, "target_done": sales_comm, "target_left": max(0.0, target - sales_comm),
            "target_pct": round(sales_comm / target * 100, 1) if target > 0 else 0,
        },
        "top_clients": [{
            "login": r[0], "name": r[1] or "", "markup": float(r[2] or 0),
            "lots": float(r[3] or 0), "trades": r[4],
        } for r in top],
    }


@router.post("/{agent_id}/settings")
def set_agent_settings(agent_id: int, data: dict, db: Session = Depends(get_db),
                       current_user: models.User = Depends(get_current_user)):
    """Set the agent's commission % and/or sales target."""
    sets, params = [], {"id": agent_id}
    if "commission_pct" in data and data["commission_pct"] is not None:
        sets.append("commission_pct=:pct"); params["pct"] = float(data["commission_pct"])
    if "sales_target" in data and data["sales_target"] is not None:
        sets.append("sales_target=:tgt"); params["tgt"] = float(data["sales_target"])
    if not sets:
        return {"ok": False, "error": "nothing to update"}
    db.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id=:id"), params)
    db.commit()
    return {"ok": True}
