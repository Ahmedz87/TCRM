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
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
from ib_router import period_dates
from perf_cache import cached
import sales_commission as SC
import crm_settings as CFG
import models


# go-live hardening: commission rates / targets are management decisions.
_MGMT_ROLES = {"super_admin", "admin", "director", "sales_manager"}

def _require_mgmt(current_user):
    role = (getattr(current_user, "role", "") or "").lower()
    if role not in _MGMT_ROLES:
        raise HTTPException(status_code=403, detail="Managers/admins only")

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
    # ROLE-SCOPED (Jul 2026): agents see only THEMSELVES; team leaders/managers see SELF + their
    # DIRECT reports; admins/director see all (rbac.visible_agent_ids). The scope is part of the
    # cache key so each viewer-tier gets its own cached slice.
    import rbac
    vis = rbac.visible_agent_ids(db, current_user)
    scope = "all" if vis is None else "v:" + ",".join(map(str, sorted(vis)))
    cache_key = (f"agents:list:{scope}:{period}:{date_from}:{date_to}:"
                 f"{group}:{sort}:{sort_dir}:{search}:t{team}")
    return cached(cache_key, 360, lambda: _build_agents(
        db, period, date_from, date_to, search, sort, group, team, sort_dir, visible_ids=vis))


@router.get("/names")
def list_agent_names(db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    """Lightweight id+name list of the sales team for filter dropdowns (Transactions etc.).
    The full GET /agents builds period KPIs over the deals table (~9s cold) — never call
    that just to populate a <datalist>. Same population rule as the full list."""
    rows = db.execute(text(f"""
        SELECT u.id, u.full_name, u.role, u.title FROM users u
        WHERE {_TEAM_WHERE} ORDER BY u.full_name""")).fetchall()
    return {"agents": [{"id": r[0], "name": r[1], "full_name": r[1],
                        "role": r[2], "title": r[3]} for r in rows]}


def _build_agents(db, period, date_from, date_to, search, sort, group, team=0, sort_dir="desc", visible_ids=None):
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    # Iraqi-day boundaries in UTC (crm_tz): day D = [D-1 21:00, D 21:00) UTC
    params: dict = {"p_from": day_lo(p_from), "p_to": p_to, "p_to_next": day_hi(p_to)}

    where = _TEAM_WHERE
    if visible_ids is not None:               # role scope: restrict to visible agents
        if not visible_ids:
            where += " AND FALSE"
        else:
            where += " AND u.id = ANY(:vis_ids)"; params["vis_ids"] = list(visible_ids)
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
            -- count UNIQUE PEOPLE (customer_no), same grain AND same universe as the Clients list:
            -- only customers kind='client' (excludes lead-kind/archived customers whose accounts
            -- still carry an agent — those made this page count ~3.9k more people than the Clients page)
            SELECT c.assigned_agent_id AS aid,
                   COUNT(DISTINCT c.customer_no) AS clients,
                   COUNT(DISTINCT c.customer_no) FILTER (WHERE COALESCE(c.total_deposits,0) > 0) AS depositors,
                   COUNT(DISTINCT c.customer_no) FILTER (WHERE {_REG_DATE_IN}) AS new_clients
            FROM clients c
            JOIN customers cu ON cu.customer_no = c.customer_no AND cu.kind = 'client'
            WHERE c.assigned_agent_id IS NOT NULL GROUP BY c.assigned_agent_id
        ),
        ld AS (
            -- REAL lead book per agent (leads.assigned_agent_id), not clients-who-were-leads.
            -- own_leads = leads the agent ADDED THEMSELVES (+Add on the Leads page), not
            -- campaign leads distributed to them.
            SELECT l.assigned_agent_id AS aid,
                   COUNT(*) AS leads,
                   COUNT(*) FILTER (WHERE l.kyc_status='verified') AS verified_leads,
                   COUNT(*) FILTER (WHERE l.source IN ('sales_agent','manual')) AS own_leads
            FROM leads l WHERE l.assigned_agent_id IS NOT NULL GROUP BY l.assigned_agent_id
        ),
        conv AS (
            -- CONVERTED in period: this agent's lead's customer made their FIRST deposit in the
            -- period (any FTD; the NDA subset that pays the $10 comes from sales_commission).
            SELECT o.lead_agent AS aid, COUNT(*) AS converted
            FROM (SELECT DISTINCT ON (l.customer_no) l.customer_no, l.assigned_agent_id AS lead_agent
                  FROM leads l WHERE l.customer_no IS NOT NULL AND l.assigned_agent_id IS NOT NULL
                  ORDER BY l.customer_no, l.created_at, l.id) o
            JOIN (SELECT customer_no, MIN(NULLIF(first_deposit_at,'')) AS fda
                  FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no) f
              ON f.customer_no = o.customer_no
            WHERE f.fda >= :p_from AND f.fda < :p_to_next
            GROUP BY o.lead_agent
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
            -- PERF (Jul 2026): reads the per-(login,day) rollup (~483k rows, date-indexed)
            -- instead of joining clients->deals (16.8M) — was ~39s cold, now sub-second.
            SELECT c.assigned_agent_id AS aid,
                   COALESCE(SUM(m.markup_usd),0) AS commission
            FROM clients c JOIN deals_login_daily m ON m.login = c.login
            WHERE c.assigned_agent_id IS NOT NULL
              AND m.day >= :p_from AND m.day < :p_to_next
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
        ),
        nda AS (
            -- FTD = new deposit accounts (unique CUSTOMER, first deposit in period); NDA = the
            -- genuinely-new subset (no relation to any existing customer). Attributes each customer
            -- to the agent on their FTD account (earliest first_deposit_at). is_nda from nda_engine.
            SELECT t.aid,
                   COUNT(*) FILTER (WHERE t.in_p)                 AS ftd,
                   COUNT(*) FILTER (WHERE t.in_p AND t.is_nda)    AS nda,
                   COUNT(*) FILTER (WHERE t.is_nda)               AS nda_all
            FROM (
                SELECT DISTINCT ON (c.customer_no) c.customer_no,
                       c.assigned_agent_id AS aid, c.is_nda,
                       (NULLIF(c.first_deposit_at,'') >= :p_from
                        AND c.first_deposit_at < :p_to_next) AS in_p
                FROM clients c
                WHERE c.assigned_agent_id IS NOT NULL AND c.customer_no IS NOT NULL
                  AND c.is_nda IS NOT NULL
                ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC NULLS LAST
            ) t GROUP BY t.aid
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
               COALESCE(mn.dep,0) - COALESCE(mn.wd,0) AS net,
               COALESCE(nda.ftd,0)           AS ftd,
               COALESCE(nda.nda,0)           AS nda,
               COALESCE(nda.nda_all,0)       AS nda_all,
               COALESCE(ld.own_leads,0)      AS own_leads,
               COALESCE(conv.converted,0)    AS converted
        FROM ag
        LEFT JOIN cl   ON cl.aid   = ag.id
        LEFT JOIN ld   ON ld.aid   = ag.id
        LEFT JOIN ib   ON ib.aid   = ag.id
        LEFT JOIN mn   ON mn.aid   = ag.id
        LEFT JOIN comm ON comm.aid = ag.id
        LEFT JOIN ibc  ON ibc.aid  = ag.id
        LEFT JOIN nda  ON nda.aid  = ag.id
        LEFT JOIN conv ON conv.aid = ag.id
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
            "ftd": r[20], "nda": r[21], "nda_all": r[22],
            "own_leads": r[23], "converted": r[24],
            "nda_pct": round(100 * r[21] / r[20]) if r[20] else 0,
            "ib_commission": ib_comm,
            "net_commission": net_comm,
            "sales_commission": net_comm * pct / 100.0,
        })

    # ── agent EARNINGS per the desk's commission rules (sales_commission.py) ──────────────
    # Overlays each agent's actual commission: sales = $unit × NDA-FTDs acquired + markup% on
    # their own/IB clients; retention = markup% gated at D2 for transferred clients. The
    # markup/ib_commission/net columns above stay the COMPANY view (all of the agent's book).
    unit = CFG.get_float(db, "sales_unit_usd", 10.0)
    try:
        comm = SC.compute(db, params["p_from"], params["p_to_next"], unit)
    except Exception:
        comm = {}
    try:
        import sales_performance as SP
        perf = SP.perf_all(db, agents, period, params["p_from"], params["p_to_next"])
    except Exception:
        perf = {}
    for a in agents:
        cc = comm.get(a["id"]) or {}
        a["unit_rate"]        = unit
        a["unit_nda"]         = cc.get("nda_ftd", 0)
        a["unit_bonus"]       = cc.get("unit_bonus", 0.0)
        a["markup_commission"] = cc.get("markup_comm", 0.0)
        a["sales_commission"] = cc.get("commission", 0.0)   # agent's real earning (was net×pct)
        # item #6: Company markup / IB / Net now reflect the ENTITLED (gated) basis — the trades
        # this agent actually earns on (retention: own/IB from D1, transferred after D2), not the
        # raw all-clients markup. Sales agents earn per-unit, so their gated markup is ~0 by design.
        if a["id"] in comm:
            a["commission"]     = cc.get("gross_markup", a["commission"])   # "Company markup" column
            a["ib_commission"]  = cc.get("comm_ib", a["ib_commission"])
            a["net_commission"] = cc.get("net_markup", a["net_commission"])
        # performance score (0-100, demo this month) + eligible commission = commission × score%
        pp = perf.get(a["id"]) or {}
        a["performance"]  = pp.get("score", 0.0)
        a["perf_demo"]    = pp.get("demo", False)
        a["perf_breakdown"] = pp.get("breakdown", [])
        a["eligible_commission"] = round(a["sales_commission"] * a["performance"] / 100.0, 2)

    # sort in Python so EVERY column (incl. the computed ones) is sortable both directions
    _sk = {
        "name": lambda a: (a["name"] or "").lower(), "clients": lambda a: a["clients"],
        "new_clients": lambda a: a["new_clients"], "leads": lambda a: a["leads"],
        "verified": lambda a: a["verified_leads"], "ibs": lambda a: a["ibs"],
        "new_ibs": lambda a: a["new_ibs"], "deposits": lambda a: a["deposits"],
        "withdrawals": lambda a: a["withdrawals"], "commission": lambda a: a["commission"],
        "ib_commission": lambda a: a["ib_commission"], "net_commission": lambda a: a["net_commission"],
        "sales_commission": lambda a: a["sales_commission"], "net": lambda a: a["net"],
        "ftd": lambda a: a["ftd"], "nda": lambda a: a["nda"], "nda_pct": lambda a: a["nda_pct"],
        "unit_bonus": lambda a: a["unit_bonus"], "markup_commission": lambda a: a["markup_commission"],
        "own_leads": lambda a: a["own_leads"], "converted": lambda a: a["converted"],
        "performance": lambda a: a["performance"], "eligible_commission": lambda a: a["eligible_commission"],
    }
    keyf = _sk.get(sort, _sk["clients"])
    agents.sort(key=keyf, reverse=(str(sort_dir).lower() != "asc"))

    # UNIQUE people across the listed agents — the sum of per-agent counts double-counts a person
    # whose accounts sit under two agents, so the TOTAL KPI shows this too.
    _ids = [a["id"] for a in agents]
    uniq_clients = db.execute(text(
        "SELECT COUNT(DISTINCT c.customer_no) FROM clients c "
        "JOIN customers cu ON cu.customer_no = c.customer_no AND cu.kind='client' "
        "WHERE c.assigned_agent_id = ANY(:ids)"), {"ids": _ids}).scalar() or 0 if _ids else 0

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
            "unique_clients": uniq_clients,
            "new_clients": sum(a["new_clients"] for a in agents),
            "total_ftd": sum(a["ftd"] for a in agents),
            "total_nda": sum(a["nda"] for a in agents),
            "total_ibs": sum(a["ibs"] for a in agents),
            "total_deposits": sum(a["deposits"] for a in agents),
            "total_withdrawals": sum(a["withdrawals"] for a in agents),
            "total_commission": sum(a["commission"] for a in agents),
            "total_ib_commission": sum(a["ib_commission"] for a in agents),
            "total_net_commission": sum(a["net_commission"] for a in agents),
            "total_sales_commission": sum(a["sales_commission"] for a in agents),
            "total_unit_bonus": sum(a["unit_bonus"] for a in agents),
            "total_unit_nda": sum(a["unit_nda"] for a in agents),
            "total_converted": sum(a["converted"] for a in agents),
            "total_markup_commission": sum(a["markup_commission"] for a in agents),
            "total_eligible_commission": sum(a["eligible_commission"] for a in agents),
            "avg_performance": round(sum(a["performance"] for a in agents) / len(agents), 1) if agents else 0,
            "perf_demo": any(a.get("perf_demo") for a in agents),
            "unit_rate": unit,
        },
    }


