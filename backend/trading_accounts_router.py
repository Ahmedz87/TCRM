from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, String
from database import get_db
from auth import get_current_user
import models
import rbac

router = APIRouter(prefix="/trading-accounts", tags=["Trading Accounts"])


def get_ib_display(agent: int, db: Session) -> dict:
    """Get IB name and code from ibs table."""
    if not agent:
        return {"ib_name": "", "ib_code": "", "ib_display": ""}
    try:
        ib = db.query(models.IB).filter(models.IB.agent_id == agent).first()
        if ib:
            return {
                "ib_name":    ib.name,
                "ib_code":    ib.ib_code,
                # IB column shows the NAME ONLY (code was too long); ib_code stays available separately
                "ib_display": ib.name or (ib.ib_code or ""),
            }
    except Exception:
        db.rollback()   # a failed query poisons the session; recover it for later queries
    return {"ib_name": "", "ib_code": str(agent), "ib_display": f"#{agent}"}


import re as _re

# roles allowed to see A/B book (dealing-desk info) — sales/everyone must NOT see it
_BOOK_ROLES = {"admin", "backoffice", "director", "dealer", "validation"}


def decode_group(group: str, platform: str, acct_type: str) -> dict:
    """Decode an MT group into the human attributes the desk cares about:
        type     : Standard / Cent / Zero / VIP / FIX / IB / Contest / Demo / ECN
        platform : MT4 / MT5
        islamic  : the '-IS' token means swap-free (Islamic)
        book     : leading digit of the retail group — 1 = A-book, 2 = B-book (dealing desk only)
        is_real  : real/live money account (Demo/Contest are not)
    NOTE: the real type lives in the MT server group (STD\\2-STD-IS, Cent\\2-Cent-IS, VIP\\2-VIP-IS,
    ...). TradeSoft instead labels every account '{1-7}ECN', which is a routing/tier code that does
    NOT map to the account type (2ECN -> Standard/Cent/Zero/VIP all mixed) — so we only fall back to
    'ECN' when the group carries no real MT type yet (account not seen on MT). The book digit is only
    trusted on real MT retail groups, never on the TradeSoft {N}ECN label."""
    plat = "MT4" if (platform or "").upper() == "MT4" else "MT5"
    seg = (group or acct_type or "").replace("/", "\\").split("\\")[-1]
    U = seg.upper()
    tokens = [t for t in _re.split(r"[^A-Z0-9]+", U) if t]
    islamic = "IS" in tokens
    real = True
    if   "DEMO" in U:                      typ = "Demo"; real = False
    elif "CONTEST" in U:                   typ = "Contest"; real = False
    elif "VIP" in U:                       typ = "VIP"
    elif "FIX" in U:                       typ = "FIX"
    elif "CENT" in U:                      typ = "Cent"
    elif "ZERO" in U:                      typ = "Zero"
    elif "IB" in tokens or "IB-" in U:     typ = "IB"
    elif "STD" in U or "STANDARD" in U:    typ = "Standard"
    elif "ECN" in U:                       typ = ""      # TradeSoft {N}ECN = routing label, NOT a real
    #        type. Real type is unknown until the account is seen on MT, so show no type (not "ECN").
    else:                                  typ = ""      # unknown group -> leave blank rather than guess
    book = ""
    if typ in ("Standard", "Cent", "Zero", "VIP", "FIX"):
        m = _re.match(r"^(\d)", seg)
        if m:
            book = {"1": "A", "2": "B"}.get(m.group(1), "")
    return {"type": typ, "platform": plat, "islamic": islamic, "is_real": real, "book": book}


def get_agent_name(login: int, db: Session) -> str:
    """Get sales agent name from assignment."""
    try:
        a = db.query(models.ClientAssignment).filter(
            models.ClientAssignment.login == login
        ).first()
        if a:
            user = db.query(models.User).filter(models.User.id == a.agent_id).first()
            if user:
                return user.full_name
    except Exception:
        db.rollback()
    return ""


def get_created_at(login: int, reg_date: str, db: Session) -> str:
    """Get first deal date as created_at."""
    try:
        d = db.query(models.Deal).filter(
            models.Deal.login == login
        ).order_by(models.Deal.deal_time.asc()).first()
        if d and d.deal_date:
            return d.deal_date
    except Exception:
        db.rollback()
    return reg_date or ""


