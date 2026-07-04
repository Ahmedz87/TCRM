# -*- coding: utf-8 -*-
"""
report_builder.py — generic, filterable report engine behind the Monthly Report page tabs.

Each "category" (validation / leads / clients / ib / deposit / withdraw / sales) is described
by a CONFIG (from-clause, date column, group-by dimension expressions, metrics, and a
predicate-per-option filter map). run_report() turns a category + chosen options into
{columns, rows, total_row}.

MULTI-SELECT semantics (all whitelisted — user input is never concatenated as SQL):
  • group_by  : a LIST of dimensions → composite grouping, one leading column per dimension
                (e.g. ["country","month"] → Country | Month | metrics…). "none" alone = a
                single Total row.
  • filters   : each filter is a LIST of option keys → the chosen options are OR'd together
                (value-list = IN; predicate options = OR of predicates). "all"/empty = no
                filter on that key. Different filters are AND'd.
  • period    : single range (presets or custom) — a time window can't be multi-valued.

Definitions follow the rest of the CRM: deposit truth from transactions; leads verified =
leads.is_verified; an account "has an IB" when clients.agent (the MT agent/IB login) is set
(clients.ib_id is unused/NULL). tx_date / reg_date are ISO VARCHAR (lexical compare / left()).
"""
from datetime import date, timedelta
from sqlalchemy import text

T_TEXT, T_INT, T_MONEY, T_FLOAT, T_PCT = "text", "int", "money", "float", "pct"
_KYC_PENDING = "('pending','pending_review','pending_admin_review','docs_needed')"


def period_to_dates(period, start=None, end=None):
    """Return (sd, ed) as ISO strings, ed EXCLUSIVE. (None, None) = no date filter."""
    today = date.today()
    if period == "custom" and start:
        e = date.fromisoformat(end) if end else today
        return start, (e + timedelta(days=1)).isoformat()
    if period == "this_month":
        s = today.replace(day=1); return s.isoformat(), (today + timedelta(days=1)).isoformat()
    if period == "last_month":
        first = today.replace(day=1); s = (first - timedelta(days=1)).replace(day=1)
        return s.isoformat(), first.isoformat()
    if period == "last_3m":
        s = (today.replace(day=1) - timedelta(days=62)).replace(day=1)
        return s.isoformat(), (today + timedelta(days=1)).isoformat()
    if period == "last_6m":
        s = (today.replace(day=1) - timedelta(days=160)).replace(day=1)
        return s.isoformat(), (today + timedelta(days=1)).isoformat()
    if period == "this_year":
        return f"{today.year}-01-01", (today + timedelta(days=1)).isoformat()
    if period == "last_year":
        return f"{today.year-1}-01-01", f"{today.year}-01-01"
    return None, None  # all_time


PERIOD_OPTS = [
    ["this_month", "This month"], ["last_month", "Last month"],
    ["last_3m", "Last 3 months"], ["last_6m", "Last 6 months"],
    ["this_year", "This year"], ["last_year", "Last year"],
    ["all_time", "All time"], ["custom", "Custom range"],
]

# ── dimension SQL (whitelisted) ───────────────────────────────────────────────
CLIENTS_DIM = {
    "none": "'Total'", "month": "left(reg_date,7)",
    "country": "coalesce(nullif(country,''),'(unknown)')",
    "city": "coalesce(nullif(city,''),'(unknown)')",
    "platform": "case when platform='MT4' then 'MT4' else 'MT5' end",
}
LEADS_DIM = {
    "none": "'Total'", "month": "to_char(created_at,'YYYY-MM')",
    "country": "coalesce(nullif(country,''),'(unknown)')",
    "city": "coalesce(nullif(city,''),'(unknown)')",
    "source": "coalesce(nullif(source,''),'(unknown)')",
    "campaign": "coalesce(nullif(campaign_name,''),'(none)')",
}
IB_DIM = {
    "none": "'Total'", "level": "'LVL '||coalesce(ib_level::text,'?')",
    "country": "coalesce(nullif(country,''),'(unknown)')",
    "city": "coalesce(nullif(city,''),'(unknown)')",
}
TXN_DIM = {
    "none": "'Total'", "month": "left(t.tx_date,7)",  # tx_date is ISO varchar
    "method": "coalesce(nullif(t.method,''),'(none)')",
    "country": "coalesce(nullif(c.country,''),'(unknown)')",
}

