"""TradeSoft CRM (standalone copy) — FastAPI backend.

A faithful, READ-ONLY rebuild of the legacy Workice/TradeSoft CRM, served from a
decoupled copy of its data (the `tradesoft_crm` database). No connection to the
live broker_crm system. Entities: Clients, Leads, Accounts, Transactions, Users.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from db import query_all, query_one

app = FastAPI(title="TradeSoft CRM (copy)", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# A SQL fragment that safely casts a TEXT column to numeric (raw mirror = all TEXT).
def num(col):
    return f"(CASE WHEN {col} ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN {col}::numeric ELSE 0 END)"


# ---------------------------------------------------------------- entity config
ENTITIES = {
    "clients": {
        "table": "fx_clients_view c",
        "live_filter": "c.deleted_at IS NULL",
        "select": f"""
            c.id, c.code, c.name, c.individual, c.country, c.city, c.state,
            c.currency, {num('c.balance')} AS balance, {num('c.expense')} AS expense,
            {num('c.paid')} AS paid, c.created_at, c.archived_at, c.user_id,
            o.name AS owner_name, c.owner, ce.email, ce.phone
        """,
        "joins": "LEFT JOIN fx_users_view o ON o.id = c.owner "
                 "LEFT JOIN contact_enrichment ce ON ce.user_id = c.user_id",
        "search": ["c.name", "c.code", "c.city", "c.country", "ce.email", "ce.phone"],
        "sort": {"name": "c.name", "code": "c.code", "balance": num("c.balance"),
                 "expense": num("c.expense"), "paid": num("c.paid"),
                 "country": "c.country", "created_at": "c.created_at"},
        "default_sort": "c.created_at",
    },
    "leads": {
        "table": "fx_leads_view l",
        "live_filter": "l.deleted_at IS NULL",
        "select": f"""
            l.id, l.name, l.company, l.country, l.city, l.source, l.stage_id,
            {num('l.lead_score')} AS lead_score, {num('l.lead_value')} AS lead_value,
            l.rating_status, l.tag, l.lead_source, l.next_followup, l.converted_at,
            l.created_at, l.sales_rep, l.user_id, a.name AS sales_rep_name,
            ce.email, ce.phone
        """,
        "joins": "LEFT JOIN fx_users_view a ON a.id = l.sales_rep "
                 "LEFT JOIN contact_enrichment ce ON ce.user_id = l.user_id",
        "search": ["l.name", "l.company", "l.country", "l.city", "ce.email", "ce.phone"],
        "sort": {"name": "l.name", "company": "l.company",
                 "lead_value": num("l.lead_value"), "lead_score": num("l.lead_score"),
                 "country": "l.country", "rating_status": "l.rating_status",
                 "created_at": "l.created_at"},
        "default_sort": "l.created_at",
    },
    "accounts": {
        "table": "fx_accounts_view ac",
        "live_filter": "ac.deleted_at IS NULL",
        "select": f"""
            ac.id, ac.account_number, ac.account_type, ac.account_group,
            ac.account_currency, {num('ac.leverage')} AS leverage,
            {num('ac.account_balance')} AS account_balance, {num('ac.equity')} AS equity,
            {num('ac.credit')} AS credit, {num('ac.margin_free')} AS margin_free,
            ac.is_islamic, ac.status, ac.user_id, ac.agent, ac.created_at,
            ag.name AS agent_name
        """,
        "joins": "LEFT JOIN fx_users_view ag ON ag.id = ac.agent",
        "search": ["ac.account_number", "ac.account_group", "ac.account_type"],
        "sort": {"account_number": "ac.account_number",
                 "account_balance": num("ac.account_balance"),
                 "equity": num("ac.equity"), "leverage": num("ac.leverage"),
                 "account_type": "ac.account_type", "created_at": "ac.created_at"},
        "default_sort": "ac.created_at",
    },
    "transactions": {
        "table": "fx_transactions_view t",
        "live_filter": "t.deleted_at IS NULL",
        "select": f"""
            t.id, t.account_number, t.type, {num('t.amount')} AS amount,
            t.currency, t.payment_method, t.status, t.order_trade, t.note,
            t.open_time, t.created_at, t.user_id
        """,
        "joins": "",
        "search": ["t.account_number", "t.payment_method", "t.type"],
        "sort": {"amount": num("t.amount"), "type": "t.type", "status": "t.status",
                 "account_number": "t.account_number", "created_at": "t.created_at"},
        "default_sort": "t.created_at",
    },
    "users": {
        "table": "fx_users_view u",
        "live_filter": "u.deleted_at IS NULL",
        "select": f"""
            u.id, u.name, u.surname, u.second_name, u.type, u.language, u.locale,
            u.last_login, u.last_ip, u.is_kyc_verified, u.banned, u.ib_code, u.ib_number,
            {num('u.total_deposit')} AS total_deposit, {num('u.loyalty_points')} AS loyalty_points,
            u.created_at, ce.email, ce.phone
        """,
        "joins": "LEFT JOIN contact_enrichment ce ON ce.user_id = u.id",
        "search": ["u.name", "u.surname", "u.type", "u.ib_code", "ce.email", "ce.phone"],
        "sort": {"name": "u.name", "type": "u.type",
                 "total_deposit": num("u.total_deposit"),
                 "last_login": "u.last_login", "created_at": "u.created_at"},
        "default_sort": "u.created_at",
    },
}


def _list(entity, search, page, page_size, sort, order, extra_where=None, extra_params=None):
    cfg = ENTITIES[entity]
    where = []
    params = dict(extra_params or {})
    if cfg["live_filter"]:
        where.append(cfg["live_filter"])
    if search:
        ors = [f"{c} ILIKE %(search)s" for c in cfg["search"]]
        where.append("(" + " OR ".join(ors) + ")")
        params["search"] = f"%{search}%"
    if extra_where:
        where.append(extra_where)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sort_col = cfg["sort"].get(sort, cfg["default_sort"])
    order_sql = "DESC" if str(order).lower() == "desc" else "ASC"
    offset = (page - 1) * page_size

    total = query_one(
        f"SELECT count(*) AS n FROM {cfg['table']} {cfg['joins']} {where_sql}", params
    )["n"]
    params["limit"] = page_size
    params["offset"] = offset
    rows = query_all(
        f"""SELECT {cfg['select']} FROM {cfg['table']} {cfg['joins']} {where_sql}
            ORDER BY {sort_col} {order_sql} NULLS LAST
            LIMIT %(limit)s OFFSET %(offset)s""",
        params,
    )
    return {"total": total, "page": page, "page_size": page_size, "rows": rows}


# ------------------------------------------------------------------- list routes
def _list_route(entity):
    def route(search: str = "", page: int = 1, page_size: int = Query(25, le=200),
              sort: str = "", order: str = "desc"):
        return _list(entity, search, page, page_size, sort, order)
    return route


for _e in ENTITIES:
    app.add_api_route(f"/api/{_e}", _list_route(_e), methods=["GET"])


# --------------------------------------------------------------- detail routes
def _person_bundle(user_id):
    """Accounts + transactions + summary for a user_id (shared by client/lead/user detail)."""
    accounts = query_all(
        f"""SELECT ac.account_number, ac.account_type, ac.account_group,
                   ac.account_currency, {num('ac.account_balance')} AS account_balance,
                   {num('ac.equity')} AS equity, {num('ac.leverage')} AS leverage,
                   ac.status, ac.created_at
            FROM fx_accounts_view ac
            WHERE ac.user_id = %(uid)s AND ac.deleted_at IS NULL
            ORDER BY ac.created_at DESC LIMIT 200""",
        {"uid": str(user_id)},
    )
    txns = query_all(
        f"""SELECT t.id, t.account_number, t.type, {num('t.amount')} AS amount,
                   t.currency, t.payment_method, t.status, t.created_at
            FROM fx_transactions_view t
            WHERE t.user_id = %(uid)s AND t.deleted_at IS NULL
            ORDER BY t.created_at DESC LIMIT 200""",
        {"uid": str(user_id)},
    )
    summary = query_one(
        f"""SELECT
              COALESCE(SUM(CASE WHEN type='deposit' AND status='completed' THEN {num('amount')} END),0) AS deposits,
              COALESCE(SUM(CASE WHEN type='withdrawal' AND status='completed' THEN {num('amount')} END),0) AS withdrawals,
              count(*) FILTER (WHERE status='completed') AS completed_txns
            FROM fx_transactions_view WHERE user_id = %(uid)s AND deleted_at IS NULL""",
        {"uid": str(user_id)},
    )
    return accounts, txns, summary


@app.get("/api/clients/{cid}")
def client_detail(cid: str):
    cfg = ENTITIES["clients"]
    row = query_one(
        f"SELECT {cfg['select']} FROM {cfg['table']} {cfg['joins']} WHERE c.id = %(id)s",
        {"id": cid},
    )
    if not row:
        raise HTTPException(404, "Client not found")
    user = query_one("SELECT * FROM fx_users_view WHERE id = %(id)s", {"id": row["user_id"]})
    accounts, txns, summary = _person_bundle(row["user_id"])
    return {"client": row, "user": _clean_user(user), "accounts": accounts,
            "transactions": txns, "summary": summary}


@app.get("/api/leads/{lid}")
def lead_detail(lid: str):
    cfg = ENTITIES["leads"]
    row = query_one(
        f"SELECT {cfg['select']} FROM {cfg['table']} {cfg['joins']} WHERE l.id = %(id)s",
        {"id": lid},
    )
    if not row:
        raise HTTPException(404, "Lead not found")
    user = query_one("SELECT * FROM fx_users_view WHERE id = %(id)s", {"id": row["user_id"]})
    accounts, txns, summary = _person_bundle(row["user_id"])
    return {"lead": row, "user": _clean_user(user), "accounts": accounts,
            "transactions": txns, "summary": summary}


@app.get("/api/accounts/{aid}")
def account_detail(aid: str):
    cfg = ENTITIES["accounts"]
    row = query_one(
        f"SELECT {cfg['select']} FROM {cfg['table']} {cfg['joins']} WHERE ac.id = %(id)s",
        {"id": aid},
    )
    if not row:
        raise HTTPException(404, "Account not found")
    txns = query_all(
        f"""SELECT t.id, t.type, {num('t.amount')} AS amount, t.currency,
                   t.payment_method, t.status, t.created_at
            FROM fx_transactions_view t
            WHERE t.account_number = %(acc)s AND t.deleted_at IS NULL
            ORDER BY t.created_at DESC LIMIT 200""",
        {"acc": row["account_number"]},
    )
    owner = query_one("SELECT * FROM fx_users_view WHERE id = %(id)s", {"id": row["user_id"]})
    return {"account": row, "owner": _clean_user(owner), "transactions": txns}


@app.get("/api/transactions/{tid}")
def transaction_detail(tid: str):
    row = query_one("SELECT * FROM fx_transactions_view WHERE id = %(id)s", {"id": tid})
    if not row:
        raise HTTPException(404, "Transaction not found")
    return {"transaction": row}


@app.get("/api/users/{uid}")
def user_detail(uid: str):
    user = query_one("SELECT * FROM fx_users_view WHERE id = %(id)s", {"id": uid})
    if not user:
        raise HTTPException(404, "User not found")
    accounts, txns, summary = _person_bundle(uid)
    return {"user": _clean_user(user), "accounts": accounts,
            "transactions": txns, "summary": summary}


# Never leak credential/secret columns from the raw user mirror.
_HIDDEN_USER_COLS = {
    "password", "remember_token", "access_token", "calendar_token", "activation_code",
    "mobile_otp", "local_2fa_code", "local_2fa_verify", "transaction_otp",
    "google2fa_secret", "google2fa_enable", "sumsub_app_id",
}


def _clean_user(u):
    if not u:
        return None
    clean = {k: v for k, v in u.items() if k not in _HIDDEN_USER_COLS}
    contact = query_one(
        "SELECT email, phone FROM contact_enrichment WHERE user_id = %(id)s", {"id": u.get("id")})
    if contact:
        clean["email"] = contact.get("email")
        clean["phone"] = contact.get("phone")
    return clean


# ------------------------------------------------------------------- dashboard
@app.get("/api/stats")
def stats():
    counts = query_one(f"""
        SELECT
          (SELECT count(*) FROM fx_clients_view WHERE deleted_at IS NULL) AS clients,
          (SELECT count(*) FROM fx_leads_view WHERE deleted_at IS NULL) AS leads,
          (SELECT count(*) FROM fx_accounts_view WHERE deleted_at IS NULL) AS accounts,
          (SELECT count(*) FROM fx_transactions_view WHERE deleted_at IS NULL) AS transactions,
          (SELECT count(*) FROM fx_users_view WHERE type <> 'client') AS staff
    """)
    # payment_method='0' rows are legacy system/demo balance-fixes (sentinel
    # 99,999,999.99 amounts) — excluded from money figures so totals are real.
    real = "deleted_at IS NULL AND COALESCE(payment_method,'') <> '0'"
    money = query_one(f"""
        SELECT
          COALESCE(SUM(CASE WHEN type='deposit' AND status='completed' THEN {num('amount')} END),0) AS deposits,
          COALESCE(SUM(CASE WHEN type='withdrawal' AND status='completed' THEN {num('amount')} END),0) AS withdrawals
        FROM fx_transactions_view WHERE {real}
    """)
    money["net"] = float(money["deposits"]) - float(money["withdrawals"])
    acct_types = query_all(
        "SELECT account_type AS label, count(*) AS n FROM fx_accounts_view "
        "WHERE deleted_at IS NULL GROUP BY account_type ORDER BY n DESC")
    txn_status = query_all(
        "SELECT status AS label, count(*) AS n FROM fx_transactions_view "
        "WHERE deleted_at IS NULL GROUP BY status ORDER BY n DESC")
    txn_types = query_all(
        f"SELECT type AS label, count(*) AS n, COALESCE(SUM({num('amount')}),0) AS total "
        f"FROM fx_transactions_view WHERE {real} AND status='completed' "
        "GROUP BY type ORDER BY n DESC")
    lead_rating = query_all(
        "SELECT COALESCE(rating_status,'unknown') AS label, count(*) AS n FROM fx_leads_view "
        "WHERE deleted_at IS NULL GROUP BY rating_status ORDER BY n DESC")
    top_countries = query_all(
        "SELECT country AS label, count(*) AS n FROM fx_leads_view "
        "WHERE deleted_at IS NULL AND country IS NOT NULL AND country <> '' "
        "GROUP BY country ORDER BY n DESC LIMIT 8")
    monthly = query_all(f"""
        SELECT to_char(date_trunc('month', created_at::timestamp), 'YYYY-MM') AS month,
               COALESCE(SUM({num('amount')}),0) AS deposits
        FROM fx_transactions_view
        WHERE {real} AND type='deposit' AND status='completed'
          AND created_at <> '' AND created_at >= '2024-01-01'
        GROUP BY 1 ORDER BY 1""")
    recent = query_all(f"""
        SELECT t.id, t.account_number, t.type, {num('t.amount')} AS amount, t.currency,
               t.payment_method, t.status, t.created_at
        FROM fx_transactions_view t WHERE t.deleted_at IS NULL
        ORDER BY t.created_at DESC LIMIT 10""")
    return {
        "counts": counts, "money": money, "account_types": acct_types,
        "txn_status": txn_status, "txn_types": txn_types, "lead_rating": lead_rating,
        "top_countries": top_countries, "monthly_deposits": monthly, "recent_txns": recent,
    }


@app.get("/api/health")
def health():
    return {"ok": True, "db": query_one("SELECT 1 AS x")["x"]}


# --------------------------------------------------- serve built frontend (SPA)
_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_BUILD):
    app.mount("/assets", StaticFiles(directory=os.path.join(_BUILD, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = os.path.join(_BUILD, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(_BUILD, "index.html"))