@router.get("/commission-settings")
def get_commission_settings(db: Session = Depends(get_db),
                            current_user: models.User = Depends(get_current_user)):
    """Tunable commission constants (the sales UNIT bonus $ per NDA first-deposit)."""
    return {"sales_unit_usd": CFG.get_float(db, "sales_unit_usd", 10.0)}


@router.post("/commission-settings")
def set_commission_settings(data: dict, db: Session = Depends(get_db),
                            current_user: models.User = Depends(get_current_user)):
    """Update the sales unit bonus rate ($ per NDA first-deposit)."""
    _require_mgmt(current_user)
    if "sales_unit_usd" in data and data["sales_unit_usd"] is not None:
        try:
            v = max(0.0, float(data["sales_unit_usd"]))
        except (TypeError, ValueError):
            return {"ok": False, "error": "sales_unit_usd must be a number"}
        CFG.set_setting(db, "sales_unit_usd", v)
        return {"ok": True, "sales_unit_usd": v}
    return {"ok": False, "error": "nothing to update"}


@router.get("/scoring-settings")
def get_scoring_settings(team: str = Query("retention"),
                         db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    """GENERAL performance rules for a team (sales | retention). Team leaders/managers use the
    retention set."""
    import sales_performance as SP
    return {"team": SP._team_key(team), **SP.team_cfg(db, team)}


@router.post("/scoring-settings")
def set_scoring_settings(data: dict, db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    """Update a team's general weights/targets. Body: {team:'sales'|'retention', perf_w_*:.., ..}."""
    _require_mgmt(current_user)
    import sales_performance as SP
    tk = SP._team_key(data.get("team") or "retention")
    saved = {}
    for k in SP.DEF:
        if k in data and data[k] is not None:
            try:
                CFG.set_setting(db, f"{k}_{tk}", max(0.0, float(data[k]))); saved[k] = float(data[k])
            except (TypeError, ValueError):
                pass
    _invalidate_agents()
    return {"ok": True, "team": tk, "saved": saved}


@router.get("/{agent_id}/scoring-rules")
def get_agent_scoring(agent_id: int, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    """INDIVIDUAL scoring overrides for one agent + the effective (resolved) rule. Individual > team."""
    import sales_performance as SP
    tt = db.execute(text("SELECT team_type FROM users WHERE id=:id"), {"id": agent_id}).scalar() or ""
    return {"agent_id": agent_id, "team": SP._team_key(tt),
            "overrides": SP.agent_overrides(db, agent_id),
            "effective": SP._cfg(db, tt, agent_id),
            "team_general": SP.team_cfg(db, tt)}


@router.post("/{agent_id}/scoring-rules")
def set_agent_scoring(agent_id: int, data: dict, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    """Set/clear a single agent's individual overrides (these WIN over the team general rule).
    Pass a key with value null/empty to CLEAR that override (falls back to the team rule)."""
    _require_mgmt(current_user)
    import sales_performance as SP
    saved, cleared = {}, []
    for k in SP.DEF:
        if k not in data:
            continue
        v = data[k]
        if v is None or v == "":
            db.execute(text("DELETE FROM agent_scoring_rules WHERE agent_id=:a AND key=:k"),
                       {"a": agent_id, "k": k}); cleared.append(k)
        else:
            try:
                fv = max(0.0, float(v))
                db.execute(text("""INSERT INTO agent_scoring_rules (agent_id,key,val) VALUES (:a,:k,:v)
                    ON CONFLICT (agent_id,key) DO UPDATE SET val=EXCLUDED.val"""),
                    {"a": agent_id, "k": k, "v": fv}); saved[k] = fv
            except (TypeError, ValueError):
                pass
    db.commit()
    _invalidate_agents()
    return {"ok": True, "saved": saved, "cleared": cleared}


def _invalidate_agents():
    try:
        from perf_cache import invalidate
        invalidate("agents:")
    except Exception:
        pass


@router.post("/scoring-snapshot")
def scoring_snapshot(data: dict, db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    """Freeze the final performance score for a month (YYYY-MM) so past eligible commission is
    locked. Run at month-end (schedule a monthly task). Management only."""
    _require_mgmt(current_user)
    import sales_performance as SP
    month = (data.get("month") or "").strip()
    if len(month) != 7:
        return {"ok": False, "error": "month must be YYYY-MM"}
    return {"ok": True, **SP.freeze_month(db, month)}


def _nda_reasons(db, customer_no):
    """Why is this FTD customer NOT an NDA — the concrete relation(s) to OTHER customers.
    Recomputes the same signals nda_engine.related_customers uses (device/ip/phone/email/
    payment-sender/family), but for ONE customer and WITH the counterparty named."""
    out = []
    try:
        # shared device / IP
        for r in db.execute(text("""
            SELECT ai.identifier_type, ai.identifier_value, c2.customer_no, MIN(c2.name), MIN(c2.login)
            FROM account_identifiers ai
            JOIN clients c  ON c.login = ai.login AND c.customer_no = :cn
            JOIN account_identifiers ai2 ON ai2.identifier_type = ai.identifier_type
                 AND ai2.identifier_value = ai.identifier_value AND ai2.login <> ai.login
            JOIN clients c2 ON c2.login = ai2.login AND c2.customer_no IS NOT NULL AND c2.customer_no <> :cn
            WHERE ai.identifier_type IN ('cid','mqid','ip') AND ai.identifier_value NOT IN ('0','')
            GROUP BY 1, 2, 3 LIMIT 4"""), {"cn": customer_no}).fetchall():
            typ = {"cid": "same device", "mqid": "same device", "ip": "same IP"}[r[0]]
            out.append({"type": typ, "value": str(r[1])[:24], "other_customer": r[2],
                        "other_name": r[3] or "", "other_login": r[4]})
        # same phone (last 9 digits)
        for r in db.execute(text("""
            SELECT c2.customer_no, MIN(c2.name), MIN(c2.login)
            FROM clients c
            JOIN clients c2 ON c2.customer_no IS NOT NULL AND c2.customer_no <> :cn
                 AND length(regexp_replace(COALESCE(c2.phone,''),'[^0-9]','','g')) >= 9
                 AND RIGHT(regexp_replace(COALESCE(c2.phone,''),'[^0-9]','','g'),9)
                   = RIGHT(regexp_replace(COALESCE(c.phone,''),'[^0-9]','','g'),9)
            WHERE c.customer_no = :cn
              AND length(regexp_replace(COALESCE(c.phone,''),'[^0-9]','','g')) >= 9
            GROUP BY 1 LIMIT 3"""), {"cn": customer_no}).fetchall():
            out.append({"type": "same phone", "value": "", "other_customer": r[0],
                        "other_name": r[1] or "", "other_login": r[2]})
        # similar email (dots/+tags stripped = same inbox family)
        for r in db.execute(text(r"""
            SELECT c2.customer_no, MIN(c2.name), MIN(c2.login)
            FROM clients c
            JOIN clients c2 ON c2.customer_no IS NOT NULL AND c2.customer_no <> :cn
                 AND c2.email IS NOT NULL AND c2.email <> ''
                 AND replace(regexp_replace(lower(split_part(c2.email,'@',1)),'\+.*$','','g'),'.','')
                   = replace(regexp_replace(lower(split_part(c.email,'@',1)),'\+.*$','','g'),'.','')
                 AND length(replace(regexp_replace(lower(split_part(c.email,'@',1)),'\+.*$','','g'),'.','')) >= 4
            WHERE c.customer_no = :cn AND c.email IS NOT NULL AND c.email <> ''
            GROUP BY 1 LIMIT 3"""), {"cn": customer_no}).fetchall():
            out.append({"type": "similar email", "value": "", "other_customer": r[0],
                        "other_name": r[1] or "", "other_login": r[2]})
        # same payment sender (same Qi card / wallet funded both)
        for r in db.execute(text("""
            SELECT ps.method || ' sender', c2.customer_no, MIN(c2.name), MIN(c2.login)
            FROM client_payment_senders ps
            JOIN clients c  ON c.login = ps.client_login AND c.customer_no = :cn
            JOIN client_payment_senders ps2 ON ps2.method = ps.method AND ps2.sender_key = ps.sender_key
                 AND ps2.client_login <> ps.client_login
            JOIN clients c2 ON c2.login = ps2.client_login AND c2.customer_no IS NOT NULL AND c2.customer_no <> :cn
            GROUP BY 1, 2 LIMIT 3"""), {"cn": customer_no}).fetchall():
            out.append({"type": f"same {r[0]}", "value": "", "other_customer": r[1],
                        "other_name": r[2] or "", "other_login": r[3]})
        # family engine
        fam = db.execute(text("SELECT MIN(family_code) FROM clients WHERE customer_no=:cn AND family_code IS NOT NULL"),
                         {"cn": customer_no}).scalar()
        if fam:
            out.append({"type": "family group", "value": str(fam), "other_customer": None,
                        "other_name": "", "other_login": None})
    except Exception:
        db.rollback()
    return out


@router.get("/{agent_id}/ftd-detail")
def agent_ftd_detail(agent_id: int, period: str = Query("this_month"),
                     date_from: str = Query(""), date_to: str = Query(""),
                     db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Drill-down for the FTD/NDA columns: each FTD customer of this agent in the period,
    NDA yes/no, and for non-NDA the concrete relation(s) that disqualified them."""
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    P = {"id": agent_id, "f": day_lo(p_from), "tnext": day_hi(p_to)}
    rows = db.execute(text("""
        WITH cust AS (
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.login, c.name,
                   c.assigned_agent_id AS aid, c.is_nda, NULLIF(c.first_deposit_at,'') AS fda
            FROM clients c
            WHERE c.customer_no IS NOT NULL AND c.is_nda IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC NULLS LAST, c.login)
        SELECT customer_no, login, name, is_nda, left(fda,16),
               (SELECT MIN(t.amount) FROM transactions t
                 WHERE t.login = cust.login AND t.tx_type='deposit' AND t.amount > 0)
        FROM cust
        WHERE aid = :id AND fda >= :f AND fda < :tnext
        ORDER BY fda"""), P).fetchall()
    out = []
    for cn, login, name, is_nda, fda, amt in rows:
        out.append({
            "customer_no": cn, "login": login, "name": name or "", "ftd_date": fda,
            "ftd_amount": float(amt or 0), "is_nda": bool(is_nda),
            "reasons": [] if is_nda else _nda_reasons(db, cn),
        })
    return {"period": {"from": p_from, "to": p_to}, "ftds": out,
            "ftd": len(out), "nda": sum(1 for x in out if x["is_nda"])}


@router.get("/{agent_id}/markup-calculator")
def markup_calculator(agent_id: int, period: str = Query("this_month"),
                      date_from: str = Query(""), date_to: str = Query(""),
                      group: str = Query("clients"),          # clients|trades|daily|weekly|monthly
                      country: str = Query(""), city: str = Query(""),
                      ib: str = Query("all"),                 # all|yes|no  (under an IB?)
                      client: str = Query(""),                # a login to expand its trades
                      db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    """Retention MARKUP CALCULATOR: per-client + per-trade breakdown showing which trades count
    (entitled) vs not (pre-D2 = red 'D1'). Entitlement per client:
      • own client / own IB  -> from the FIRST trade (D1)
      • transferred from sales -> from D2 (2nd deposit); if D2 done but NO call was logged -> from D3
    Excludes credit trades from company markup. Filters: country/city/under-IB/one client.
    Groupable: clients (summary) | trades (rows) | daily | weekly | monthly."""
    import rbac
    vis = rbac.visible_agent_ids(db, current_user)
    if vis is not None and agent_id not in vis:
        raise HTTPException(status_code=403, detail="Not in your team")
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    P = {"id": agent_id, "f": day_lo(p_from), "tnext": day_hi(p_to)}

    fil = ""
    if country: fil += " AND c.country ILIKE :country"; P["country"] = country
    if city:    fil += " AND c.city ILIKE :city";       P["city"] = city
    if ib == "yes": fil += " AND EXISTS (SELECT 1 FROM ibs i WHERE i.agent_id=c.agent)"
    if ib == "no":  fil += " AND NOT EXISTS (SELECT 1 FROM ibs i WHERE i.agent_id=c.agent)"
    if client:  fil += " AND c.login = :one"; P["one"] = int(client)

    # per-login attribution: entitlement date (own/IB->'', transferred->D2, D2-but-no-call->D3)
    attr = db.execute(text(f"""
        WITH origin AS (
            SELECT DISTINCT ON (l.customer_no) l.customer_no, l.assigned_agent_id AS la
            FROM leads l WHERE l.customer_no IS NOT NULL AND l.assigned_agent_id IS NOT NULL
            ORDER BY l.customer_no, l.created_at, l.id),
        ibo AS (
            SELECT DISTINCT ON (c.login) c.login, ic.assigned_agent_id AS owner
            FROM clients c JOIN ibs i ON i.agent_id=c.agent JOIN clients ic ON ic.login=i.agent_id
            WHERE c.agent IS NOT NULL AND ic.assigned_agent_id IS NOT NULL ORDER BY c.login, i.id),
        dep AS (
            SELECT login, left((array_agg(tx_date ORDER BY tx_date))[2],10) AS d2,
                          left((array_agg(tx_date ORDER BY tx_date))[3],10) AS d3
            FROM transactions WHERE tx_type='deposit' AND COALESCE(tx_date,'')<>'' GROUP BY login)
        SELECT c.login, MIN(c.name), MIN(c.country), MIN(c.city),
               bool_or(i.agent_id IS NOT NULL) AS under_ib,
               (MIN(CASE WHEN origin.la=:id OR ibo.owner=:id THEN 1 ELSE 0 END)=1) AS own_or_ib,
               MIN(dep.d2) AS d2, MIN(dep.d3) AS d3,
               bool_or(ca.login IS NOT NULL) AS had_call
        FROM clients c
        LEFT JOIN origin ON origin.customer_no=c.customer_no
        LEFT JOIN ibo ON ibo.login=c.login
        LEFT JOIN dep ON dep.login=c.login
        LEFT JOIN ibs i ON i.agent_id=c.agent
        LEFT JOIN (SELECT DISTINCT login FROM call_actions WHERE agent_id=:id) ca ON ca.login=c.login
        WHERE c.assigned_agent_id=:id {fil}
        GROUP BY c.login
    """), P).fetchall()

    meta = {}
    for login, name, cty, city_, under_ib, own_or_ib, d2, d3, had_call in attr:
        if own_or_ib:
            earn_from = ""            # from the first trade
        elif d2:
            earn_from = d2 if had_call else (d3 or "9999-12-31")   # D2 if called, else D3
        else:
            earn_from = "9999-12-31"  # transferred, no 2nd deposit yet -> nothing counts
        meta[login] = {"name": name or "", "country": cty or "", "city": city_ or "",
                       "under_ib": bool(under_ib), "own_or_ib": bool(own_or_ib),
                       "d2": d2, "d3": d3, "had_call": bool(had_call), "earn_from": earn_from}
    if not meta:
        return {"period": {"from": p_from, "to": p_to}, "group": group, "rows": [], "totals": {}}

    logins = list(meta.keys())
    P["logins"] = logins
    # trades in period for these logins (exclude credit action 3/6; buy/sell only)
    trades = db.execute(text("""
        SELECT d.login, left(d.deal_date,10) AS dt, COALESCE(d.volume,0)/10000.0 AS lots,
               COALESCE(d.markup_profit,0)/10000.0 AS markup
        FROM deals d
        WHERE d.login = ANY(:logins) AND d.action IN (0,1) AND d.deal_date <> ''
          AND d.deal_date >= :f AND d.deal_date < :tnext
          AND NOT EXISTS (SELECT 1 FROM ib_trades cr WHERE cr.deal_id = d.deal_id AND cr.reason = 'credit')
        ORDER BY d.login, d.deal_date
    """), P).fetchall()
    # IB commission per login in period (for net profit)
    ibc_rows = db.execute(text("""
        SELECT ic.client_login, COALESCE(SUM(ic.commission_usd),0)
        FROM ib_commissions ic
        WHERE ic.client_login = ANY(:logins) AND ic.trade_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
          AND ic.trade_date >= :f AND ic.trade_date < :tnext GROUP BY ic.client_login
    """), P).fetchall()
    ibc_by = {r[0]: float(r[1]) for r in ibc_rows}

    def entitled(login, dt):
        return dt >= meta[login]["earn_from"]

    # ---- group: individual trade rows ----
    if group == "trades" or client:
        rows = []
        for login, dt, lots, markup in trades:
            m = meta[login]
            rows.append({"login": login, "name": m["name"], "date": dt,
                         "lots": round(lots, 2), "markup": round(markup, 2),
                         "entitled": entitled(login, dt),
                         "status": "counted" if entitled(login, dt) else "D1"})
        tot_e = sum(r["markup"] for r in rows if r["entitled"])
        return {"period": {"from": p_from, "to": p_to}, "group": "trades", "rows": rows,
                "totals": {"trades": len(rows), "entitled_markup": round(tot_e, 2)}}

    # ---- group: time buckets ----
    if group in ("daily", "weekly", "monthly"):
        from datetime import date as _d
        def bucket(dt):
            if group == "daily":  return dt
            if group == "monthly":return dt[:7]
            try:
                y, m, dd = map(int, dt.split("-")); wk = _d(y, m, dd).isocalendar()
                return f"{wk[0]}-W{wk[1]:02d}"
            except Exception: return dt
        agg = {}
        for login, dt, lots, markup in trades:
            b = bucket(dt); a = agg.setdefault(b, {"bucket": b, "lots": 0.0, "markup": 0.0, "d1_markup": 0.0, "trades": 0})
            a["trades"] += 1; a["lots"] += lots
            if entitled(login, dt): a["markup"] += markup
            else:                   a["d1_markup"] += markup
        for b in agg.values():
            b["ib_comm"] = 0.0  # IB comm isn't dated per bucket here
            b["net"] = round(b["markup"], 2); b["lots"] = round(b["lots"], 2)
            b["markup"] = round(b["markup"], 2); b["d1_markup"] = round(b["d1_markup"], 2)
        rows = sorted(agg.values(), key=lambda x: x["bucket"])
        return {"period": {"from": p_from, "to": p_to}, "group": group, "rows": rows,
                "totals": {"markup": round(sum(r["markup"] for r in rows), 2)}}

    # ---- default group: per-client summary ----
    per = {}
    for login, dt, lots, markup in trades:
        a = per.setdefault(login, {"lots": 0.0, "markup": 0.0, "d1_markup": 0.0, "trades": 0})
        a["trades"] += 1; a["lots"] += lots
        if entitled(login, dt): a["markup"] += markup
        else:                   a["d1_markup"] += markup
    rows = []
    for login, m in meta.items():
        a = per.get(login, {"lots": 0.0, "markup": 0.0, "d1_markup": 0.0, "trades": 0})
        ibc = ibc_by.get(login, 0.0)
        rows.append({
            "login": login, "name": m["name"], "country": m["country"], "city": m["city"],
            "under_ib": m["under_ib"], "own_or_ib": m["own_or_ib"], "d2": m["d2"],
            "had_call": m["had_call"], "earns_from": ("first trade" if m["own_or_ib"]
                       else ("D2 " + m["d2"] if (m["d2"] and m["had_call"]) else
                             ("D3 " + (m["d3"] or "—") if m["d2"] else "not yet (no D2)"))),
            "trades": a["trades"], "lots": round(a["lots"], 2),
            "markup": round(a["markup"], 2), "d1_markup": round(a["d1_markup"], 2),
            "ib_comm": round(ibc, 2), "net": round(a["markup"] - ibc, 2),
        })
    rows = [r for r in rows if r["trades"] > 0]
    rows.sort(key=lambda r: r["net"], reverse=True)
    totals = {
        "clients": len(rows), "lots": round(sum(r["lots"] for r in rows), 2),
        "markup": round(sum(r["markup"] for r in rows), 2),
        "d1_markup": round(sum(r["d1_markup"] for r in rows), 2),
        "ib_comm": round(sum(r["ib_comm"] for r in rows), 2),
        "net": round(sum(r["net"] for r in rows), 2),
    }
    return {"period": {"from": p_from, "to": p_to}, "group": "clients", "rows": rows, "totals": totals}


@router.get("/{agent_id}/sales-funnel")
def sales_funnel(agent_id: int, period: str = Query("this_month"),
                 date_from: str = Query(""), date_to: str = Query(""),
                 country: str = Query(""), city: str = Query(""),
                 source: str = Query(""), status: str = Query(""),   # status: won|verified|lost
                 db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """SALES funnel table: this agent's leads that DEPOSITED — how many calls before converting,
    and 'lost/no call' (deposited with ZERO calls = NOT a win). Plus verified leads. Filters."""
    import rbac
    vis = rbac.visible_agent_ids(db, current_user)
    if vis is not None and agent_id not in vis:
        raise HTTPException(status_code=403, detail="Not in your team")
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    P = {"id": agent_id, "f": day_lo(p_from), "tnext": day_hi(p_to)}
    fil = ""
    if country: fil += " AND l.country ILIKE :country"; P["country"] = country
    if city:    fil += " AND l.city ILIKE :city";       P["city"] = city
    if source:  fil += " AND COALESCE(l.source,'') ILIKE :source"; P["source"] = f"%{source}%"

    rows = db.execute(text(f"""
        WITH lead AS (
            SELECT l.id, l.full_name, l.country, l.city, l.source, l.customer_no,
                   l.kyc_status, l.campaign_name, l.created_at
            FROM leads l WHERE l.assigned_agent_id = :id {fil}
        ),
        conv AS (   -- the lead's customer + first deposit date/amount
            SELECT le.id AS lead_id, cl.login,
                   MIN(NULLIF(cl.first_deposit_at,'')) AS fda
            FROM lead le JOIN clients cl ON cl.customer_no = le.customer_no
            WHERE cl.customer_no IS NOT NULL GROUP BY le.id, cl.login
        )
        SELECT l.id, l.full_name, l.country, l.city, l.source, l.campaign_name,
               (l.kyc_status='verified') AS verified,
               (SELECT MIN(fda) FROM conv WHERE conv.lead_id=l.id) AS ftd_date,
               (SELECT COUNT(*) FROM call_actions ca
                  JOIN conv ON conv.lead_id=l.id AND ca.login=conv.login
                WHERE ca.agent_id=:id) AS calls,
               l.created_at AS reg_date
        FROM lead l
    """), P).fetchall()

    def short_name(n):   # first + second name only
        parts = (n or "").split()
        return " ".join(parts[:2]) if parts else ""

    out, won, lost, verified_n = [], 0, 0, 0
    for lid, name, cty, city_, src, camp, verified, ftd, calls, reg in rows:
        deposited = ftd is not None and P["f"] <= ftd < P["tnext"]
        calls = int(calls or 0)
        if deposited and calls == 0:
            st = "lost"; lost += 1          # deposited but never called -> not a win
        elif deposited:
            st = "won"; won += 1
        elif verified:
            st = "verified"; verified_n += 1
        else:
            st = "open"
        if status and st != status:
            continue
        if status or st in ("won", "lost", "verified"):
            out.append({"lead_id": lid, "name": short_name(name), "country": cty or "", "city": city_ or "",
                        "source": src or "", "campaign": camp or "", "verified": bool(verified),
                        "ftd_date": ftd[:16] if ftd else "", "calls": calls, "status": st,
                        "reg_date": (str(reg)[:10] if reg else "")})
    # sort: WON first, then LOST, then everything else — within each, newest registration first
    _rank = {"won": 0, "lost": 1}
    out.sort(key=lambda r: r["reg_date"], reverse=True)
    out.sort(key=lambda r: _rank.get(r["status"], 2))
    return {"period": {"from": p_from, "to": p_to}, "rows": out,
            "won": won, "lost": lost, "verified": verified_n}


@router.get("/{agent_id}")
def agent_detail(agent_id: int, period: str = Query("this_month"),
                 date_from: str = Query(""), date_to: str = Query(""),
                 db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    P = {"id": agent_id, "p_from": day_lo(p_from), "p_to": p_to, "p_to_next": day_hi(p_to)}
    u = db.execute(text("""
        SELECT full_name, role, title, team_type, COALESCE(commission_pct,10), COALESCE(sales_target,0),
               extension, department, email
        FROM users WHERE id=:id
    """), {"id": agent_id}).fetchone()
    if not u:
        return {"error": "agent not found"}

    # role scope: an agent may only open their own detail; leaders their team; admins anyone
    import rbac
    vis = rbac.visible_agent_ids(db, current_user)
    if vis is not None and agent_id not in vis:
        raise HTTPException(status_code=403, detail="Not in your team")

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
    own_added = scalar("SELECT COUNT(*) FROM leads WHERE assigned_agent_id=:id AND source IN ('sales_agent','manual')")
    converted = scalar("""
        SELECT COUNT(*) FROM (
          SELECT DISTINCT ON (l.customer_no) l.customer_no, l.assigned_agent_id AS la
          FROM leads l WHERE l.customer_no IS NOT NULL AND l.assigned_agent_id IS NOT NULL
          ORDER BY l.customer_no, l.created_at, l.id) o
        JOIN (SELECT customer_no, MIN(NULLIF(first_deposit_at,'')) AS fda
              FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no) f
          ON f.customer_no = o.customer_no
        WHERE o.la = :id AND f.fda >= :p_from AND f.fda < :p_to_next""")
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
    net_comm = markup - ib_comm          # COMPANY net on the agent's whole book (display only)

    # agent's ACTUAL earning per the desk's rules (unit bonus + scoped/gated markup commission)
    unit = CFG.get_float(db, "sales_unit_usd", 10.0)
    try:
        cc = SC.compute(db, P["p_from"], P["p_to_next"], unit, only_aid=agent_id).get(agent_id) or {}
    except Exception:
        cc = {}
    unit_nda   = cc.get("nda_ftd", 0)
    unit_bonus = cc.get("unit_bonus", 0.0)
    markup_commission = cc.get("markup_comm", 0.0)
    sales_comm = cc.get("commission", 0.0)
    # item #6: Company markup / IB / Net shown = the ENTITLED (gated) basis, not the raw book
    if cc:
        markup   = cc.get("gross_markup", markup)
        ib_comm  = cc.get("comm_ib", ib_comm)
        net_comm = cc.get("net_markup", net_comm)
    # performance score + eligible commission
    try:
        import sales_performance as SP
        pp = SP.perf(db, agent_id, u[3] or "", period, P["p_from"], P["p_to_next"])
    except Exception:
        pp = {}
    performance = pp.get("score", 0.0)
    eligible_commission = round(sales_comm * performance / 100.0, 2)

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
            "own_leads": own_leads, "own_added": own_added, "converted": converted,
            "ibs": ibs, "active_ibs": active_ibs, "calls": calls,
            "deposits": float(deposits), "withdrawals": float(withdrawals),
            "net_deposit": float(deposits) - float(withdrawals), "lots": lots,
            "markup": markup, "ib_commission": ib_comm, "net_commission": net_comm,
            "sales_commission": sales_comm,
            "unit_rate": unit, "unit_nda": unit_nda, "unit_bonus": unit_bonus,
            "markup_commission": markup_commission,
            "performance": performance, "perf_demo": pp.get("demo", False),
            "perf_breakdown": pp.get("breakdown", []), "perf_metrics": pp.get("metrics", {}),
            "eligible_commission": eligible_commission,
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
    _require_mgmt(current_user)
    sets, params = [], {"id": agent_id}
    _old = db.execute(text("SELECT commission_pct, sales_target FROM users WHERE id=:id"),
                      {"id": agent_id}).fetchone()
    if "commission_pct" in data and data["commission_pct"] is not None:
        sets.append("commission_pct=:pct"); params["pct"] = float(data["commission_pct"])
    if "sales_target" in data and data["sales_target"] is not None:
        sets.append("sales_target=:tgt"); params["tgt"] = float(data["sales_target"])
    if not sets:
        return {"ok": False, "error": "nothing to update"}
    db.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id=:id"), params)
    db.commit()
    import audit
    audit.log(db, current_user, "commission_rate_change", "user", agent_id,
              old=f"pct={_old[0] if _old else None},target={_old[1] if _old else None}",
              new=f"pct={params.get('pct','-')},target={params.get('tgt','-')}")
    return {"ok": True}


# ── NDA KPI ─────────────────────────────────────────────────────────────────
# NDA = "New Deposit Account": a customer who made an FTD and has NO relation to any other TNFX
# customer (genuine acquisition). is_nda is set by nda_engine.py. This KPI surfaces total NDA and
# each sales agent's NDA rate — a LOW rate means their "new" accounts are mostly family/friends.
@router.get("/nda")
def nda_kpi(period: str = Query("all"), db: Session = Depends(get_db),
            current_user: models.User = Depends(get_current_user)):
    # period window on first_deposit_at (the FTD date)
    dr = ""
    if period == "month":
        dr = "AND c.first_deposit_at >= date_trunc('month', NOW())"
    elif period == "year":
        dr = "AND c.first_deposit_at >= date_trunc('year', NOW())"
    elif period == "last30":
        dr = "AND c.first_deposit_at >= NOW() - INTERVAL '30 days'"

    tot = db.execute(text(f"""
        SELECT COUNT(*) FILTER (WHERE is_nda) AS nda,
               COUNT(*) FILTER (WHERE is_nda IS NOT NULL) AS deposited
        FROM (SELECT DISTINCT ON (c.customer_no) c.customer_no, c.is_nda
              FROM clients c WHERE c.customer_no IS NOT NULL AND c.is_nda IS NOT NULL {dr}) t
    """)).fetchone()
    nda, deposited = tot[0] or 0, tot[1] or 0

    rows = db.execute(text(f"""
        SELECT u.full_name, u.id,
               COUNT(*) AS deposited,
               COUNT(*) FILTER (WHERE t.is_nda) AS nda
        FROM (SELECT DISTINCT ON (c.customer_no) c.customer_no, c.assigned_agent_id, c.is_nda
              FROM clients c WHERE c.customer_no IS NOT NULL AND c.is_nda IS NOT NULL
                AND c.assigned_agent_id IS NOT NULL {dr}) t
        JOIN users u ON u.id = t.assigned_agent_id
        GROUP BY u.full_name, u.id HAVING COUNT(*) >= 5
        ORDER BY (COUNT(*) FILTER (WHERE t.is_nda))::float / COUNT(*) ASC
    """)).fetchall()
    agents = [{"agent": r[0] or f"#{r[1]}", "agent_id": r[1], "deposited": r[2], "nda": r[3],
               "nda_pct": round(100 * r[3] / r[2]) if r[2] else 0} for r in rows]
    return {
        "total_deposited": deposited, "total_nda": nda,
        "nda_pct": round(100 * nda / deposited) if deposited else 0,
        "related": deposited - nda,
        "agents": agents,   # sorted worst NDA% first (most family/friend accounts)
    }