def account_to_dict(ta: models.TradingAccount, db: Session, full: bool = False) -> dict:
    """Convert TradingAccount to dict."""
    ib_info    = get_ib_display(ta.agent, db)
    agent_name = get_agent_name(ta.login, db)
    created_at = get_created_at(ta.login, ta.reg_date, db)

    # CID from identifiers if missing
    cid = ta.cid or ""
    if not cid:
        try:
            rec = db.query(models.AccountIdentifier).filter(
                models.AccountIdentifier.login == ta.login,
                models.AccountIdentifier.identifier_type == "cid"
            ).first()
            if rec:
                cid = rec.identifier_value
        except Exception:
            db.rollback()

    # Get live financial data from clients table (more up to date)
    raw = db.query(models.Client).filter(models.Client.login == ta.login).first()
    equity      = (raw.equity if raw else None) or ta.equity or 0
    margin_level= (raw.margin_level if raw else None) or ta.margin_level or 0
    free_margin = (raw.free_margin if raw else None) or ta.free_margin or 0
    credit      = (raw.credit if raw else None) or ta.credit or 0
    balance     = (raw.balance if raw else None) or ta.balance or 0

    base = {
        "login":        ta.login,
        "name":         ta.name or "",
        "email":        ta.email or "",
        "phone":        ta.phone or "",
        "group_name":   ta.group_name or "",
        "account_type": ta.account_type or "live",
        "is_islamic":   ta.is_islamic or False,
        "is_ib":        ta.is_ib or False,
        "leverage":     ta.leverage or 100,
        "balance":      balance,
        "equity":       equity,
        "credit":       credit,
        "margin_level": margin_level,
        "free_margin":  free_margin,
        "country":      ta.country or "",
        "city":         ta.city or "",
        "last_ip":      ta.last_ip or "",
        "cid":          cid,
        "mqid":         ta.mqid or 0,
        "agent":        ta.agent or 0,
        **ib_info,
        "agent_name":   agent_name,
        "reg_date":     ta.reg_date or "",
        "created_at":   created_at,
        "total_deposits":    ta.total_deposits or 0,
        "total_withdrawals": ta.total_withdrawals or 0,
        "net_deposit":       ta.net_deposit or 0,
        "total_volume":      ta.total_volume or 0,
        "total_trades":      ta.total_trades or 0,
        "is_active":    ta.is_active,
        "kyc_status":   ta.kyc_status or "pending",
        "risk_score":   ta.risk_score or "low",
        "source":       ta.source or "none",
    }

    if full:
        # All identifiers
        all_ips, all_cids, all_mqids = [], [], []
        try:
            ids = db.query(models.AccountIdentifier).filter(
                models.AccountIdentifier.login == ta.login
            ).all()
            all_ips   = [i.identifier_value for i in ids if i.identifier_type == "ip"]
            all_cids  = [i.identifier_value for i in ids if i.identifier_type == "cid"]
            all_mqids = [i.identifier_value for i in ids if i.identifier_type == "mqid"]
        except Exception:
            db.rollback()

        # Network connections
        connections = []
        try:
            edges = db.query(models.NetworkEdge).filter(
                or_(
                    models.NetworkEdge.login_a == ta.login,
                    models.NetworkEdge.login_b == ta.login,
                )
            ).limit(20).all()
            for e in edges:
                other_login = e.login_b if e.login_a == ta.login else e.login_a
                other = db.query(models.TradingAccount).filter(
                    models.TradingAccount.login == other_login
                ).first()
                if other:
                    connections.append({
                        "login":   other_login,
                        "name":    other.name or f"#{other_login}",
                        "reasons": [e.reason.upper()],
                        "value":   e.value or "",
                        "risk":    other.risk_score or "low",
                    })
        except Exception:
            db.rollback()

        # Deposits & withdrawals from deals
        deposits_list, withdrawals_list = [], []
        open_positions, trade_history   = [], []
        try:
            # Extract payment method from comment
            def get_method(comment):
                if comment and " - " in comment:
                    parts = comment.split(" - ")
                    if len(parts) >= 3:
                        return parts[1].strip()
                return ""

            # Real deposits from transactions table
            deps = db.query(models.Transaction).filter(
                models.Transaction.login == ta.login,
                models.Transaction.tx_type == "deposit"
            ).order_by(models.Transaction.tx_date.desc()).limit(100).all()
            deposits_list = [{
                "deal_id": d.deal_id, "amount": d.amount or 0,
                "date": d.tx_date, "method": d.method or get_method(d.notes),
                "comment": d.notes or "", "status": d.status or "approved"
            } for d in deps]

            # Real withdrawals
            withs = db.query(models.Transaction).filter(
                models.Transaction.login == ta.login,
                models.Transaction.tx_type == "withdrawal"
            ).order_by(models.Transaction.tx_date.desc()).limit(100).all()
            withdrawals_list = [{
                "deal_id": d.deal_id, "amount": d.amount or 0,
                "date": d.tx_date, "method": d.method or get_method(d.notes),
                "comment": d.notes or "", "status": d.status or "approved"
            } for d in withs]

            # Internal transfers
            transfers = db.query(models.Transaction).filter(
                models.Transaction.login == ta.login,
                models.Transaction.tx_type == "internal_transfer"
            ).order_by(models.Transaction.tx_date.desc()).limit(100).all()
            internal_list = [{
                "deal_id": d.deal_id, "amount": d.amount or 0,
                "date": d.tx_date, "comment": d.notes or "", "status": "approved"
            } for d in transfers]

            # Bonuses
            bonus_deps = db.query(models.Transaction).filter(
                models.Transaction.login == ta.login,
                models.Transaction.tx_type.in_(["bonus_deposit","bonus_withdrawal"])
            ).order_by(models.Transaction.tx_date.desc()).limit(100).all()
            bonuses_list = [{
                "deal_id": d.deal_id, "amount": d.amount or 0,
                "tx_type": d.tx_type,
                "date": d.tx_date, "comment": d.notes or ""
            } for d in bonus_deps]

            # Open positions (entry=0)
            opens = db.query(models.Deal).filter(
                models.Deal.login == ta.login,
                models.Deal.deal_type == "trade",
                models.Deal.entry == 0
            ).order_by(models.Deal.deal_time.desc()).limit(100).all()
            open_positions = [{
                "ticket":     d.deal_id,
                "symbol":     d.symbol,
                "direction":  d.direction or "buy",
                "type":       d.direction or "buy",
                "volume":     round((d.volume or 0) / 10000, 2),
                "open_price": d.price or 0,
                "current":    d.price or 0,
                "profit":     float(d.profit or 0),
                "pnl":        float(d.profit or 0),
                "swap":       float(d.swap or 0),
                "commission": float(d.commission or 0),
                "open_time":  d.deal_date,
                "open_timestamp": d.deal_time or 0,
            } for d in opens]

            # Trade history (entry=1) with open time lookup
            hist = db.query(models.Deal).filter(
                models.Deal.login == ta.login,
                models.Deal.deal_type == "trade",
                models.Deal.entry == 1
            ).order_by(models.Deal.deal_time.desc()).limit(500).all()

            trade_history = []
            for d in hist:
                # Find matching open deal by position ID
                open_deal = db.query(models.Deal).filter(
                    models.Deal.login == ta.login,
                    models.Deal.deal_type == "trade",
                    models.Deal.entry == 0,
                    models.Deal.symbol == d.symbol,
                    models.Deal.deal_time < (d.deal_time or 0)
                ).order_by(models.Deal.deal_time.desc()).first()

                open_time = open_deal.deal_time if open_deal else None
                close_time = d.deal_time

                # Duration in seconds
                duration_secs = (close_time - open_time) if open_time and close_time else 0

                trade_history.append({
                    "ticket":      d.deal_id,
                    "symbol":      d.symbol,
                    "direction":   d.direction or "buy",
                    "volume":      round((d.volume or 0) / 10000, 2),
                    "open_price":  open_deal.price if open_deal else 0,
                    "close_price": d.price or 0,
                    "profit":      d.profit or 0,
                    "commission":  d.commission or 0,
                    "swap":        d.swap or 0,
                    "open_time":   open_deal.deal_date if open_deal else d.deal_date,
                    "close_time":  d.deal_date,
                    "open_timestamp":  open_time,
                    "close_timestamp": close_time,
                    "duration_secs":   duration_secs,
                })
        except Exception:
            db.rollback()

        # Calculate total floating PnL = equity - balance
        total_floating = round(float(ta.equity or ta.balance or 0) - float(ta.balance or 0), 2)
        # Distribute floating PnL by volume weight across open positions
        total_volume = sum(p.get("volume", 0) for p in open_positions) or 1
        for p in open_positions:
            vol_weight = (p.get("volume", 0) / total_volume) if total_volume > 0 else 0
            p["pnl"] = round(total_floating * vol_weight, 2)

        base.update({
            "all_ips":          all_ips,
            "all_cids":         all_cids,
            "all_mqids":        all_mqids,
            "network_connections": connections,
            "deposits_list":    deposits_list,
            "withdrawals_list": withdrawals_list,
            "internal_list":    internal_list,
            "bonuses_list":     bonuses_list,
            "open_positions":   open_positions,
            "trade_history":    trade_history,
        })

    return base