# ── per-category config ───────────────────────────────────────────────────────
# metrics: list of (sql_expr, key, label, type[, no_total])
CONFIG = {
    "validation": {
        "title": "Validation / Registrations", "date_label": "by registration date",
        "from": "clients", "date_col": "reg_date", "dim": CLIENTS_DIM,
        "group_by": [["month", "Month"], ["none", "Total"], ["country", "Country"], ["city", "City"], ["platform", "Platform"]],
        "metrics": [
            ("count(*)", "reg", "Reg. accounts", T_INT),
            ("count(*) FILTER (WHERE kyc_status='verified')", "verified", "Verified", T_INT),
            (f"count(*) FILTER (WHERE kyc_status IN {_KYC_PENDING})", "pending", "KYC pending", T_INT),
            ("count(*) FILTER (WHERE kyc_status IS NULL OR kyc_status='exists')", "no_kyc", "No KYC", T_INT),
        ],
        "order": "reg",
        "filters": [
            {"key": "kyc", "label": "KYC status", "opts": [["all", "All"], ["verified", "Verified"], ["pending", "KYC pending"], ["no_kyc", "No KYC"]],
             "pred": {"verified": "kyc_status='verified'", "pending": f"kyc_status IN {_KYC_PENDING}", "no_kyc": "(kyc_status IS NULL OR kyc_status='exists')"}},
            {"key": "platform", "label": "Platform", "opts": [["all", "All"], ["MT4", "MT4"], ["MT5", "MT5"]],
             "pred": {"MT4": "platform='MT4'", "MT5": "(platform IS NULL OR platform<>'MT4')"}},
        ],
    },
    "leads": {
        "title": "Leads", "date_label": "by created date",
        "from": "leads", "date_col": "created_at", "dim": LEADS_DIM,
        "group_by": [["none", "Total"], ["month", "Month"], ["country", "Country"], ["city", "City"], ["source", "Source"], ["campaign", "Campaign"]],
        "metrics": [
            ("count(*)", "total", "Total leads", T_INT),
            ("count(*) FILTER (WHERE is_verified IS TRUE)", "verified", "Verified", T_INT),
            ("count(*) FILTER (WHERE phone_verified IS TRUE)", "phone_v", "Phone verified", T_INT),
            ("count(*) FILTER (WHERE email_verified IS TRUE)", "email_v", "Email verified", T_INT),
            ("count(*) FILTER (WHERE matched_login IS NOT NULL)", "matched", "Matched", T_INT),
            ("count(*) FILTER (WHERE converted_login IS NOT NULL)", "converted", "Converted", T_INT),
        ],
        "order": "total",
        "filters": [
            {"key": "status", "label": "Lead filter", "opts": [["all", "All leads"], ["verified", "Verified"], ["phone_verified", "Phone verified"], ["email_verified", "Email verified"], ["unverified", "Unverified"], ["matched", "Matched"], ["converted", "Converted"]],
             "pred": {"verified": "is_verified IS TRUE", "phone_verified": "phone_verified IS TRUE", "email_verified": "email_verified IS TRUE", "unverified": "coalesce(is_verified,false)=false", "matched": "matched_login IS NOT NULL", "converted": "converted_login IS NOT NULL"}},
            {"key": "source", "label": "Source", "opts": [["all", "All sources"], ["facebook", "Facebook"], ["instagram", "Instagram"], ["tradesoft", "TradeSoft (legacy)"], ["registration", "Registration"]],
             "pred": {"facebook": "source='facebook'", "instagram": "source='instagram'", "tradesoft": "source='tradesoft'", "registration": "source='registration'"}},
        ],
    },
    "clients": {
        "title": "Clients", "date_label": "by registration date",
        "from": "clients", "date_col": "reg_date", "dim": CLIENTS_DIM,
        "group_by": [["none", "Total"], ["month", "Month"], ["country", "Country"], ["city", "City"], ["platform", "Platform"]],
        "metrics": [
            ("count(*)", "clients", "Clients", T_INT),
            ("count(*) FILTER (WHERE kyc_status='verified')", "verified", "Verified", T_INT),
            ("count(*) FILTER (WHERE coalesce(total_deposits,0)>0)", "depositing", "Depositing", T_INT),
            ("coalesce(sum(total_deposits),0)", "deposits", "Total deposits", T_MONEY),
            ("coalesce(sum(total_withdrawals),0)", "withdrawals", "Total withdrawals", T_MONEY),
            ("coalesce(sum(total_deposits),0)-coalesce(sum(total_withdrawals),0)", "net", "Net deposits", T_MONEY),
        ],
        "order": "clients",
        "filters": [
            {"key": "platform", "label": "Platform", "opts": [["all", "All"], ["MT4", "MT4"], ["MT5", "MT5"]],
             "pred": {"MT4": "platform='MT4'", "MT5": "(platform IS NULL OR platform<>'MT4')"}},
            {"key": "kyc", "label": "KYC status", "opts": [["all", "All"], ["verified", "Verified"], ["pending", "Pending"], ["no_kyc", "No KYC"]],
             "pred": {"verified": "kyc_status='verified'", "pending": f"kyc_status IN {_KYC_PENDING}", "no_kyc": "(kyc_status IS NULL OR kyc_status='exists')"}},
            {"key": "deposit", "label": "Deposit", "opts": [["all", "All"], ["deposited", "Has deposited"], ["no_deposit", "Never deposited"]],
             "pred": {"deposited": "coalesce(total_deposits,0)>0", "no_deposit": "coalesce(total_deposits,0)=0"}},
            {"key": "ib", "label": "IB", "opts": [["all", "All"], ["with_ib", "With IB"], ["without_ib", "Without IB"]],
             "pred": {"with_ib": "coalesce(agent,0)>0", "without_ib": "coalesce(agent,0)=0"}},
        ],
    },
    "ib": {
        "title": "IB / Partners", "date_label": "by IB registration date",
        "from": "ibs", "date_col": "created_at", "dim": IB_DIM,
        "group_by": [["none", "Total"], ["level", "IB level"], ["country", "Country"], ["city", "City"]],
        "metrics": [
            ("count(*)", "ibs", "IBs", T_INT),
            ("count(*) FILTER (WHERE coalesce(total_clients,0)>0)", "with_clients", "With clients", T_INT),
            ("coalesce(sum(total_clients),0)", "total_clients", "Total clients", T_INT),
            ("coalesce(sum(active_clients),0)", "active_clients", "Active clients", T_INT),
            ("coalesce(sum(total_volume),0)", "volume", "Volume (lots)", T_FLOAT),
            ("coalesce(sum(total_commission),0)", "commission", "Commission $", T_MONEY),
            ("coalesce(sum(net_deposits),0)", "net_deposits", "Net deposits $", T_MONEY),
        ],
        "order": "commission",
        "filters": [
            {"key": "clients", "label": "Clients", "opts": [["all", "All"], ["with_clients", "With clients (≥1)"], ["without_clients", "Without clients (0)"]],
             "pred": {"with_clients": "coalesce(total_clients,0)>0", "without_clients": "coalesce(total_clients,0)=0"}},
            {"key": "level", "label": "Level", "opts": [["all", "All"], ["5", "LVL 5"], ["6", "LVL 6"], ["7", "LVL 7"], ["8", "LVL 8"], ["9", "LVL 9"], ["10", "LVL 10"]],
             "pred": {"5": "ib_level=5", "6": "ib_level=6", "7": "ib_level=7", "8": "ib_level=8", "9": "ib_level=9", "10": "ib_level=10"}},
        ],
    },
    "deposit": {
        "title": "Transactions — Deposits", "date_label": "by transaction date",
        "from": "transactions t LEFT JOIN clients c ON c.login = t.login", "date_col": "t.tx_date", "dim": TXN_DIM,
        "base_where": ["t.tx_type='deposit'"],
        "group_by": [["month", "Month"], ["none", "Total"], ["method", "Method"], ["country", "Country"]],
        "metrics": [
            ("count(*)", "cnt", "Deposit count", T_INT),
            ("count(DISTINCT t.login)", "clients", "Clients", T_INT),
            ("coalesce(sum(abs(t.amount)),0)", "total", "Total deposits $", T_MONEY),
            ("coalesce(avg(abs(t.amount)),0)", "avg_amt", "Avg amount $", T_MONEY, True),
        ],
        "order": "total",
        "filters": [
            {"key": "ib", "label": "IB", "opts": [["all", "All"], ["with_ib", "With IB"], ["without_ib", "Without IB"]],
             "pred": {"with_ib": "coalesce(c.agent,0)>0", "without_ib": "coalesce(c.agent,0)=0"}},
            {"key": "method", "label": "Method", "opts": [["all", "All methods"], ["Qi card", "Qi card"], ["Zaincash", "Zaincash"], ["Tether | USDT", "USDT"], ["Perfect Money", "Perfect Money"], ["Wallet Cash", "Wallet Cash"], ["MT5", "MT5 (internal)"]],
             "pred": {"Qi card": "t.method='Qi card'", "Zaincash": "t.method='Zaincash'", "Tether | USDT": "t.method='Tether | USDT'", "Perfect Money": "t.method='Perfect Money'", "Wallet Cash": "t.method='Wallet Cash'", "MT5": "t.method='MT5'"}},
        ],
    },
    "withdraw": {
        "title": "Transactions — Withdrawals", "date_label": "by transaction date",
        "from": "transactions t LEFT JOIN clients c ON c.login = t.login", "date_col": "t.tx_date", "dim": TXN_DIM,
        "base_where": ["t.tx_type='withdrawal'"],
        "group_by": [["month", "Month"], ["none", "Total"], ["method", "Method"], ["country", "Country"]],
        "metrics": [
            ("count(*)", "cnt", "Withdrawal count", T_INT),
            ("count(DISTINCT t.login)", "clients", "Clients", T_INT),
            ("coalesce(sum(abs(t.amount)),0)", "total", "Total withdrawals $", T_MONEY),
            ("coalesce(avg(abs(t.amount)),0)", "avg_amt", "Avg amount $", T_MONEY, True),
        ],
        "order": "total",
        "filters": [
            {"key": "ib", "label": "IB", "opts": [["all", "All"], ["with_ib", "With IB"], ["without_ib", "Without IB"]],
             "pred": {"with_ib": "coalesce(c.agent,0)>0", "without_ib": "coalesce(c.agent,0)=0"}},
            {"key": "method", "label": "Method", "opts": [["all", "All methods"], ["Qi card", "Qi card"], ["Zaincash", "Zaincash"], ["USDT", "USDT"], ["TB", "Bank (TB)"]],
             "pred": {"Qi card": "t.method='Qi card'", "Zaincash": "t.method='Zaincash'", "USDT": "t.method='USDT'", "TB": "t.method='TB'"}},
        ],
    },
}

