"""Global staff search — one box, everything.

GET /search?q= returns matches grouped by entity type: clients / leads / IBs / trading
accounts / trades / transactions / deposits (payment senders & receipts). Staff-only
(get_current_user — the whole main CRM is staff; clients/IBs live on the portal). READ-ONLY.

Every query is written to hit an existing index — login / email / name / customer_no /
phone-last-9 (functional idx) / deal_id / ocr_txid — so it stays fast even against the
16.8M-row deals table and the 100k+ payment tables. Each category is independently
try/except'd (a broken query returns [] and rolls back, never 500s the whole search).
"""
import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/search", tags=["search"])

PER_CAT = 12
_PH9 = "right(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)"


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _ctx(q: str) -> dict:
    q = (q or "").strip()
    dig = _digits(q)
    is_num = q.isdigit()
    return {
        "q": q, "like": f"%{q}%", "pfx": f"{q}%", "dig": dig,
        "is_num": is_num,
        "numval": int(q) if is_num and len(q) <= 15 else None,
        "has_at": "@" in q,
        "last9": dig[-9:] if len(dig) >= 6 else None,
    }


def _rows(db, sql, p):
    try:
        return db.execute(text(sql), p).mappings().all()
    except Exception:
        db.rollback()
        return []


def _clients(db, c):
    conds, p = [], {"lk": c["like"], "q": c["q"], "lim": PER_CAT}
    if c["numval"] is not None:
        conds.append("login = :nv"); p["nv"] = c["numval"]
    if c["last9"]:
        conds.append(f"{_PH9} = :l9"); p["l9"] = c["last9"]
    conds += ["email ILIKE :lk", "name ILIKE :lk", "COALESCE(full_name_en,'') ILIKE :lk",
              "customer_no = :q", "id_number = :q"]
    where = " OR ".join(f"({x})" for x in conds)
    # ONE row per PERSON (customer_no → email → login) — a person's many accounts collapse to a
    # single client hit; the individual accounts show in the Trading-accounts group. n_accounts =
    # how many of their accounts matched (all of them, on a name/email search).
    rows = _rows(db, f"""
        SELECT login, name, full_name_en, email, phone, platform, customer_no, country,
               is_archived, is_flagged, n_accounts
        FROM (
          SELECT DISTINCT ON (pk) login, name, full_name_en, email, phone, platform, customer_no,
                 country, is_archived, is_flagged,
                 COUNT(*) OVER (PARTITION BY pk) AS n_accounts
          FROM (
            SELECT login, name, full_name_en, email, phone, platform, customer_no, country,
                   is_archived, is_flagged,
                   COALESCE(NULLIF(customer_no,''), NULLIF(LOWER(email),''), CAST(login AS TEXT)) AS pk
            FROM clients WHERE {where}
          ) s
          ORDER BY pk, COALESCE(is_archived,false), login
        ) d
        ORDER BY COALESCE(is_archived,false), login LIMIT :lim""", p)
    out = []
    for r in rows:
        sub = f"login {r['login']} · {r['platform'] or 'MT5'}"
        if r["email"]:       sub += f" · {r['email']}"
        if r["phone"]:       sub += f" · {r['phone']}"
        if r["country"]:     sub += f" · {r['country']}"
        if r["customer_no"]: sub += f" · #{r['customer_no']}"
        if (r["n_accounts"] or 1) > 1: sub += f" · {r['n_accounts']} accounts"
        out.append({
            "type": "client",
            "title": r["full_name_en"] or r["name"] or f"Client {r['login']}",
            "subtitle": sub,
            "meta": "archived" if r["is_archived"] else ("flagged" if r["is_flagged"] else ""),
            "nav": {"page": "clients", "search": (r["email"] or r["customer_no"] or str(r["login"])), "openProfile": r["login"]},
        })
    return out


