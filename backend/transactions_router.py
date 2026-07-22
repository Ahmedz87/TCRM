"""
transactions_router.py — Full transaction history with filtering, sorting, review actions
Auto payments: USDT, Ovadraft, Visa/Master (instant approved)
Manual payments: Qi card, ZainCash, AsiaPay, Bank wire (require admin review)
Withdrawals with network ≥6/10 auto-flagged as pending
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
import audit
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, date
from database import get_db
from auth import get_current_user
from perf_cache import cached
import models
import rbac

# Only back-office (+admins) may take action on transactions; everyone else is read-only.
BACKOFFICE_ROLES = {"super_admin", "admin", "backoffice"}

# Who may EXPORT the transactions list to CSV: any admin/super-admin, plus explicitly-named staff
# (Jwan is backoffice, so kept in the name/email allowlist). Matched by role, then email/name.
EXPORT_ROLES  = {"admin", "super_admin"}
EXPORT_EMAILS = {"jwanf@tnfx.co", "narmeena@tnfx.co"}
EXPORT_NAMES  = {"jwan", "narmeen"}

def _can_export(user) -> bool:
    email = (getattr(user, "email", "") or "").strip().lower()
    name  = (getattr(user, "full_name", "") or "").strip().lower()
    role  = (getattr(user, "role", "") or "").strip().lower()
    return role in EXPORT_ROLES or email in EXPORT_EMAILS or name in EXPORT_NAMES

router = APIRouter(prefix="/transactions", tags=["Transactions"])

AUTO_METHODS = {'usdt', 'ovadraft', 'visa/master', 'visa', 'master', 'mastercard'}

# ── "MT5" balance-adjustment rows (tickets #43 / #55) ───────────────────────────
# In build_transactions.py the payment method is parsed from the MT deal comment
# (split_part(comment,' - ',3)); when a balance deal has no real payment segment it
# falls back to d.platform = the literal 'MT5'. So method='MT5' is NOT a payment
# provider — it marks an internal MT5 balance adjustment / zeroing (notes like
# "Negative balance payoff", "Deposit fix", "Deposit fee", "Cashback",
# "Stop out compensation", "reverting capital", …). Every method='MT5' deposit row
# in the live DB is one of these (none are genuine client deposits).
MT5_ADJUST_METHOD = "MT5"
# Friendlier label shown in the UI instead of the bare platform name "MT5".
MT5_ADJUST_LABEL = "Internal / MT5 adjustment"

# ── Internal non-method labels (ticket #85, Jwan) ───────────────────────────────
# MT4 journal-sourced balance adjustments land their internal note in the *method*
# column (instead of the literal 'MT5' that MT5-sourced adjustments use), e.g.
# 'Deposit Fix' / 'Deposit fix' / 'Deposit/fix', 'Deposit Fees', 'Cashback',
# 'Stop out compensation'. These are NOT real deposit methods, so — exactly like
# method='MT5' — they must be hidden from the DEPOSITS view and excluded from the
# per-method / client-profile deposit totals. The pattern is normalised over
# spaces/slashes and case-insensitive (POSTGRES ~*). Verified against live data it
# matches ONLY internal-label rows, never a real PSP method (214 deposit rows,
# ~$36k, on top of the ~2.7k method='MT5' fix rows already excluded).
INTERNAL_LABEL_RE = (
    r"(deposit\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance"
    r"|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back"
    r"|credit\s*(in|out)|bonus\s*adjustment)"
)
# SQL fragment that is TRUE for a genuine deposit method (excludes 'MT5' + the
# internal labels above). Reused by the deposits list, the per-method stats, and
# the client-profile totals so all three stay consistent.
NOT_INTERNAL_SQL = "(t.method <> :mt5_adj_method AND t.method !~* :internal_re)"

# PERF (Jul 2026): evaluating the regex above per-row costs ~0.4s on the 2M-row table
# (method has 143k distinct values — transfers embed counterparties). Only ~44 method
# values are internal, so the hot deposits view uses `method <> ALL(:list)` with the
# list precomputed from the SAME regex and cached in-process for an hour (0.06s counts,
# identical results). The regex stays the single source of truth.
import time as _time
_INTERNAL_METHODS = {"ts": 0.0, "vals": None}

def _internal_methods(db) -> list:
    if _INTERNAL_METHODS["vals"] is None or _time.time() - _INTERNAL_METHODS["ts"] > 3600:
        rows = db.execute(text(
            "SELECT DISTINCT method FROM transactions "
            "WHERE tx_type='deposit' AND (method = :m OR method ~* :re)"),
            {"m": MT5_ADJUST_METHOD, "re": INTERNAL_LABEL_RE}).fetchall()
        _INTERNAL_METHODS["vals"] = [r[0] for r in rows] or ["MT5"]
        _INTERNAL_METHODS["ts"] = _time.time()
    return _INTERNAL_METHODS["vals"]


def method_display(method: str) -> str:
    """Human-friendly payment-method label. The bare platform value 'MT5' is a
    placeholder for an internal balance adjustment, not a real method — relabel it."""
    if (method or "").strip().upper() == MT5_ADJUST_METHOD:
        return MT5_ADJUST_LABEL
    return method or "—"


import re as _re
# An internal transfer always names its counterparty in the method/notes, e.g.
#   method 'from 438760' / 'to 438747'      notes 'Transfer - from/to 438760 [MT4]'
#   method 'Transfer from #572115'          notes 'Transfer - from 572115 [MT5]'
# Direction "from X" = money came IN from X (From=X, To=this login); "to X" = money went
# OUT to X (From=this login, To=X). Returns (from_account, to_account) as strings.
_XFER_RE = _re.compile(r"\b(from|to)\b\s*#?\s*(\d+)", _re.I)


def parse_transfer(login, method: str, notes: str):
    blob = f"{method or ''} || {notes or ''}"
    m = _XFER_RE.search(blob)
    me = str(login) if login is not None else ""
    if not m:
        return ("", "")                       # counterparty unknown (truncated/reverting)
    direction, other = m.group(1).lower(), m.group(2)
    return (other, me) if direction == "from" else (me, other)


class ActionRequest(BaseModel):
    deal_id:  int
    action:   str   # approve / reject / risk
    note:     Optional[str] = ""


@router.get("")
async def get_transactions(
    page:       int   = Query(1, ge=1),
    page_size:  int   = Query(20, ge=1, le=500),
    tx_type:    str   = Query("deposit"),
    tx_type_multi: str = Query(""),
    sort:       str   = Query("date"),
    sort_dir:   str   = Query("desc"),
    search:     str   = Query(""),
    method:     str   = Query(""),
    status:     str   = Query(""),
    agent:      str   = Query(""),
    ib:         str   = Query(""),
    country:    str   = Query(""),
    client:     str   = Query(""),
    date_from:  str   = Query(""),
    date_to:    str   = Query(""),
    period:     str   = Query(""),
    login:      int   = Query(0),
    logins:     str   = Query(""),
    export:     str   = Query(""),   # "csv" -> download the filtered rows (gated to allowed staff)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Map tx_type to DB types
    type_map = {
        "deposit":           ["deposit"],
        "withdrawal":        ["withdrawal"],
        "internal_transfer": ["internal_transfer"],
        "bonus":             ["bonus_deposit", "bonus_withdrawal"],
        # #1 — MT internal balance ops (deposit-fix / negative-balance cover / rejected-withdrawal
        # reverts / abuse clawbacks); NOT real deposits or withdrawals
        "mt_adjustment":     ["balance_fix", "negative_cover", "withdrawal_revert", "abuse_clawback"],
    }
    types = type_map.get(tx_type, ["deposit"])
    if tx_type_multi:
        # whitelist — this string is interpolated into SQL, so ONLY known tx types pass
        _VALID_TYPES = {"deposit", "withdrawal", "internal_transfer", "bonus_deposit",
                        "bonus_withdrawal", "balance_fix", "negative_cover",
                        "withdrawal_revert", "abuse_clawback", "deposit_dup",
                        "withdrawal_dup", "internal_transfer_dup"}
        types = [t.strip() for t in tx_type_multi.split(',') if t.strip() in _VALID_TYPES] or ["deposit"]

    types_str = "','".join(types)
    where_parts = [f"t.tx_type IN ('{types_str}')"]
    params: dict = {}

    # Ticket #55: the client DEPOSITS view must NOT show internal MT5 balance
    # adjustments / zeroing (method='MT5'); those are not genuine client deposits.
    # Only exclude them from the deposit list — they stay visible in other views
    # so the money still reconciles elsewhere. A user explicitly filtering by the
    # MT5 method keeps seeing them.
    if "deposit" in types and not method:
        # fast list-based equivalent of NOT_INTERNAL_SQL (see _internal_methods)
        where_parts.append("t.method <> ALL(:internal_methods)")
        params["internal_methods"] = _internal_methods(db)

    if search:
        where_parts.append("(CAST(t.login AS TEXT) LIKE :s OR c.name ILIKE :s OR t.method ILIKE :s OR t.notes ILIKE :s OR c.phone ILIKE :s)")
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
    if country:
        where_parts.append("c.country ILIKE :country")
        params["country"] = f"%{country}%"
    if client:
        # dedicated client filter (name OR login) — set by the "Filter by client" box and by clicking
        # a client name in the table (click again on the filtered client opens the profile).
        where_parts.append("(c.name ILIKE :client OR CAST(t.login AS TEXT) LIKE :client)")
        params["client"] = f"%{client}%"
    if login:
        where_parts.append("t.login = :login")
        params["login"] = login
    if logins:
        login_list = [int(x) for x in logins.split(',') if x.strip().isdigit()]
        if login_list:
            placeholders = ",".join([f":ll{i}" for i in range(len(login_list))])
            where_parts.append(f"t.login IN ({placeholders})")
            for i, ll in enumerate(login_list): params[f"ll{i}"] = ll
    # tx_date is TEXT ('YYYY-MM-DD HH24:MI:SS'), so compare as ISO STRINGS (never CAST the param to DATE —
    # `text >= date` errors and broke the whole custom-range query). date_to is INCLUSIVE.
    # TIMEZONE: the picked dates are IRAQI calendar days but tx_date is UTC — crm_tz.day_lo/day_hi
    # shift each boundary to 21:00 UTC so the selected day covers 00:00-24:00 Baghdad.
    from crm_tz import day_lo as _day_lo, day_hi as _day_hi
    if date_from:
        where_parts.append("t.tx_date >= :date_from")
        try:
            params["date_from"] = _day_lo(date_from)
        except Exception:
            params["date_from"] = date_from
    if date_to:
        try:
            where_parts.append("t.tx_date < :date_to_next")
            params["date_to_next"] = _day_hi(date_to)
        except Exception:
            where_parts.append("t.tx_date <= :date_to")
            params["date_to"] = date_to + " 23:59:59"
    # Period preset (today / this_week / this_month / …) — applied only when no explicit date range
    # is given, so the table shares ONE time window with the dashboard KPI cards above it. Uses
    # index-friendly string comparison on the tx_date column (same approach as dashboard_router,
    # same Iraqi-day boundaries).
    if period and period != "all_time" and not date_from and not date_to:
        try:
            from dashboard_router import get_period_dates
            _pf, _pt = get_period_dates(period)
            where_parts.append("t.tx_date >= :pf AND t.tx_date < :pt_next")
            params["pf"] = _day_lo(_pf)
            params["pt_next"] = _day_hi(_pt)
        except Exception:
            pass

    # Role-based visibility: agent -> own clients' tx; manager -> team; director/admin -> all
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where_parts.append("c.assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where_parts.append("FALSE")

    where = "WHERE " + " AND ".join(where_parts)

    sort_col = {
        "date":   "t.tx_date",
        "amount": "t.amount",
    }.get(sort, "t.tx_date")
    sort_dir_sql = "DESC" if sort_dir == "desc" else "ASC"

    # ── CSV EXPORT (Jwan / Narmeen / super admin only) — same filters, no pagination ──
    if export == "csv":
        if not _can_export(current_user):
            raise HTTPException(status_code=403, detail="You are not allowed to export transactions")
        exp_rows = db.execute(text(f"""
            SELECT t.tx_date, c.name, t.login, t.amount, t.tx_type,
                   COALESCE(NULLIF(t.method,''),'') AS method,
                   u.full_name AS agent, ib.name AS ib, COALESCE(t.status,'approved') AS status
            FROM transactions t
            LEFT JOIN clients c ON c.login = t.login
            LEFT JOIN users u ON u.id = c.assigned_agent_id
            LEFT JOIN ibs ib ON ib.agent_id = c.agent
            {where}
            ORDER BY {sort_col} {sort_dir_sql} NULLS LAST
            LIMIT 100000
        """), params).fetchall()
        import io, csv as _csv
        from fastapi.responses import StreamingResponse
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["Date", "Client", "Login", "Amount", "Type", "Method", "Sales agent", "IB", "Status"])
        for r in exp_rows:
            w.writerow([str(r[0] or ""), r[1] or "", r[2], float(r[3] or 0),
                        r[4] or "", r[5] or "", r[6] or "", r[7] or "", r[8] or ""])
        buf.seek(0)
        fn = f"transactions_{tx_type}.csv"
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{fn}"'})

    # The two HEAVY aggregates — the pagination COUNT(*) and the KPI summary — each scan the full
    # 2M-row transactions table with 3 LEFT JOINs and depend ONLY on the filters + role scope (NOT on
    # page/sort). Cache them together for 30s so repeat loads + the page's 60s auto-refresh don't
    # re-scan; the actual rows below stay live. The scope token MUST be in the key so a scoped agent
    # never sees another scope's cached totals.
    _scope_tok = ("all" if _scope is None
                  else ("none" if not _scope else "a" + "_".join(map(str, sorted(_scope)))))
    _agg_key = "tx:agg:" + "|".join([
        tx_type, tx_type_multi, search, method, status, agent, ib, country, client,
        str(login), logins, date_from, date_to, period, _scope_tok,
    ])
    _agg_params = dict(params)  # filter params only (limit/offset not added until the rows query)

    # PERF: only join clients/users/ibs when a filter actually references them (search/agent/
    # ib/client/scope). A LEFT JOIN on a non-unique key can't be eliminated by the planner for
    # a COUNT, and it costs ~0.7s per aggregate on the 2M-row table.
    _needs_join = any(tok in where for tok in ("c.", "u.", "ib."))
    _agg_joins = ("""
        LEFT JOIN clients c ON c.login = t.login
        LEFT JOIN users u ON u.id = c.assigned_agent_id
        LEFT JOIN ibs ib ON ib.agent_id = c.agent""" if _needs_join else "")
    count_sql = f"""
        SELECT COUNT(*)
        FROM transactions t
        {_agg_joins}
        {where}
    """
    kpi_sql = f"""
        SELECT
            COALESCE(SUM(t.amount),0) as total_amount,
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE t.status IN ('pending','processing')) as pending_count,
            COALESCE(AVG(t.amount),0) as avg_amount,
            COALESCE(SUM(t.amount) FILTER (WHERE DATE(t.tx_date) = CURRENT_DATE),0) as today_amount,
            COUNT(*) FILTER (WHERE t.tx_type = 'deposit') as deposit_count,
            COUNT(*) FILTER (WHERE t.tx_type = 'withdrawal') as withdrawal_count,
            COUNT(*) FILTER (WHERE t.tx_type = 'internal_transfer') as transfer_count,
            COUNT(*) FILTER (WHERE t.tx_type IN ('bonus_deposit','bonus_withdrawal')) as bonus_count,
            COUNT(*) FILTER (WHERE t.tx_type IN ('balance_fix','negative_cover','withdrawal_revert','abuse_clawback')) as mt_adjustment_count
        FROM transactions t
        {_agg_joins}
        {where}
    """

    def _compute_agg():
        _total = db.execute(text(count_sql), _agg_params).scalar() or 0
        _k = db.execute(text(kpi_sql), _agg_params).fetchone()
        return {
            "total": _total,
            "kpis": {
                "total_amount":      float(_k[0] or 0),
                "total_count":       _k[1] or 0,
                "pending_count":     _k[2] or 0,
                "avg_amount":        float(_k[3] or 0),
                "today_amount":      float(_k[4] or 0),
                "deposit_count":     _k[5] or 0,
                "withdrawal_count":  _k[6] or 0,
                "transfer_count":    _k[7] or 0,
                "bonus_count":       _k[8] or 0,
                "mt_adjustment_count": _k[9] or 0,
                "flagged_count":     0,
            },
        }

    _agg = cached(_agg_key, 30, _compute_agg)
    total = _agg["total"]

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
            -- Network score: the SINGLE canonical 0-10 value (build_network_scores.py), same as every page
            (SELECT COALESCE(cx.network_score,0) FROM clients cx WHERE cx.login = t.login LIMIT 1) as network_score,
            -- Total tx count for this client
            (SELECT COUNT(*) FROM transactions t2
             WHERE t2.login = t.login AND t2.tx_type IN ('deposit','withdrawal')) as tx_count,
            t.currency, t.psp_reference, t.approved_at, t.deal_id as ref_id,
            tw.wallet_id AS ocr_wallet_id, tw.confidence AS wallet_conf, tw.sender_acct AS ocr_sender_acct,
            tw.sender_block AS ocr_sender_block, tw.receiver_acct AS ocr_receiver_acct,
            tw.card_name AS company_card_name, tw.sender_src AS sender_src,
            -- back-office team member who HOLDS the receiving card (from the Card settings /
            -- payment_cards). Match by the receiver account first, then the card name.
            COALESCE(
              (SELECT pc.holder_name FROM payment_cards pc
                 WHERE pc.number = NULLIF(tw.receiver_acct,'') AND COALESCE(pc.holder_name,'')<>'' LIMIT 1),
              (SELECT pc.holder_name FROM payment_cards pc
                 WHERE pc.account_number::text = NULLIF(tw.receiver_acct,'') AND COALESCE(pc.holder_name,'')<>'' LIMIT 1),
              (SELECT pc.holder_name FROM payment_cards pc
                 WHERE lower(pc.card_name) = lower(NULLIF(tw.card_name,'')) AND COALESCE(pc.holder_name,'')<>'' LIMIT 1)
            ) AS card_holder,
            tw.receipt_filename AS receipt_filename,
            -- appended LAST on purpose: the row dict below reads by POSITION (r[0]..r[34]),
            -- so a new column must never be inserted mid-list.
            c.country AS country
        FROM transactions t
        LEFT JOIN clients c ON c.login = t.login
        LEFT JOIN users u ON u.id = c.assigned_agent_id
        LEFT JOIN ibs ib ON ib.agent_id = c.agent
        LEFT JOIN transaction_wallet tw ON tw.transaction_id = t.id
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

    # Withdrawal abuse flags come from the TRADING-BEHAVIOUR detectors via the
    # abuse_account_flags table (worst open case per login, covering EVERY account
    # involved in a case — winner, loser, ring members — not just login_a).
    abuse_by_login = {}
    if rows and db.execute(text("SELECT to_regclass('public.abuse_account_flags')")).scalar():
        plogins = list({r[2] for r in rows if r[2]})
        if plogins:
            arows = db.execute(text("""
                SELECT login, abuse_type, severity, hot, case_id
                FROM abuse_account_flags WHERE login = ANY(:l)
            """), {"l": plogins}).fetchall()
            abuse_by_login = {a[0]: {"type": a[1], "severity": a[2], "hot": a[3], "case_id": a[4]} for a in arows}

    ABUSE_LABELS = {
        'margin_partner': 'Margin-Out Partner', 'bonus_ring': 'Bonus Ring',
        'bonus_cashout': 'Bonus Cash-Out', 'chip_dump': 'Chip Dumping',
        'swap_carry': 'Swap Carry', 'toxic_arb': 'Toxic / Latency',
    }

    def get_abuse_flag(login: int, tx_type: str) -> str:
        # flag withdrawals from any flagged account (money is leaving — hold & review)
        if tx_type not in ("withdrawal", "bonus_withdrawal"):
            return ""
        info = abuse_by_login.get(login)
        if not info:
            return ""
        return ABUSE_LABELS.get(info["type"], info["type"])

    transactions = []
    for r in rows:
        wallet_type, wallet_id = parse_wallet(r[5], r[8])
        net_score = max(0, min(10, int(r[19] or 0)))   # already canonical 0-10
        abuse_flag = get_abuse_flag(r[2], r[3])
        from_acct, to_acct = parse_transfer(r[2], r[5], r[8]) if r[3] == "internal_transfer" else ("", "")

        transactions.append({
            "id":               r[0],
            "deal_id":          r[1],
            "login":            r[2],
            "tx_type":          r[3],
            "amount":           float(r[4] or 0),
            "method":           r[5] or "",
            "method_label":     method_display(r[5]),
            "status":           r[6] or "approved",
            "tx_date":          str(r[7]) if r[7] else "",
            "notes":            r[8] or "",
            "client_name":      r[9] or f"#{r[2]}",
            # r[10] is c.agent (the IB link) — NOT a flag; real flag = open abuse case
            "is_flagged":       r[2] in abuse_by_login,
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
            "from_account":     from_acct,
            "to_account":       to_acct,
            "abuse_flag":       abuse_flag,
            "abuse_severity":   (abuse_by_login.get(r[2]) or {}).get("severity", "") if abuse_flag else "",
            "abuse_hot":        bool((abuse_by_login.get(r[2]) or {}).get("hot")) if abuse_flag else False,
            "abuse_case_id":    (abuse_by_login.get(r[2]) or {}).get("case_id") if abuse_flag else None,
            "currency":         r[21] or "USD",
            "psp_reference":    r[22] or "",
            "approved_at":      str(r[23]) if r[23] else "",
            "ref_id":           r[24],
            "ocr_wallet_id":    r[25] or "",
            "wallet_confidence": r[26] or "",
            "sender_acct":      r[27] or "",
            "sender_block":     r[28] or "",
            "receiver_acct":    r[29] or "",
            "card_name":        r[30] or "",
            "sender_src":       r[31] or "",
            "card_holder":      r[32] or "",
            "has_receipt":      bool(r[33]),
            "country":          r[34] or "",
        })

    return {
        "transactions": transactions,
        "total":        total,
        "page":         page,
        "page_size":    page_size,
        "kpis":         _agg["kpis"],
    }


# ── Receipt image for a transaction ─────────────────────────────────────────────
# The receipt files live on the docs box (S3, 192.248.181.91) under
# /var/lib/broker_docs/deposits/f1|f2. Serve them to back-office via SFTP with a
# small local cache so the details popup can show the actual payment proof.
RECEIPT_CACHE = r"C:\broker-crm\backend\receipt_cache"
DOCS_BOX = ("192.248.181.91", "root", r"C:\Users\Administrator\.ssh\id_ed25519")
_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "jfif": "image/jpeg", "png": "image/png",
         "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp", "pdf": "application/pdf"}


def _fetch_receipt(fn: str, folder: str) -> str:
    """Return a local path for the receipt, pulling it from the docs box on first view."""
    import os
    os.makedirs(RECEIPT_CACHE, exist_ok=True)
    local = os.path.join(RECEIPT_CACHE, os.path.basename(fn))
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return local
    import paramiko
    host, user, keyfile = DOCS_BOX
    key = paramiko.Ed25519Key.from_private_key_file(keyfile)
    tr = paramiko.Transport((host, 22))
    try:
        tr.connect(username=user, pkey=key)
        sftp = paramiko.SFTPClient.from_transport(tr)
        for fo in [folder or "f1", ("f2" if (folder or "f1") == "f1" else "f1")]:
            try:
                sftp.get(f"/var/lib/broker_docs/deposits/{fo}/{os.path.basename(fn)}", local)
                return local
            except FileNotFoundError:
                continue
    finally:
        tr.close()
    raise HTTPException(status_code=404, detail="Receipt file not found on the docs box")


@router.get("/{txn_id}/receipt")
def transaction_receipt(txn_id: int, db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    row = db.execute(text("""
        SELECT tw.receipt_filename, COALESCE(q.folder, z.folder, s.folder, 'f1')
        FROM transaction_wallet tw
        LEFT JOIN pay_qi_card   q ON q.receipt_filename = tw.receipt_filename
        LEFT JOIN pay_zaincash  z ON z.receipt_filename = tw.receipt_filename
        LEFT JOIN pay_sham_cash s ON s.receipt_filename = tw.receipt_filename
        WHERE tw.transaction_id = :t"""), {"t": txn_id}).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No receipt linked to this transaction")
    local = _fetch_receipt(row[0], row[1])
    from fastapi.responses import FileResponse
    ext = row[0].rsplit(".", 1)[-1].lower() if "." in row[0] else ""
    return FileResponse(local, media_type=_MIME.get(ext, "application/octet-stream"))


@router.post("/action")
async def transaction_action(
    data: ActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    role = (getattr(current_user, "role", "") or "").lower()
    if role not in BACKOFFICE_ROLES:
        raise HTTPException(status_code=403, detail="Read-only: only back-office can action transactions")

    tx = db.query(models.Transaction).filter(models.Transaction.deal_id == data.deal_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    _old_status = tx.status
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
    # immutable audit trail for a money-state change (approve/reject a deposit/withdrawal)
    audit.log(db, current_user, f"transaction_{data.action}", "transaction", data.deal_id,
              old=_old_status, new=tx.status, amount=float(getattr(tx, "amount", 0) or 0),
              request=request)
    return {"message": f"Transaction {data.action}d successfully"}


# ── Portal MONEY REQUESTS (deposits + withdrawals) admin queue ──────────────
# Bug: portal deposit requests (incl. bank-wire 'pending_payment') were never shown to admin.
_REQ_DONE = ("completed", "approved", "confirmed", "rejected", "done", "cancelled")
# reject-reason presets (mirror payment_cards_router.REJECT_REASONS) offered in the review popup
REJECT_REASONS = ["Duplicate receipt / transaction ID", "Altered / edited receipt",
                  "Amount does not match", "Wrong receiver card", "Fake / unreadable receipt",
                  "Transaction not found", "Wrong sender name", "Other"]


@router.get("/requests")
def money_requests_admin(kind: str = "", db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    # go-live hardening: the pending queue exposes card numbers/receipts — back-office only.
    if (getattr(current_user, "role", "") or "").lower() not in BACKOFFICE_ROLES | {"director"}:
        raise HTTPException(status_code=403, detail="Back-office only")

    """Pending portal deposit/withdraw requests awaiting back-office action."""
    db.execute(text("""CREATE TABLE IF NOT EXISTS portal_money_requests (
        id SERIAL PRIMARY KEY, client_id INT, login BIGINT, kind VARCHAR(12), amount NUMERIC,
        method VARCHAR(40), status VARCHAR(24) DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())"""))
    db.commit()
    # join the uploaded deposit proof (if any) so back-office can open the receipt/OCR case-file
    # straight from the Transactions page (LEFT JOINs so gateway/no-proof requests still show).
    # Keep REJECTED requests visible (recent 14d) so the row stays with a red "rejected" status
    # instead of vanishing; approved/completed ones drop out (they become real ledger rows).
    # Enrich each uploaded request from the client record so the row is filled the moment a payment
    # is uploaded: sales agent (assigned_agent_id), IB (client's agent login -> ibs), network score,
    # the sender wallet-id + company card the client paid to (deposit_proofs/payment_cards).
    rows = db.execute(text("""
        SELECT r.id, r.client_id, r.login, r.kind, r.amount, r.method, r.status, r.created_at,
               c.name, c.email, c.phone, c.country,
               dp.id AS proof_id, COALESCE(dp.image_path,'')<>'' AS has_image, dp.verdict,
               u.full_name AS agent_name,
               ib.name AS ib_name,
               (SELECT COALESCE(cx.network_score,0) FROM clients cx WHERE cx.login = r.login LIMIT 1) AS net_edges,
               COALESCE(NULLIF(dp.entered_wallet_id,''), NULLIF(dp.ocr_wallet_id,''), '') AS wallet_id,
               COALESCE(NULLIF(pc.card_name,''), '') AS card_name
        FROM portal_money_requests r LEFT JOIN clients c ON c.login = r.login
        LEFT JOIN deposit_proofs dp ON dp.request_id = r.id
        LEFT JOIN payment_cards pc ON pc.id = dp.card_id
        LEFT JOIN users u ON u.id = c.assigned_agent_id
        LEFT JOIN ibs ib ON ib.agent_id = c.agent
        WHERE LOWER(COALESCE(r.status,'')) <> ALL(:hide) AND (:k = '' OR r.kind = :k)
          AND (LOWER(COALESCE(r.status,'')) <> 'rejected' OR r.created_at > NOW() - INTERVAL '14 days')
        ORDER BY r.id DESC LIMIT 500
    """), {"hide": ["completed", "approved", "confirmed", "done", "cancelled"], "k": kind}).fetchall()
    # tx-count per login in ONE grouped query (not a per-row correlated subquery)
    logins = list({r[2] for r in rows if r[2] is not None})
    txc = {}
    if logins:
        for lg, cnt in db.execute(text(
                "SELECT login, count(*) FROM transactions WHERE login = ANY(:ls) GROUP BY login"),
                {"ls": logins}).fetchall():
            txc[lg] = int(cnt)
    return {"requests": [{
        "id": r[0], "client_id": r[1], "login": r[2], "kind": r[3], "amount": float(r[4] or 0),
        "method": r[5] or "", "status": r[6], "date": str(r[7])[:16] if r[7] else None,
        "name": r[8] or "", "email": r[9] or "", "phone": r[10] or "", "country": r[11] or "",
        "proof_id": r[12], "has_image": bool(r[13]), "ai_verdict": r[14],
        "agent_name": r[15] or "", "ib_name": r[16] or "", "network_score": max(0, min(10, int(r[17] or 0))),
        "wallet_id": r[18] or "", "card_name": r[19] or "", "tx_count": txc.get(r[2], 0),
    } for r in rows], "reject_reasons": REJECT_REASONS}


@router.get("/requests/{rid}/detail")
def money_request_detail(rid: int, db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    # go-live hardening: full case-file (receipt, OCR, card data) — back-office only.
    if (getattr(current_user, "role", "") or "").lower() not in BACKOFFICE_ROLES | {"director"}:
        raise HTTPException(status_code=403, detail="Back-office only")
    """Full case-file for a pending/rejected portal request: payment + (optional) receipt/OCR + client +
    the client's recent deposit/withdraw timeline comments. Powers the Transactions review popup."""
    r = db.execute(text("""
        SELECT r.id, r.login, r.kind, r.amount, r.method, r.status, r.created_at,
               c.name, c.email, c.phone,
               dp.id, COALESCE(dp.image_path,'')<>'', dp.ocr_txid, dp.ocr_wallet_id, dp.entered_wallet_id,
               dp.ocr_amount, dp.ocr_date, dp.verdict, dp.reasons, dp.entered_txid,
               pc.number, pc.card_name, pc.account_number
        FROM portal_money_requests r LEFT JOIN clients c ON c.login = r.login
        LEFT JOIN deposit_proofs dp ON dp.request_id = r.id
        LEFT JOIN payment_cards pc ON pc.id = dp.card_id
        WHERE r.id = :i
    """), {"i": rid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    d = {"id": r[0], "login": r[1], "kind": r[2], "amount": float(r[3] or 0), "method": r[4] or "",
         "status": r[5] or "pending_admin_review", "date": str(r[6])[:16] if r[6] else None,
         "name": r[7] or "", "email": r[8] or "", "phone": r[9] or "",
         "proof_id": r[10], "has_image": bool(r[11]), "ocr_txid": r[12], "ocr_wallet_id": r[13],
         "entered_wallet_id": r[14], "ocr_amount": float(r[15]) if r[15] is not None else None,
         "ocr_date": r[16], "verdict": r[17], "reasons": r[18], "entered_txid": r[19],
         "company_card": r[20] or "", "company_card_name": r[21] or "", "company_account": r[22] or ""}
    # recent money-related comments on this client's timeline (deposit + withdraw), newest first
    try:
        comments = db.execute(text("""
            SELECT a.action, a.note, a.created_at, u.full_name
            FROM call_actions a LEFT JOIN users u ON u.id = a.agent_id
            WHERE a.login = :l AND (a.action ILIKE '%deposit%' OR a.action ILIKE '%withdraw%'
                                    OR a.note ILIKE '%deposit%' OR a.note ILIKE '%withdraw%')
            ORDER BY a.created_at DESC LIMIT 10
        """), {"l": d["login"]}).fetchall()
        d["comments"] = [{"action": c[0], "note": c[1] or "", "date": str(c[2])[:16], "by": c[3] or ""} for c in comments]
    except Exception:
        db.rollback(); d["comments"] = []
    return d


@router.post("/requests/{rid}/action")
def money_request_action(rid: int, data: dict, request: Request, db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    """Approve (-> records a real ledger transaction) or reject a portal money request."""
    role = (getattr(current_user, "role", "") or "").lower()
    if role not in BACKOFFICE_ROLES:
        raise HTTPException(status_code=403, detail="Only back-office can action requests")
    r = db.execute(text("SELECT client_id, login, kind, amount, method, status FROM portal_money_requests WHERE id=:i"),
                   {"i": rid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    act = (data.get("action") or "").lower()
    reason = (data.get("reason") or "").strip()
    login, kind, amount, method = r[1], r[2], float(r[3] or 0), r[4] or "Portal"
    uid = getattr(current_user, "id", None)
    who = getattr(current_user, "full_name", None) or getattr(current_user, "email", None) or "back-office"

    def _comment(action_key, note):
        # auto-add a timeline comment on the client's page (best-effort; never blocks the action)
        try:
            db.execute(text("""INSERT INTO call_actions (login, agent_id, action, note, created_at)
                VALUES (:l,:a,:k,:n,NOW())"""), {"l": login, "a": uid, "k": action_key, "n": note})
        except Exception:
            db.rollback()

    if act == "reject":
        db.execute(text("UPDATE portal_money_requests SET status='rejected' WHERE id=:i"), {"i": rid})
        # keep the linked deposit proof in sync
        db.execute(text("UPDATE deposit_proofs SET verdict='reject', reasons=:rs WHERE request_id=:i"),
                   {"i": rid, "rs": (f"Rejected: {reason}" if reason else "Rejected")})
        _comment(f"{kind}_rejected",
                 f"{kind.title()} ${amount:,.2f} via {method} REJECTED by {who} — {reason or 'no reason given'}")
        db.commit()
        audit.log(db, current_user, f"{kind}_request_reject", "money_request", rid,
                  old=r[5], new=f"rejected: {reason or 'no reason'}", amount=amount, request=request)
        return {"ok": True, "status": "rejected"}
    if act == "approve":
        # record it in the ledger so it shows + counts (deal_id offset 9e9 avoids MT/legacy collision)
        tt = "deposit" if kind == "deposit" else "withdrawal"
        db.execute(text("""INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method,
              status, notes, tx_date, tx_month, created_at, updated_at)
            VALUES (:d,:l,:t,:a,'USD',:m,'approved','Portal request approved',
              to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'), to_char(NOW(),'YYYY-MM'), NOW(), NOW())
            ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING"""),
            {"d": 9_000_000_000 + rid, "l": login, "t": tt, "a": amount, "m": method})
        db.execute(text("UPDATE portal_money_requests SET status='approved' WHERE id=:i"), {"i": rid})
        db.execute(text("UPDATE deposit_proofs SET verdict='approve' WHERE request_id=:i"), {"i": rid})
        _comment(f"{kind}_approved", f"{kind.title()} ${amount:,.2f} via {method} APPROVED by {who}")
        db.commit()
        audit.log(db, current_user, f"{kind}_request_approve", "money_request", rid,
                  old=r[5], new="approved", amount=amount, request=request)
        # TODO: push real MT credit/debit via the bridge once enabled
        return {"ok": True, "status": "approved", "note": "Recorded in ledger (simulation — no live MT move)"}
    return {"ok": False, "error": "unknown action"}


# ── Pending withdrawals queue + per-method statistics (ticket #16) ──
@router.get("/pending-withdrawals")
def pending_withdrawals(db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    PENDING = ("pending", "processing", "requested", "review", "pending_admin_review", "on_hold")
    # the pending queue (withdrawals not yet performed)
    items = db.execute(text("""
        SELECT t.tx_date, t.login, t.amount, COALESCE(NULLIF(t.method,''),'Other') AS method, t.status
        FROM transactions t
        WHERE t.tx_type='withdrawal' AND LOWER(COALESCE(t.status,'')) = ANY(:st)
        ORDER BY t.tx_date DESC NULLS LAST LIMIT 200
    """), {"st": list(PENDING)}).fetchall()
    pend_method = db.execute(text("""
        SELECT COALESCE(NULLIF(method,''),'Other') AS method, COUNT(*), COALESCE(SUM(amount),0)
        FROM transactions
        WHERE tx_type='withdrawal' AND LOWER(COALESCE(status,'')) = ANY(:st)
        GROUP BY 1 ORDER BY 3 DESC
    """), {"st": list(PENDING)}).fetchall()
    # also include portal withdrawal requests that aren't finalised yet
    try:
        prows = db.execute(text("""
            SELECT COALESCE(NULLIF(method,''),'Portal') AS method, COUNT(*), COALESCE(SUM(amount),0)
            FROM portal_money_requests
            WHERE kind='withdraw' AND LOWER(COALESCE(status,'')) NOT IN ('completed','approved','confirmed','rejected','done')
            GROUP BY 1
        """)).fetchall()
    except Exception:
        db.rollback(); prows = []

    merged = {}
    for m, c, v in list(pend_method) + list(prows):
        e = merged.setdefault(m, {"method": m, "count": 0, "value": 0.0})
        e["count"] += int(c or 0); e["value"] += float(v or 0)
    by_method = sorted(merged.values(), key=lambda x: x["value"], reverse=True)
    total_count = sum(x["count"] for x in by_method)
    total_value = round(sum(x["value"] for x in by_method), 2)

    # per-method statistics across ALL withdrawals (so the stats are useful even with 0 pending)
    allm = db.execute(text("""
        SELECT COALESCE(NULLIF(method,''),'Other') AS method, COUNT(*), COALESCE(SUM(amount),0)
        FROM transactions WHERE tx_type='withdrawal'
        GROUP BY 1 ORDER BY 3 DESC
    """)).fetchall()
    all_by_method = [{"method": method_display(m), "count": int(c or 0), "value": round(float(v or 0), 2)} for m, c, v in allm]

    # breakdown by transaction TYPE — deposit / withdrawal / internal transfer / bonus (ticket #16)
    typ = db.execute(text("""
        SELECT tx_type, COUNT(*), COALESCE(SUM(amount),0)
        FROM transactions GROUP BY tx_type ORDER BY 3 DESC
    """)).fetchall()
    TYPE_LABEL = {"deposit": "Deposits", "withdrawal": "Withdrawals",
                  "internal_transfer": "Internal transfers", "bonus_deposit": "Bonus in",
                  "bonus_withdrawal": "Bonus out", "credit": "Credit"}
    by_type = [{"type": t, "label": TYPE_LABEL.get(t, (t or "other").replace("_", " ").title()),
                "count": int(c or 0), "value": round(float(v or 0), 2)} for t, c, v in typ]

    return {
        "pending": {
            "total_count": total_count,
            "total_value": total_value,
            "by_method": [{"method": method_display(x["method"]), "count": x["count"], "value": round(x["value"], 2)} for x in by_method],
            "items": [{
                "date": str(r[0])[:16] if r[0] else None, "login": r[1],
                "amount": float(r[2] or 0), "method": r[3], "status": r[4],
            } for r in items],
        },
        "by_type": by_type,
        "all_by_method": all_by_method,
        "all_total": {"count": sum(x["count"] for x in all_by_method),
                      "value": round(sum(x["value"] for x in all_by_method), 2)},
    }