# ── schema for the UI (adds multi flags + period list) ────────────────────────
def get_schema(db=None):
    out = {}
    for k, cfg in CONFIG.items():
        out[k] = {
            "key": k, "title": cfg["title"], "date_label": cfg["date_label"],
            "periods": PERIOD_OPTS, "group_by": cfg["group_by"], "multi_group": True,
            "filters": [{"key": f["key"], "label": f["label"], "opts": f["opts"], "multi": True} for f in cfg["filters"]],
        }
    # sales (special — CTE based, single group dimension). Team + country lists are LIVE from the DB.
    teams, countries = [], []
    if db is not None:
        try:
            tr = db.execute(text(
                "SELECT id, full_name FROM users "
                "WHERE (title ILIKE '%team leader%' OR role='sales_manager') AND COALESCE(is_active,TRUE) "
                "ORDER BY full_name")).fetchall()
            teams = [[str(r[0]), r[1] or f"#{r[0]}"] for r in tr]
        except Exception:
            pass
        try:
            cr = db.execute(text(
                "SELECT country, count(*) n FROM clients "
                "WHERE country IS NOT NULL AND country<>'' GROUP BY country ORDER BY n DESC LIMIT 80")).fetchall()
            countries = [[r[0], r[0]] for r in cr]
        except Exception:
            pass
    out["sales"] = {
        "key": "sales", "title": "Sales agents",
        "date_label": "deposits & commission in the period; Own NDA / New IB registered in the period",
        "periods": PERIOD_OPTS, "group_by": [["agent", "Sales agent"]], "multi_group": False,
        "filters": [
            {"key": "team", "label": "Team (leader)", "multi": True, "opts": teams},
            {"key": "country", "label": "Country", "multi": True, "opts": countries},
            {"key": "ib", "label": "IB", "multi": True,
             "opts": [["under_ib", "Under IB"], ["not_under_ib", "Not under IB"]]},
            {"key": "role", "label": "Role", "multi": True,
             "opts": [["sales_agent", "Agents"], ["sales_manager", "Managers"]]},
        ],
    }
    return out