def _leads(db, c):
    conds, p = [], {"lk": c["like"], "q": c["q"], "lim": PER_CAT}
    if c["numval"] is not None:
        conds.append("id = :nv"); p["nv"] = c["numval"]
    if c["last9"]:
        conds.append(f"{_PH9} = :l9"); p["l9"] = c["last9"]
    conds += ["email ILIKE :lk", "full_name ILIKE :lk", "customer_no = :q", "id_number = :q"]
    where = " OR ".join(f"({x})" for x in conds)
    # ONE row per PERSON (customer_no → email → id) — dup lead entries for the same person collapse.
    rows = _rows(db, f"""
        SELECT id, full_name, email, phone, country, source, matched_login, is_archived, n_leads
        FROM (
          SELECT DISTINCT ON (pk) id, full_name, email, phone, country, source, matched_login,
                 is_archived, created_at,
                 COUNT(*) OVER (PARTITION BY pk) AS n_leads
          FROM (
            SELECT id, full_name, email, phone, country, source, matched_login, is_archived, created_at,
                   COALESCE(NULLIF(customer_no,''), NULLIF(LOWER(email),''), CAST(id AS TEXT)) AS pk
            FROM leads WHERE {where}
          ) s
          ORDER BY pk, COALESCE(is_archived,false), created_at DESC NULLS LAST
        ) d
        ORDER BY COALESCE(is_archived,false), id DESC LIMIT :lim""", p)
    out = []
    for r in rows:
        sub = f"lead #{r['id']}"
        if r["source"]:   sub += f" · {r['source']}"
        if r["email"]:    sub += f" · {r['email']}"
        if r["phone"]:    sub += f" · {r['phone']}"
        if r["country"]:  sub += f" · {r['country']}"
        if r["matched_login"]: sub += f" · → client {r['matched_login']}"
        if (r["n_leads"] or 1) > 1: sub += f" · {r['n_leads']} lead rows"
        out.append({
            "type": "lead",
            "title": r["full_name"] or f"Lead #{r['id']}",
            "subtitle": sub,
            "meta": "archived" if r["is_archived"] else ("converted" if r["matched_login"] else ""),
            "nav": {"page": "leads", "search": (r["email"] or r["phone"] or r["full_name"] or str(r["id"]))},
        })
    return out


def _ibs(db, c):
    conds, p = [], {"lk": c["like"], "q": c["q"], "lim": PER_CAT}
    if c["numval"] is not None:
        conds += ["agent_id = :nv", "id = :nv"]; p["nv"] = c["numval"]
    if c["last9"]:
        conds.append(f"{_PH9} = :l9"); p["l9"] = c["last9"]
    conds += ["name ILIKE :lk", "email ILIKE :lk", "ib_code = :q"]
    where = " OR ".join(f"({x})" for x in conds)
    # ONE row per PERSON (email → agent login → id) — a partner with several IB records collapses.
    rows = _rows(db, f"""
        SELECT id, agent_id, ib_code, name, email, phone, country, ib_level, status, total_commission
        FROM (
          SELECT DISTINCT ON (pk) id, agent_id, ib_code, name, email, phone, country, ib_level,
                 status, total_commission
          FROM (
            SELECT id, agent_id, ib_code, name, email, phone, country, ib_level, status, total_commission,
                   COALESCE(NULLIF(LOWER(email),''), CAST(agent_id AS TEXT), CAST(id AS TEXT)) AS pk
            FROM ibs WHERE {where}
          ) s
          ORDER BY pk, total_commission DESC NULLS LAST
        ) d
        ORDER BY total_commission DESC NULLS LAST LIMIT :lim""", p)
    out = []
    for r in rows:
        sub = f"IB {r['ib_code'] or r['id']}"
        if r["agent_id"]: sub += f" · login {r['agent_id']}"
        if r["ib_level"]: sub += f" · {r['ib_level']}"
        if r["email"]:    sub += f" · {r['email']}"
        if r["country"]:  sub += f" · {r['country']}"
        out.append({
            "type": "ib",
            "title": r["name"] or f"IB {r['ib_code'] or r['id']}",
            "subtitle": sub,
            "meta": r["status"] or "",
            "nav": {"page": "ib_admin", "ibId": r["id"]},
        })
    return out


def _accounts(db, c):
    # NOT deduped — a person's every trading account is listed (higher cap than the person groups).
    conds, p = [], {"lk": c["like"], "q": c["q"], "lim": 40}
    if c["numval"] is not None:
        conds.append("login = :nv"); p["nv"] = c["numval"]
    if c["last9"]:
        conds.append(f"{_PH9} = :l9"); p["l9"] = c["last9"]
    conds += ["group_name ILIKE :lk", "name ILIKE :lk", "email ILIKE :lk", "customer_no = :q"]
    where = " OR ".join(f"({x})" for x in conds)
    rows = _rows(db, f"""SELECT login, name, group_name, platform, balance, is_active, country, is_ib
        FROM trading_accounts WHERE {where}
        ORDER BY COALESCE(is_active,false) DESC, login LIMIT :lim""", p)
    out = []
    for r in rows:
        sub = f"login {r['login']}"
        if r["group_name"]: sub += f" · {r['group_name']}"
        if r["platform"]:   sub += f" · {r['platform']}"
        if r["balance"] is not None: sub += f" · bal ${r['balance']:,.2f}"
        out.append({
            "type": "account",
            "title": r["name"] or f"Account {r['login']}",
            "subtitle": sub,
            "meta": ("IB" if r["is_ib"] else "") + (" · active" if r["is_active"] else " · inactive"),
            "nav": {"page": "accounts", "login": r["login"]},
        })
    return out


_ACT = {0: "buy", 1: "sell", 2: "balance", 3: "credit", 6: "bonus"}