@router.get("")
def get_trading_accounts(
    page:      int   = Query(1, ge=1),
    page_size: int   = Query(20, ge=1, le=500),
    search:    str   = Query(""),
    sort:      str   = Query("balance"),
    acc_type:  str   = Query(""),
    archived:  str   = Query(""),    # ''=active only, 'archived'=Archive tab, 'all'=both
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from sqlalchemy import text as sqlt
    where_parts = ["1=1"]
    params = {}
    if search:
        where_parts.append("(CAST(ta.login AS TEXT) LIKE :s OR ta.name ILIKE :s OR ta.phone ILIKE :s OR ta.group_name ILIKE :s OR ta.last_ip LIKE :s)")
        params["s"] = f"%{search}%"
    if acc_type:
        where_parts.append("ta.account_type = :acc_type")
        params["acc_type"] = acc_type
    # Archive filter — subquery form so the (un-joined) COUNT query works too. MT-archived
    # accounts (clients.archived_at set) are hidden from the default list and shown in their tab.
    if archived == "archived":
        where_parts.append("ta.login IN (SELECT login FROM clients WHERE archived_at IS NOT NULL)")
    elif archived == "all":
        pass
    else:
        where_parts.append("ta.login NOT IN (SELECT login FROM clients WHERE archived_at IS NOT NULL)")
    # Role-based visibility: restrict to accounts of the user's own/team clients
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where_parts.append("ta.login IN (SELECT login FROM clients WHERE assigned_agent_id = ANY(:rbac_agent_ids))")
            params["rbac_agent_ids"] = _scope
        else:
            where_parts.append("FALSE")
    where = " AND ".join(where_parts)
    
    sort_col = "ta.balance DESC"
    if sort == "equity":    sort_col = "ta.equity DESC NULLS LAST"
    # "new" = most recently added. reg_date is free-text/NULL for TradeSoft-imported accounts, so
    # sort by created_at (import time) so recent MT5 accounts actually surface at the top.
    elif sort == "new":     sort_col = "ta.created_at DESC NULLS LAST"
    elif sort == "name":    sort_col = "ta.name ASC NULLS LAST"
    elif sort == "login":   sort_col = "ta.login DESC"
    elif sort == "deposit": sort_col = "ta.total_deposits DESC NULLS LAST"
    elif sort == "margin":  sort_col = "ta.margin_level DESC NULLS LAST"
    elif sort == "balance": sort_col = "ta.balance DESC NULLS LAST" 
    total = db.execute(sqlt(f"SELECT COUNT(*) FROM trading_accounts ta WHERE {where}"), params).scalar() or 0
    sql = f"""
        SELECT ta.login, ta.name, ta.email, ta.phone, ta.group_name,
            ta.account_type, ta.is_islamic, ta.is_ib, ta.leverage,
            ta.balance, ta.equity, ta.credit, ta.margin_level, ta.free_margin,
            ta.country, ta.city, ta.last_ip, ta.cid, ta.mqid,
            ta.agent, ta.reg_date, ta.is_active, ta.kyc_status, ta.risk_score,
            ta.total_deposits, ta.total_withdrawals, ta.net_deposit,
            ta.total_volume, ta.total_trades,
            ib.name as ib_name, ib.ib_code as ib_code,
            u.full_name as agent_name,
            (SELECT MIN(tx_date) FROM transactions
             WHERE login=ta.login AND tx_type='deposit' LIMIT 1) as credit_at,
            c.archived_at, c.archive_reason, c.created_at, ta.platform
        FROM trading_accounts ta
        LEFT JOIN ibs ib ON ib.agent_id = ta.agent
        LEFT JOIN clients c ON c.login = ta.login
        LEFT JOIN users u ON u.id = c.assigned_agent_id
        WHERE {where}
        ORDER BY {sort_col}
        LIMIT :limit OFFSET :offset
    """
    try:
        rows = db.execute(sqlt(sql), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()
    except Exception as e:
        print(f"TRADING ACCOUNTS SQL ERROR: {e}")
        raise
    show_book = (getattr(current_user, "role", "") or "").lower() in _BOOK_ROLES
    accounts = []
    for r in rows:
        _dg = decode_group(r[4], (r[36] if len(r) > 36 else ""), r[5])
        accounts.append({
            "login": r[0], "name": r[1] or "", "email": r[2] or "",
            "phone": r[3] or "", "group_name": r[4] or "",
            "account_type": _dg["type"], "is_islamic": _dg["islamic"],
            "is_ib": r[7] or False, "leverage": r[8] or 100,
            "balance": float(r[9] or 0), "equity": float(r[10] or 0),
            "credit": float(r[11] or 0), "margin_level": float(r[12] or 0),
            "free_margin": float(r[13] or 0), "country": r[14] or "",
            "city": r[15] or "", "last_ip": r[16] or "", "cid": r[17] or "",
            "mqid": r[18] or 0, "agent": r[19] or 0, "reg_date": r[20] or "",
            "is_active": r[21] or False, "kyc_status": r[22] or "pending",
            "risk_score": r[23] or "low",
            "total_deposits": float(r[24] or 0),
            "total_withdrawals": float(r[25] or 0),
            "net_deposit": float(r[26] or 0),
            "total_volume": float(r[27] or 0),
            "total_trades": r[28] or 0,
            "ib_name": r[29] or "", "ib_code": r[30] or "",
            # IB column = name only (the code made the column too long)
            "ib_display": (r[29] or ""),
            "agent_name": r[31] or "", "credit_at": str(r[32]) if len(r)>32 and r[32] else "",
            "archived": bool(r[33]) if len(r) > 33 and r[33] else False,
            "archived_at": str(r[33]) if len(r) > 33 and r[33] else "",
            "archive_reason": (r[34] if len(r) > 34 else "") or "",
            # real creation date (import/registration) so the "Created" column populates for
            # TradeSoft accounts too (their reg_date text is empty; created_at is always set)
            "created_at": str(r[35]) if len(r) > 35 and r[35] else "",
            # decoded account attributes shown to everyone: platform + Real/Demo + Islamic (+ type above)
            "platform": _dg["platform"], "is_real": _dg["is_real"],
            # A/B book is dealing-desk info — only sent to privileged roles (sales must not see it)
            "book": (_dg["book"] if show_book else ""),
        })
    return {"accounts": accounts, "total": total, "page": page, "page_size": page_size}


@router.post("/{login}/archive")
def archive_account(login: int, data: dict = None,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """Manually archive / un-archive ONE trading account (desk override). Archiving only sets
    clients.archived_at — all history, IB/sales commission and loyalty stay; the portal blocks
    new deposits/transfers for it. Pass {archived:false} to restore."""
    from sqlalchemy import text as sqlt
    archived = True if data is None else bool(data.get("archived", True))
    if archived:
        db.execute(sqlt("UPDATE clients SET archived_at=COALESCE(archived_at,NOW()), "
                        "archive_reason=COALESCE(archive_reason,'manual') WHERE login=:l"), {"l": login})
    else:
        db.execute(sqlt("UPDATE clients SET archived_at=NULL, archive_reason=NULL WHERE login=:l"), {"l": login})
    db.commit()
    return {"ok": True, "login": login, "archived": archived}


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Real KPI stats for the trading accounts page (role-scoped)."""
    from sqlalchemy import func
    _scope = rbac.scope_agent_ids(db, current_user)
    _sublogins = None
    if _scope is not None:
        _sublogins = db.query(models.Client.login).filter(
            models.Client.assigned_agent_id.in_(_scope or [-1]))
    # exclude ARCHIVED accounts from the KPIs (matches the default list) — otherwise the totals
    # include the ~140k archived TradeSoft/ECN accounts whose balances are unverified/fake ($34B+),
    # and the tradesoft_test accounts we just hid. KPIs must reflect only live, listed accounts.
    _arch = db.query(models.Client.login).filter(models.Client.archived_at.isnot(None))
    def q():
        qq = db.query(models.TradingAccount).filter(~models.TradingAccount.login.in_(_arch))
        if _sublogins is not None:
            qq = qq.filter(models.TradingAccount.login.in_(_sublogins))
        return qq
    total     = q().count()
    active    = q().filter(models.TradingAccount.is_active == True).count()
    with_bal  = q().filter(models.TradingAccount.balance > 0).count()
    zero_bal  = q().filter(models.TradingAccount.balance <= 0).count()
    total_bal = q().with_entities(func.sum(models.TradingAccount.balance)).scalar() or 0
    total_eq  = q().with_entities(func.sum(models.TradingAccount.equity)).scalar() or 0
    total_cr  = q().with_entities(func.sum(models.TradingAccount.credit)).scalar() or 0
    # By type
    by_type = {}
    for t in ["standard","zero","cent","vip","fix","ib","demo"]:
        by_type[t] = q().filter(models.TradingAccount.account_type == t).count()
    return {
        "total":       total,
        "active":      active,
        "with_balance": with_bal,
        "zero_balance": zero_bal,
        "total_balance": round(total_bal, 2),
        "total_equity":  round(total_eq, 2),
        "total_credit":  round(total_cr, 2),
        "by_type":     by_type,
    }


@router.get("/margin-watch")
def margin_watch(
    threshold: float = Query(110.0, ge=0, le=100000),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """#210: accounts approaching a margin call — margin level below `threshold` (default 110%).
    Powers the floating margin-watch widget. Returns the at-risk list (worst first) plus
    `data_as_of` = the last time the equity/margin feed refreshed, so the desk can see how fresh
    the numbers are (the MT bridge polls live equity/margin every 30s)."""
    from sqlalchemy import text as sqlt
    _scope = rbac.scope_agent_ids(db, current_user)
    params = {"th": threshold}
    scope_sql = ""
    if _scope is not None:
        # non-all-access: only this viewer's team's accounts
        scope_sql = (" AND ta.login IN (SELECT login FROM clients WHERE assigned_agent_id = ANY(:aids))")
        params["aids"] = _scope or [-1]
    rows = db.execute(sqlt(f"""
        SELECT ta.login, ta.name, ta.balance, ta.equity, ta.margin_level, ta.free_margin,
               ta.credit, ta.country, ta.phone, ta.platform, ta.updated_at,
               u.full_name AS agent_name
        FROM trading_accounts ta
        LEFT JOIN clients c ON c.login = ta.login
        LEFT JOIN users u ON u.id = c.assigned_agent_id
        WHERE ta.margin_level IS NOT NULL AND ta.margin_level > 0 AND ta.margin_level < :th
          AND ta.equity > 0
          AND ta.is_active IS NOT FALSE
          {scope_sql}
        ORDER BY ta.margin_level ASC
        LIMIT 500
    """), params).fetchall()
    data_as_of = db.execute(sqlt(
        "SELECT MAX(updated_at) FROM trading_accounts WHERE margin_level > 0 AND equity > 0")).scalar()
    return {
        "threshold": threshold,
        "count": len(rows),
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "accounts": [{
            "login": r[0], "name": r[1] or "", "balance": float(r[2] or 0),
            "equity": float(r[3] or 0), "margin_level": float(r[4] or 0),
            "free_margin": float(r[5] or 0), "credit": float(r[6] or 0),
            "country": r[7] or "", "phone": r[8] or "", "platform": r[9] or "",
            "updated_at": r[10].isoformat() if r[10] else None,
            "agent_name": r[11] or "",
        } for r in rows],
    }


@router.get("/{login}")
def get_trading_account(
    login: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from fastapi import HTTPException
    ta = db.query(models.TradingAccount).filter(
        models.TradingAccount.login == login
    ).first()
    if not ta:
        raise HTTPException(status_code=404, detail="Account not found")
    # Role-based visibility: only own/team accounts (by the client that owns this login)
    cl = db.query(models.Client).filter(models.Client.login == login).first()
    if not rbac.can_see_agent(db, current_user, cl.assigned_agent_id if cl else None):
        raise HTTPException(status_code=403, detail="Not authorized to view this account")
    return account_to_dict(ta, db, full=True)


@router.post("/action")
def save_action(
    login:   int,
    action:  str,
    note:    str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        db.add(models.CallAction(
            login=login, agent_id=current_user.id,
            action=action, note=note,
        ))
        db.commit()
    except Exception:
        db.rollback()   # failed commit must roll back or the session stays poisoned
    return {"message": "Action saved"}