# ── helpers ───────────────────────────────────────────────────────────────────
def _as_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v else []
    return list(v)


def _build_filter_where(cfg, filters, params):
    """AND across filters; OR across the selected options within one filter."""
    where = []
    for f in cfg["filters"]:
        sel = [s for s in _as_list(filters.get(f["key"])) if s in f["pred"]]
        if not sel:
            continue  # 'all' / empty → no constraint
        ors = [f["pred"][s] for s in sel]
        where.append("(" + " OR ".join(ors) + ")")
    return where


def _resolve_group_dims(cfg, group_by):
    valid = cfg["dim"]
    dims = [d for d in _as_list(group_by) if d in valid]
    dims = [d for d in dims if d != "none"] or (dims and ["none"]) or [cfg["group_by"][0][0]]
    if len(dims) > 1:
        dims = [d for d in dims if d != "none"]  # drop the meaningless Total when grouping
    return dims or ["none"]


def _dim_label(cfg, key):
    for k, label in cfg["group_by"]:
        if k == key:
            return label
    return key.title()


def run_report(db, category, params):
    if category == "sales":
        return _run_sales(db, params)
    if category not in CONFIG:
        raise ValueError("unknown category")
    cfg = CONFIG[category]
    sd, ed = period_to_dates(params.get("period", "all_time"), params.get("start"), params.get("end"))
    filters = params.get("filters") or {}
    group_dims = _resolve_group_dims(cfg, params.get("group_by"))

    where = list(cfg.get("base_where", []))
    sqlp = {}
    if sd:
        col = cfg["date_col"]
        where.append(f"{col} >= :sd AND {col} < :ed"); sqlp.update(sd=sd, ed=ed)
    where += _build_filter_where(cfg, filters, sqlp)
    where_sql = " AND ".join(where) if where else "1=1"

    # SELECT dims + metrics
    dim_exprs = [f"{cfg['dim'][d]} AS dim_{i}" for i, d in enumerate(group_dims)]
    metric_exprs = [f"{m[0]} AS {m[1]}" for m in cfg["metrics"]]
    select_sql = ", ".join(dim_exprs + metric_exprs)
    n_dims = len(group_dims)
    group_sql = ", ".join(str(i + 1) for i in range(n_dims))
    if "month" in group_dims:
        order_sql = ", ".join(str(i + 1) for i in range(n_dims))  # chronological-ish
    else:
        order_sql = f"{cfg['order']} DESC NULLS LAST"

    sql = f"SELECT {select_sql} FROM {cfg['from']} WHERE {where_sql} GROUP BY {group_sql} ORDER BY {order_sql} LIMIT 500"
    rows = [list(r) for r in db.execute(text(sql), sqlp).fetchall()]

    columns = [{"key": f"dim_{i}", "label": _dim_label(cfg, d), "type": T_TEXT} for i, d in enumerate(group_dims)]
    for m in cfg["metrics"]:
        columns.append({"key": m[1], "label": m[2], "type": m[3], **({"no_total": True} if len(m) > 4 and m[4] else {})})

    return _result(category, cfg["title"], columns, rows, n_dims, sd, ed, params.get("period", "all_time"), group_dims)