def _trades(db, c):
    if c["numval"] is None:
        return []
    rows = _rows(db, """SELECT deal_id, login, symbol, action, volume, price, profit, deal_date, platform
        FROM deals WHERE deal_id = :nv ORDER BY deal_date DESC NULLS LAST LIMIT :lim""",
                 {"nv": c["numval"], "lim": PER_CAT})
    out = []
    for r in rows:
        lots = (r["volume"] or 0) / 10000
        sub = f"trade #{r['deal_id']} · login {r['login']} · {r['symbol'] or ''} {_ACT.get(r['action'], '')} {lots:g} lots"
        if r["deal_date"]: sub += f" · {r['deal_date']}"
        if r["platform"]:  sub += f" · {r['platform']}"
        out.append({
            "type": "trade",
            "title": f"Trade {r['deal_id']}",
            "subtitle": sub,
            "meta": (f"{float(r['profit']):+,.2f}" if r["profit"] is not None else ""),
            "nav": {"page": "accounts", "login": r["login"]},
        })
    return out


def _transactions(db, c):
    conds, p = [], {"lk": c["like"], "lim": PER_CAT}
    if c["numval"] is not None:
        conds += ["deal_id = :nv", "login = :nv"]; p["nv"] = c["numval"]
    conds.append("psp_reference ILIKE :lk")
    where = " OR ".join(f"({x})" for x in conds)
    rows = _rows(db, f"""SELECT deal_id, login, tx_type, amount, method, psp_reference, tx_date, status
        FROM transactions WHERE {where} ORDER BY tx_date DESC NULLS LAST LIMIT :lim""", p)
    out = []
    for r in rows:
        typ = (r["tx_type"] or "tx").replace("_", " ")
        amt = float(r["amount"] or 0)
        sub = f"{typ} ${amt:,.2f} · login {r['login']}"
        if r["method"]:        sub += f" · {r['method']}"
        if r["psp_reference"]: sub += f" · ref {r['psp_reference']}"
        if r["tx_date"]:       sub += f" · {r['tx_date']}"
        out.append({
            "type": "transaction",
            "title": f"{typ.title()} ${amt:,.0f}",
            "subtitle": sub,
            "meta": r["status"] or "",
            "nav": {"page": "transactions"},
        })
    return out


def _deposits(db, c):
    """Payment receipts / senders across Qi, ZainCash, ShamCash. Search by receipt txid
    (ocr_txid — indexed prefix), the TradeSoft txn id, or the depositing client login."""
    if len(c["q"]) < 4:
        return []
    out = []
    for tbl, method in (("pay_qi_card", "Qi"), ("pay_zaincash", "ZainCash"), ("pay_sham_cash", "ShamCash")):
        conds = ["ocr_txid ILIKE :pfx", "ts_txn_id = :q"]
        p = {"pfx": c["pfx"], "q": c["q"], "lim": 6}
        if c["numval"] is not None:
            conds.append("client_login = :nv"); p["nv"] = c["numval"]
        where = " OR ".join(f"({x})" for x in conds)
        rows = _rows(db, f"""SELECT id, client_login, person_name, sys_amount, ocr_txid, ts_txn_id,
                 ocr_sender_name, ocr_sender_acct, tx_date, status
            FROM {tbl} WHERE {where} ORDER BY tx_date DESC NULLS LAST LIMIT :lim""", p)
        for r in rows:
            sub = f"{method} deposit · login {r['client_login']}"
            if r["sys_amount"]:       sub += f" · ${float(r['sys_amount']):,.2f}"
            if r["ocr_txid"]:         sub += f" · txid {r['ocr_txid']}"
            if r["ocr_sender_name"]:  sub += f" · from {r['ocr_sender_name']}"
            if r["ocr_sender_acct"]:  sub += f" ({r['ocr_sender_acct']})"
            out.append({
                "type": "deposit",
                "title": f"{method} deposit {r['ocr_txid'] or r['ts_txn_id'] or r['id']}",
                "subtitle": sub,
                "meta": r["status"] or "",
                "nav": ({"page": "clients", "search": str(r["client_login"]), "openProfile": r["client_login"]}
                        if r["client_login"] else {"page": "transactions"}),
            })
    return out[:PER_CAT]


_CATS = [
    ("clients",      "Clients",             "👤", _clients),
    ("leads",        "Leads",               "🎯", _leads),
    ("ibs",          "IBs / Partners",      "🤝", _ibs),
    ("accounts",     "Trading accounts",    "📊", _accounts),
    ("trades",       "Trades",              "📈", _trades),
    ("transactions", "Transactions",        "💵", _transactions),
    ("deposits",     "Deposits / Senders",  "🧾", _deposits),
]


@router.get("")
def global_search(q: str = Query("", max_length=100),
                  db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    c = _ctx(q)
    if len(c["q"]) < 2:
        return {"query": c["q"], "total": 0, "groups": []}
    groups, total = [], 0
    for key, label, icon, fn in _CATS:
        items = fn(db, c)
        if items:
            groups.append({"category": key, "label": label, "icon": icon, "count": len(items), "items": items})
            total += len(items)
    return {"query": c["q"], "total": total, "groups": groups}