def _run_sales(db, params):
    """Per-sales-agent report. Reuses the SalesAgents-page definitions (commission =
    markup_profit/10000; IB commission = ib_commissions.commission_usd; new IB = IB whose
    client registered in period). Adds deposit tiers D1/D2/D3 (customers with >=1/2/3 deposits
    in the period), Own NDA (customers whose FIRST-ever deposit falls in the period), and
    team / country / under-IB filters."""
    sd, ed = period_to_dates(params.get("period", "this_month"), params.get("start"), params.get("end"))
    f = params.get("filters") or {}
    sp = {}
    tx_in = reg_in = deal_in = ic_in = ""
    fd_in = "TRUE"
    if sd:
        sp.update(sd=sd, ed=ed)
        tx_in = "AND t.tx_date >= :sd AND t.tx_date < :ed"
        reg_in = "AND c.reg_date >= :sd AND c.reg_date < :ed"
        deal_in = "AND d.deal_date >= :sd AND d.deal_date < :ed"
        ic_in = "AND ic.trade_date >= :sd AND ic.trade_date < :ed"
        fd_in = "z.fd >= :sd AND z.fd < :ed"

    # who counts as sales team (same predicate as the Sales Agents page)
    where = ("((u.role IN ('sales_agent','sales_manager') OR u.title ILIKE '%team leader%') "
             "AND u.full_name NOT ILIKE '%narmeen%')")
    roles = [r for r in _as_list(f.get("role")) if r in ("sales_agent", "sales_manager")]
    if roles:
        where += " AND u.role IN :roles"; sp["roles"] = tuple(roles)
    teams = [int(t) for t in _as_list(f.get("team")) if str(t).isdigit()]
    if teams:
        where += " AND (u.id IN :teams OR u.manager_id IN :teams)"; sp["teams"] = tuple(teams)

    # client-scope filters applied INSIDE every client-joined CTE (country + under-IB)
    cflt = ""
    countries = [x for x in _as_list(f.get("country")) if x]
    if countries:
        cflt += " AND c.country = ANY(:countries)"; sp["countries"] = countries
    ib_sel = _as_list(f.get("ib"))
    if "under_ib" in ib_sel and "not_under_ib" not in ib_sel:
        cflt += " AND COALESCE(c.agent,0) > 0"
    elif "not_under_ib" in ib_sel and "under_ib" not in ib_sel:
        cflt += " AND COALESCE(c.agent,0) = 0"

    sql = f"""
        WITH ag AS (
            SELECT u.id, u.full_name, COALESCE(u.commission_pct,10) AS pct
            FROM users u WHERE {where}
        ),
        cl AS (
            SELECT c.assigned_agent_id aid, COUNT(DISTINCT c.customer_no) clients
            FROM clients c WHERE c.assigned_agent_id IS NOT NULL {cflt}
            GROUP BY c.assigned_agent_id
        ),
        tiers AS (
            SELECT aid,
                   COUNT(*) FILTER (WHERE ndep>=1) d1,
                   COUNT(*) FILTER (WHERE ndep>=2) d2,
                   COUNT(*) FILTER (WHERE ndep>=3) d3
            FROM (
                SELECT c.assigned_agent_id aid, c.customer_no, COUNT(*) ndep
                FROM clients c JOIN transactions t ON t.login=c.login AND t.tx_type='deposit' {tx_in}
                WHERE c.assigned_agent_id IS NOT NULL {cflt}
                GROUP BY c.assigned_agent_id, c.customer_no
            ) z GROUP BY aid
        ),
        nda AS (
            SELECT aid, COUNT(*) own_nda FROM (
                SELECT c.assigned_agent_id aid, c.customer_no, MIN(t.tx_date) fd
                FROM clients c JOIN transactions t ON t.login=c.login AND t.tx_type='deposit'
                WHERE c.assigned_agent_id IS NOT NULL {cflt}
                GROUP BY c.assigned_agent_id, c.customer_no
            ) z WHERE {fd_in} GROUP BY aid
        ),
        ib AS (
            SELECT c.assigned_agent_id aid,
                   COUNT(DISTINCT i.id) FILTER (WHERE TRUE {reg_in}) new_ibs
            FROM ibs i JOIN clients c ON c.login=i.agent_id
            WHERE c.assigned_agent_id IS NOT NULL {cflt}
            GROUP BY c.assigned_agent_id
        ),
        mn AS (
            SELECT c.assigned_agent_id aid,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='deposit'),0) dep,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='withdrawal' AND COALESCE(t.status,'')<>'rejected'),0) wd
            FROM clients c JOIN transactions t ON t.login=c.login
            WHERE c.assigned_agent_id IS NOT NULL {cflt} {tx_in}
            GROUP BY c.assigned_agent_id
        ),
        comm AS (
            SELECT c.assigned_agent_id aid, COALESCE(SUM(d.markup_profit),0)/10000.0 markup
            FROM clients c JOIN deals d ON d.login=c.login
            WHERE c.assigned_agent_id IS NOT NULL AND d.action IN (0,1) {cflt} {deal_in}
            GROUP BY c.assigned_agent_id
        ),
        ibc AS (
            SELECT c.assigned_agent_id aid, COALESCE(SUM(ic.commission_usd),0) ib_comm
            FROM clients c JOIN ib_commissions ic ON ic.client_login=c.login
            WHERE c.assigned_agent_id IS NOT NULL {cflt} {ic_in}
            GROUP BY c.assigned_agent_id
        )
        SELECT ag.full_name AS dim_0,
               COALESCE(cl.clients,0)     AS clients,
               COALESCE(tiers.d1,0)       AS d1,
               COALESCE(tiers.d2,0)       AS d2,
               COALESCE(tiers.d3,0)       AS d3,
               COALESCE(mn.dep,0)         AS deposits,
               COALESCE(nda.own_nda,0)    AS own_nda,
               COALESCE(ib.new_ibs,0)     AS new_ibs,
               COALESCE(mn.wd,0)          AS withdrawals,
               COALESCE(mn.dep,0)-COALESCE(mn.wd,0) AS net,
               GREATEST(COALESCE(comm.markup,0)-COALESCE(ibc.ib_comm,0),0)*ag.pct/100.0 AS sales_comm,
               COALESCE(ibc.ib_comm,0)    AS ib_comm
        FROM ag
        LEFT JOIN cl    ON cl.aid=ag.id
        LEFT JOIN tiers ON tiers.aid=ag.id
        LEFT JOIN nda   ON nda.aid=ag.id
        LEFT JOIN ib    ON ib.aid=ag.id
        LEFT JOIN mn    ON mn.aid=ag.id
        LEFT JOIN comm  ON comm.aid=ag.id
        LEFT JOIN ibc   ON ibc.aid=ag.id
        ORDER BY deposits DESC NULLS LAST LIMIT 500"""
    rows = [list(r) for r in db.execute(text(sql), sp).fetchall()]
    columns = [
        {"key": "dim_0", "label": "Sales agent", "type": T_TEXT},
        {"key": "clients", "label": "Total clients", "type": T_INT},
        {"key": "d1", "label": "D1 (≥1 dep)", "type": T_INT},
        {"key": "d2", "label": "D2 (≥2 dep)", "type": T_INT},
        {"key": "d3", "label": "D3 (≥3 dep)", "type": T_INT},
        {"key": "deposits", "label": "Total deposits $", "type": T_MONEY},
        {"key": "own_nda", "label": "Own NDA", "type": T_INT},
        {"key": "new_ibs", "label": "New IB", "type": T_INT},
        {"key": "withdrawals", "label": "Total withdrawals $", "type": T_MONEY},
        {"key": "net", "label": "Net deposit $", "type": T_MONEY},
        {"key": "sales_comm", "label": "Sales commission $", "type": T_MONEY},
        {"key": "ib_comm", "label": "IB commission $", "type": T_MONEY},
    ]
    return _result("sales", "Sales agents", columns, rows, 1, sd, ed, params.get("period", "this_month"), ["agent"])


def _result(category, title, columns, rows, n_dims, sd, ed, preset, group_dims):
    total = None
    if rows:
        total = ["TOTAL"] + [None] * (n_dims - 1)
        for ci in range(n_dims, len(columns)):
            col = columns[ci]
            if col["type"] in (T_INT, T_MONEY, T_FLOAT) and not col.get("no_total"):
                total.append(sum((r[ci] or 0) for r in rows))
            else:
                total.append(None)
    return {
        "category": category, "title": title, "columns": columns, "rows": rows,
        "total_row": total, "n_dims": n_dims,
        "period": {"start": sd, "end": ed, "preset": preset}, "group_by": group_dims,
    }
