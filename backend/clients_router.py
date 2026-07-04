"""
clients_router.py
Groups trading accounts by phone number to show unique clients.
All changes included:
- Group by phone â†’ unique clients
- Real balance, deposits, withdrawals aggregated across all accounts
- IB name display
- First deposit date + amount
- Deposit count
- Last activity (client actions from transactions)
- Last comment (sales agent actions from call_actions)
- Network score (IP + CID + City + IB + Phone prefix)
- Priority score calculation
- Real data inside client detail (deposits, withdrawals, accounts, calls, network)
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/clients", tags=["Clients"])


class ActionCreate(BaseModel):
    login:            int
    action:           str
    note:             str = ""
    call_later_days:  int = 0
    call_later_hours: int = 0
    pass_to_manager:  bool = False


def calc_priority_score(c: dict, settings: dict) -> int:
    """Calculate client priority score based on configurable settings."""
    score = 0
    now = datetime.now(timezone.utc)

    # --- Overdue contact ---
    last_action_date = c.get("last_action_date", "")
    if last_action_date:
        try:
            lad = datetime.fromisoformat(str(last_action_date).replace("Z", "+00:00"))
            if lad.tzinfo is None:
                lad = lad.replace(tzinfo=timezone.utc)
            days_since = (now - lad).days
            if days_since >= 14:
                score += settings.get("no_contact_14d", 30)
            elif days_since >= 7:
                score += settings.get("no_contact_7d", 15)
        except:
            score += settings.get("no_contact_14d", 30)
    else:
        score += settings.get("no_contact_14d", 30)

    # --- Deposit triggers ---
    total_dep = float(c.get("total_deposit", 0) or 0)
    balance   = float(c.get("balance", 0) or 0)

    if balance > 0 and total_dep == 0:
        score += settings.get("no_deposit_ever", 25)

    if total_dep > 0:
        last_dep_date = c.get("last_activity_date", "")
        if last_dep_date and c.get("last_activity_type") in ("deposit",):
            try:
                ldd = datetime.fromisoformat(str(last_dep_date).replace("Z", "+00:00"))
                if ldd.tzinfo is None:
                    ldd = ldd.replace(tzinfo=timezone.utc)
                if (now - ldd).days >= 21:
                    score += settings.get("no_deposit_21d", 20)
            except:
                pass

    first_dep_date = c.get("first_deposit_date", "")
    if first_dep_date:
        try:
            fdd = datetime.fromisoformat(str(first_dep_date).replace("Z", "+00:00"))
            if fdd.tzinfo is None:
                fdd = fdd.replace(tzinfo=timezone.utc)
            if (now - fdd).days <= 7:
                score += settings.get("first_dep_7d", 20)
        except:
            pass

    # --- Account health ---
    if balance > 0:
        score += settings.get("has_balance", 10)

    margin = float(c.get("margin_level", 0) or 0)
    if 0 < margin < 50:
        score += settings.get("margin_below_50", 40)
    elif 50 <= margin < 100:
        score += settings.get("margin_below_100", 25)

    return min(score, 100)


def get_score_settings(db: Session) -> dict:
    try:
        settings = db.query(models.ScoreSettings).all()
        return {s.trigger: s.points for s in settings}
    except:
        return {}



def _get_last_activity_type(last_dep, last_with):
    """Return the type of the most recent activity."""
    if last_dep and last_with:
        return 'deposit' if str(last_dep) >= str(last_with) else 'withdrawal'
    if last_dep: return 'deposit'
    if last_with: return 'withdrawal'
    return ''

@router.get("")
async def get_clients(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100000),
    sort:      str = Query("balance"),
    search:    str = Query(""),
    country:   str = Query(""),
    city:      str = Query(""),
    ib:        str = Query(""),
    agent:     str = Query(""),
    kyc:       str = Query(""),
    risk:      str = Query(""),
    sources:   str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    base_where = "c.group_name NOT ILIKE '%retail%' AND c.group_name NOT ILIKE '%demo%'"
    params: dict = {}
    extra_where = ""
    if search:
        extra_where += " AND (CAST(c.login AS TEXT) LIKE :s OR c.name ILIKE :s OR c.email ILIKE :s OR c.phone ILIKE :s OR c.country ILIKE :s OR c.city ILIKE :s)"
        params["s"] = f"%{search}%"
    if country:
        extra_where += " AND c.country = :country"
        params["country"] = country
    if city:
        extra_where += " AND c.city ILIKE :city"
        params["city"] = f"%{city}%"
    if ib:
        # Filter by IB name - look up agent_id from ibs table
        ib_row = db.execute(text("SELECT agent_id FROM ibs WHERE name ILIKE :n LIMIT 1"), {"n": f"%{ib}%"}).fetchone()
        if ib_row:
            extra_where += " AND c.agent = :ib_agent_id"
            params["ib_agent_id"] = ib_row[0]
    if agent:
        agent_user = db.execute(text("SELECT id FROM users WHERE full_name ILIKE :a LIMIT 1"), {"a": f"%{agent}%"}).fetchone()
        if agent_user:
            extra_where += " AND c.assigned_agent_id = :agent_id"
            params["agent_id"] = agent_user[0]
    if kyc:
        extra_where += " AND c.kyc_status = :kyc"
        params["kyc"] = kyc
    if risk:
        extra_where += " AND c.risk_score = :risk"
        params["risk"] = risk
    if sources:
        src_list = [s.strip() for s in sources.split(',')]
        extra_where += " AND c.source = ANY(:sources)"
        params["sources"] = src_list
    where = f"WHERE {base_where}{extra_where}"

    sort_col = "balance DESC"
    if sort == "name":         sort_col = "name ASC"
    elif sort == "login":      sort_col = "login DESC"
    elif sort == "new":        sort_col = "first_deposit_at DESC NULLS LAST"
    elif sort == "score":      sort_col = "COALESCE(call_score,0) DESC, balance DESC"
    elif sort == "deposits":   sort_col = "total_deposit DESC"
    elif sort == "equity":     sort_col = "equity DESC"
    elif sort == "total_dep":  sort_col = "total_deposit DESC"
    elif sort == "total_with": sort_col = "total_withdraw DESC"
    elif sort == "country":    sort_col = "country ASC"
    elif sort == "city":       sort_col = "city ASC"
    # (no recapture pin — Priority sorts purely by score, Newest by date)

    # Count unique clients by phone
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT CASE
                WHEN c.phone IS NOT NULL AND c.phone != '' AND c.phone != '0'
                THEN c.phone ELSE CAST(c.login AS TEXT)
            END as ck
            FROM clients c {where}
            GROUP BY ck
        ) x
    """
    total = db.execute(text(count_sql), params).scalar() or 0

    # Main query â€” aggregate by phone
    query_sql = f"""
        SELECT
            MIN(c.id)                 as id,
            MIN(c.login)              as login,
            MIN(c.name)               as name,
            MIN(c.email)              as email,
            MIN(c.phone)              as phone,
            MIN(c.country)            as country,
            MIN(c.city)               as city,
            MIN(c.last_ip)            as ip,
            MIN(c.cid)                as cid,
            SUM(c.balance)            as balance,
            SUM(CASE WHEN c.equity IS NOT NULL AND c.equity != 0 THEN c.equity ELSE c.balance END) as equity,
            AVG(CASE WHEN c.margin_level IS NOT NULL AND c.margin_level > 0 THEN c.margin_level END) as margin_level,
            SUM(COALESCE(c.credit,0))  as bonus,
            SUM(COALESCE(c.total_deposits,0))    as total_deposit,
            SUM(COALESCE(c.total_withdrawals,0)) as total_withdraw,
            SUM(COALESCE(c.total_deposits,0)) - SUM(COALESCE(c.total_withdrawals,0)) as net_deposit,
            MIN(c.agent)              as agent,
            MIN(c.reg_date)           as reg_date,
            COALESCE(MIN(c.first_deposit_at), MIN(td.first_tx_date)) as first_deposit_at,
            MIN(c.first_deposit_amount) as first_deposit_amount,
            MAX(c.last_deposit_at)    as last_deposit_at,
            MAX(c.last_withdraw_at)   as last_withdraw_at,
            MIN(c.kyc_status)         as kyc,
            MIN(c.risk_score)         as risk,
            COUNT(*)                  as account_count,
            BOOL_OR(COALESCE(c.is_flagged, FALSE)) as is_flagged,
            MIN(c.assigned_agent_id)  as assigned_agent_id,
            array_agg(DISTINCT c.login) as all_logins,
            MAX(c.lead_badge)         as lead_badge,
            MAX(c.matched_lead_id)    as matched_lead_id,
            CASE
                WHEN c.phone IS NOT NULL AND c.phone != '' AND c.phone != '0'
                THEN c.phone ELSE CAST(c.login AS TEXT)
            END as ck,
            MAX(ml.meta_created)      as recapture_form_date
        FROM clients c
        LEFT JOIN (
            SELECT login, MIN(tx_date) as first_tx_date
            FROM transactions WHERE tx_type='deposit'
            GROUP BY login
        ) td ON td.login = c.login
        LEFT JOIN leads ml ON ml.id = c.matched_lead_id
        {where}
        GROUP BY ck
        ORDER BY {sort_col}
        LIMIT :limit OFFSET :offset
    """
    params["limit"]  = page_size
    params["offset"] = (page - 1) * page_size
    rows = db.execute(text(query_sql), params).fetchall()

    if not rows:
        return {"clients": [], "total": total, "page": page, "page_size": page_size}

    logins_list = [r[0] for r in rows]

    # IB names in batch
    agent_ids = list({r[16] for r in rows if r[16]})
    ib_map = {}
    if agent_ids:
        ibs = db.query(models.IB).filter(models.IB.agent_id.in_(agent_ids)).all()
        ib_map = {ib.agent_id: ib.name for ib in ibs}

    # Last activity per client - get most recent transaction of ANY type
    last_tx_map = {}
    dep_stats_map = {}
    with_stats_map = {}
    if logins_list:
        last_txs = db.execute(text(
            "SELECT DISTINCT ON (login) login, tx_type, amount, tx_date "
            "FROM transactions WHERE login=ANY(:logins) "
            "ORDER BY login, tx_date DESC NULLS LAST"
        ), {"logins": logins_list}).fetchall()
        last_tx_map = {r[0]: {"type": r[1], "amount": float(r[2] or 0), "date": str(r[3] or "")} for r in last_txs}

        dep_stats = db.execute(text(
            "SELECT login, COUNT(*) as dc, MIN(tx_date) as fd, SUM(amount) as total "
            "FROM transactions WHERE login=ANY(:logins) AND tx_type='deposit' GROUP BY login"
        ), {"logins": logins_list}).fetchall()
        dep_stats_map = {r[0]: {
            "dep_count": r[1] or 0,
            "first_dep_date": str(r[2] or ""),
            "total_dep": float(r[3] or 0)
        } for r in dep_stats}

        with_stats = db.execute(text(
            "SELECT login, SUM(amount) as total "
            "FROM transactions WHERE login=ANY(:logins) AND tx_type='withdrawal' GROUP BY login"
        ), {"logins": logins_list}).fetchall()
        with_stats_map = {r[0]: float(r[1] or 0) for r in with_stats}

    # Agent name lookup
    assigned_agent_ids = list({r[26] for r in rows if len(r) > 26 and r[26]})
    agent_name_map = {}
    if assigned_agent_ids:
        agents = db.execute(text("SELECT id, full_name FROM users WHERE id=ANY(:ids)"), {"ids": assigned_agent_ids}).fetchall()
        agent_name_map = {a[0]: a[1] for a in agents}

    # First deposit date + count
    first_dep_map = {}
    dep_count_map = {}
    first_dep_amount_map = {}
    try:
        fdeps = db.execute(text("""
            SELECT MIN(c.login) as rep_login,
                   MIN(t.tx_date) as first_dep,
                   COUNT(t.id) as dep_count
            FROM transactions t
            JOIN clients c ON c.login = t.login
            WHERE t.tx_type = 'deposit'
            AND c.login = ANY(:logins)
            GROUP BY CASE
                WHEN c.phone IS NOT NULL AND c.phone != '' AND c.phone != '0'
                THEN c.phone ELSE CAST(c.login AS TEXT)
            END
        """), {"logins": logins_list}).fetchall()
        for r in fdeps:
            first_dep_map[r[0]] = r[1]
            dep_count_map[r[0]] = r[2]

        # First deposit amounts
        famts = db.execute(text("""
            SELECT t.login, t.amount
            FROM transactions t
            WHERE t.tx_type = 'deposit'
            AND t.login = ANY(:logins)
            ORDER BY t.tx_date ASC
        """), {"logins": logins_list}).fetchall()
        seen_famts: set = set()
        for r in famts:
            if r[0] not in seen_famts:
                first_dep_amount_map[r[0]] = float(r[1] or 0)
                seen_famts.add(r[0])
    except:
        pass

    # Last client activity (transactions)
    last_activity_map = {}
    try:
        acts = db.execute(text("""
            SELECT MIN(c.login) as rep_login, t.tx_type, MAX(t.tx_date) as last_date
            FROM transactions t
            JOIN clients c ON c.login = t.login
            WHERE t.tx_type IN ('deposit','withdrawal','internal_transfer')
            AND c.login = ANY(:logins)
            GROUP BY
                CASE WHEN c.phone IS NOT NULL AND c.phone != '' AND c.phone != '0'
                    THEN c.phone ELSE CAST(c.login AS TEXT) END,
                t.tx_type
            ORDER BY last_date DESC
        """), {"logins": logins_list}).fetchall()
        for a in acts:
            rep = a[0]
            if rep not in last_activity_map:
                last_activity_map[rep] = {"type": a[1], "date": str(a[2]) if a[2] else ""}
            elif a[2] and str(a[2]) > last_activity_map[rep].get("date", ""):
                last_activity_map[rep] = {"type": a[1], "date": str(a[2]) if a[2] else ""}
    except:
        pass

    # Last sales action (call_actions)
    last_action_map = {}
    try:
        login_list_str = ",".join(str(l) for l in logins_list)
        actions = db.execute(text(f"""
            SELECT DISTINCT ON (login) login, action, note, created_at, call_later_at
            FROM call_actions
            WHERE login IN ({login_list_str})
            ORDER BY login, created_at DESC
        """)).fetchall()
        for a in actions:
            last_action_map[a[0]] = {
                "type":          a[1],
                "note":          a[2],
                "date":          str(a[3]) if a[3] else "",
                "call_later_at": str(a[4]) if a[4] else "",
            }
    except:
        pass

    # Network scores (IP/CID + City + IB + Phone prefix)
    net_scores = {}
    try:
        nets = db.execute(text("""
            SELECT login_a as login, COUNT(*) as cnt FROM network_edges
            WHERE login_a = ANY(:logins) GROUP BY login_a
            UNION ALL
            SELECT login_b as login, COUNT(*) as cnt FROM network_edges
            WHERE login_b = ANY(:logins) GROUP BY login_b
        """), {"logins": logins_list}).fetchall()
        for r in nets:
            net_scores[r[0]] = net_scores.get(r[0], 0) + r[1]

        # Same city
        city_counts = db.execute(text("""
            SELECT c1.login, COUNT(c2.login) as cnt
            FROM clients c1
            JOIN clients c2 ON c2.city = c1.city AND c2.login != c1.login
                AND c1.city IS NOT NULL AND c1.city != ''
            WHERE c1.login = ANY(:logins)
            GROUP BY c1.login
        """), {"logins": logins_list}).fetchall()
        for r in city_counts:
            net_scores[r[0]] = net_scores.get(r[0], 0) + min(r[1], 10)

        # Same IB
        ib_counts = db.execute(text("""
            SELECT c1.login, COUNT(c2.login) as cnt
            FROM clients c1
            JOIN clients c2 ON c2.agent = c1.agent AND c2.login != c1.login
                AND c1.agent IS NOT NULL AND c1.agent != 0
            WHERE c1.login = ANY(:logins)
            GROUP BY c1.login
        """), {"logins": logins_list}).fetchall()
        for r in ib_counts:
            net_scores[r[0]] = net_scores.get(r[0], 0) + min(r[1], 5)

        # Same phone prefix (family)
        phone_counts = db.execute(text("""
            SELECT c1.login, COUNT(c2.login) as cnt
            FROM clients c1
            JOIN clients c2 ON LEFT(c2.phone, 7) = LEFT(c1.phone, 7)
                AND c2.login != c1.login
                AND c1.phone IS NOT NULL AND LENGTH(c1.phone) >= 7
            WHERE c1.login = ANY(:logins)
            GROUP BY c1.login
        """), {"logins": logins_list}).fetchall()
        for r in phone_counts:
            net_scores[r[0]] = net_scores.get(r[0], 0) + min(r[1] * 3, 15)
    except:
        pass

    # Score settings
    settings = get_score_settings(db)

    clients = []
    for r in rows:
        login  = r[1]
        agent  = r[16]
        la     = last_action_map.get(login, {})
        lact   = last_activity_map.get(login, {})

        mapped = {
            "id":                  r[0],
            "login":               login,
            "name":                r[2] or "",
            "email":               r[3] or "",
            "phone":               r[4] or "",
            "country":             r[5] or "",
            "city":                r[6] or "",
            "ip":                  r[7] or "",
            "cid":                 r[8] or "",
            "balance":             float(r[9] or 0),
            "equity":              float(r[10] or 0),
            "margin_level":        float(r[11] or 0) if r[11] else 0.0,
            "bonus":               float(r[12] or 0),
            "total_deposit":       dep_stats_map.get(login, {}).get("total_dep") or float(r[13] or 0),
            "total_withdraw":      with_stats_map.get(login) or float(r[14] or 0),
            "dep_count":           dep_stats_map.get(login, {}).get("dep_count", 0),
            "net_deposit":         float(r[15] or 0),
            "ib":                  str(agent or ""),
            "ib_display":          ib_map.get(agent, f"#{agent}" if agent else ""),
            "reg_date":            r[17] or "",
            "kyc":                 r[22] or "pending",
            "risk":                r[23] or "low",
            "account_count":       r[24] or 1,
            "first_deposit_date":  dep_stats_map.get(login, {}).get("first_dep_date", "") or (str(r[18]) if len(r) > 18 and r[18] else ""),
            "first_deposit_amount": float(r[19] or 0) if len(r) > 19 and r[19] else 0,
            "deposit_count":       dep_count_map.get(login, 0),
            "last_activity_type":  last_tx_map.get(login, {}).get("type", _get_last_activity_type(r[20], r[21]) if len(r) > 21 else ""),
            "last_activity_date":  last_tx_map.get(login, {}).get("date", str(max(filter(None, [r[20] if len(r)>20 else None, r[21] if len(r)>21 else None]), default="")) if len(r) > 20 else ""),
            "last_activity_amount": last_tx_map.get(login, {}).get("amount", 0),
            "assigned_agent_id": r[26] if len(r)>26 else None,
            "last_action_type":    la.get("type", ""),
            "last_action_note":    la.get("note", ""),
            "last_action_date":    la.get("date", ""),
            "last_action":         la,
            "network_score":       net_scores.get(login, 0),
            "flags":               [],
            "agent_name":          agent_name_map.get(r[26] if len(r)>26 else None, ""),
            "all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],
            "lead_badge":          r[27] if len(r)>27 else None,
            "matched_lead_id":     r[28] if len(r)>28 else None,
            "recapture_form_date": str(r[-1]) if r[-1] else "",
            "source":              "none",
            "_patch_marker": "v2_recapture",
        }
        mapped["call_score"] = calc_priority_score(mapped, settings)
        if mapped.get("lead_badge") == "recapture":
            mapped["call_score"] += 50
        clients.append(mapped)

    # If sorting by priority, sort by call_score desc
    if sort == "score":
        clients.sort(key=lambda x: x["call_score"], reverse=True)

    return {"clients": clients, "total": total, "page": page, "page_size": page_size}


@router.get("/id/{client_id}")
async def get_client_by_id(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    c = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    # Delegate to login-based handler using the client login
    return await get_client(c.login, db, current_user)


@router.get("/{login}")
async def get_client(
    login: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    c = db.query(models.Client).filter(models.Client.login == login).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    # All trading accounts for this client (MT4 + MT5) via client_id
    trading_accounts_all = db.query(models.TradingAccount).filter(
        models.TradingAccount.client_id == c.id
    ).order_by(models.TradingAccount.platform, models.TradingAccount.login).all()

    # Also find any same-phone clients (e.g. before linking was done)
    # and merge their trading accounts
    if c.phone and c.phone not in ('', '0'):
        same_phone_clients = db.query(models.Client).filter(
            models.Client.phone == c.phone,
            models.Client.id != c.id
        ).all()
        for sp in same_phone_clients:
            extra = db.query(models.TradingAccount).filter(
                models.TradingAccount.client_id == sp.id
            ).all()
            trading_accounts_all.extend(extra)

    all_logins = [ta.login for ta in trading_accounts_all]

    # Keep accounts as [c] for balance/equity aggregation (client-level fields)
    accounts = [c]

    # IB info
    ib_display = ""
    if c.agent:
        ib = db.query(models.IB).filter(models.IB.agent_id == c.agent).first()
        if ib:
            ib_display = f"{ib.name} ({ib.ib_code})"

    # Transactions
    deposits = db.query(models.Transaction).filter(
        models.Transaction.login.in_(all_logins),
        models.Transaction.tx_type == "deposit"
    ).order_by(models.Transaction.tx_date.desc()).limit(200).all()

    withdrawals = db.query(models.Transaction).filter(
        models.Transaction.login.in_(all_logins),
        models.Transaction.tx_type == "withdrawal"
    ).order_by(models.Transaction.tx_date.desc()).limit(200).all()

    # Network connections
    connections = []
    try:
        from sqlalchemy import or_
        edges = db.query(models.NetworkEdge).filter(
            or_(
                models.NetworkEdge.login_a == login,
                models.NetworkEdge.login_b == login,
            )
        ).limit(30).all()
        for e in edges:
            other = e.login_b if e.login_a == login else e.login_a
            other_c = db.query(models.Client).filter(models.Client.login == other).first()
            connections.append({
                "login":   other,
                "name":    other_c.name if other_c else f"#{other}",
                "reason":  e.reason or "",
                "value":   e.value or "",
                "risk":    other_c.risk_score if other_c else "low",
            })
    except:
        pass

    # Call actions
    actions = db.query(models.CallAction).filter(
        models.CallAction.login == login
    ).order_by(models.CallAction.created_at.desc()).all()

    # Timeline â€” merge all activities
    timeline = []
    for d in deposits[:10]:
        timeline.append({"type": "deposit", "amount": float(d.amount or 0), "method": d.method or "", "date": str(d.tx_date), "account": d.login})
    for d in withdrawals[:5]:
        timeline.append({"type": "withdrawal", "amount": float(d.amount or 0), "method": d.method or "", "date": str(d.tx_date), "account": d.login})
    for a in actions[:5]:
        timeline.append({"type": "call_action", "action": a.action, "note": a.note or "", "date": a.created_at.isoformat() if a.created_at else "", "agent": a.agent_id})
    timeline.sort(key=lambda x: x.get("date", ""), reverse=True)

    total_balance  = sum(float(a.balance or 0) for a in accounts)
    total_equity   = sum(float(a.equity or a.balance or 0) for a in accounts)
    total_deposits = sum(float(a.total_deposits or 0) for a in accounts)
    total_withdraw = sum(float(a.total_withdrawals or 0) for a in accounts)
    # Override with transactions if clients table shows 0
    all_logins = [a.login for a in accounts]
    if total_deposits == 0 and all_logins:
        tx_dep = db.execute(text(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE login=ANY(:l) AND tx_type='deposit'"
        ), {"l": all_logins}).scalar() or 0
        if tx_dep > 0: total_deposits = float(tx_dep)
    if total_withdraw == 0 and all_logins:
        tx_with = db.execute(text(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE login=ANY(:l) AND tx_type='withdrawal'"
        ), {"l": all_logins}).scalar() or 0
        if tx_with > 0: total_withdraw = float(tx_with)
    # Lowest non-zero margin across all accounts
    margins = [float(a.margin_level) for a in accounts if a.margin_level and float(a.margin_level) > 0]
    min_margin = min(margins) if margins else 0

    return {
        "login":          c.login,
        "name":           c.name or "",
        "email":          c.email or "",
        "phone":          c.phone or "",
        "country":        c.country or "",
        "city":           c.city or "",
        "ip":             c.last_ip or "",
        "cid":            str(c.cid or ""),
        "balance":        total_balance,
        "equity":         total_equity,
        "bonus":          sum(float(a.credit or 0) for a in accounts),
        "margin_level":   min_margin,
        "total_deposit":  total_deposits,
        "total_withdraw": total_withdraw,
        "net_deposit":    total_deposits - total_withdraw,
        "ib":             str(c.agent or ""),
        "ib_display":     ib_display,
        "reg_date":       str(c.first_deposit_at or c.reg_date or ""),
        "kyc":            c.kyc_status or "pending",
        "risk":           c.risk_score or "low",
        "account_count":  len(accounts),
        "first_deposit_date":   str(c.first_deposit_at or ""),
        "first_deposit_amount": float(c.first_deposit_amount or 0),
        "last_deposit_date":    str(c.last_deposit_at or ""),
        "last_withdraw_date":   str(c.last_withdraw_at or ""),
        "related_accounts": [{
            "login":     ta.login,
            "balance":   float(ta.balance or 0),
            "equity":    float(ta.equity or 0),
            "group":     ta.group_name or "",
            "is_active": bool(ta.is_active),
            "platform":  ta.platform or "MT5",
            "account_type": ta.account_type or "",
        } for ta in trading_accounts_all],
        "deposits_list": [{
            "deal_id": d.deal_id, "amount": float(d.amount or 0),
            "date": str(d.tx_date), "method": d.method or "",
            "account": d.login, "status": d.status or "approved"
        } for d in deposits],
        "withdrawals_list": [{
            "deal_id": d.deal_id, "amount": float(d.amount or 0),
            "date": str(d.tx_date), "method": d.method or "",
            "account": d.login, "status": d.status or "approved"
        } for d in withdrawals],
        "network_connections": connections,
        "timeline": timeline,
        "actions_history": [{
            "action":     a.action,
            "note":       a.note or "",
            "created_at": a.created_at.isoformat() if a.created_at else "",
            "agent_id":   a.agent_id,
        } for a in actions],
        "flags":      [],
        "call_score": 0,
        "source":     "none",
    }


@router.post("/action")
def save_action(
    data: ActionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    call_later_at = None
    if data.action == "call_later":
        now = datetime.now(timezone.utc)
        call_later_at = now + timedelta(
            days=data.call_later_days or 0,
            hours=data.call_later_hours or 0
        )
    db.add(models.CallAction(
        login=data.login,
        agent_id=current_user.id,
        action=data.action,
        note=data.note,
        call_later_at=call_later_at,
        passed_to_manager=data.pass_to_manager or False,
    ))
    db.commit()
    return {"message": "Action saved"}


@router.post("/assign")
def assign_client(
    login: int, agent_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    existing = db.query(models.ClientAssignment).filter(
        models.ClientAssignment.login == login
    ).first()
    if existing:
        existing.agent_id = agent_id
    else:
        db.add(models.ClientAssignment(login=login, agent_id=agent_id))
    db.commit()
    return {"message": "Assigned"}


@router.post("/{login}/comment")
async def post_comment(
    login: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from models import CallAction
    action = CallAction(
        login=login,
        agent_id=current_user.id,
        action="comment",
        note=data.get("note",""),
        created_at=datetime.utcnow()
    )
    db.add(action)
    db.commit()
    return {"message": "Comment posted"}

@router.get("/logins-only")
def get_client_logins(
    search:  str = Query(""),
    sort:    str = Query("score"),
    country: str = Query(""),
    city:    str = Query(""),
    ib:      str = Query(""),
    agent:   str = Query(""),
    kyc:     str = Query(""),
    risk:    str = Query(""),
    sources: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fast endpoint â€” returns only login IDs for power dialer."""
    where_parts = ["1=1"]
    params: dict = {}
    if search:
        where_parts.append("(CAST(c.login AS TEXT) LIKE :s OR c.name ILIKE :s OR c.phone ILIKE :s)")
        params["s"] = f"%{search}%"
    if country: where_parts.append("c.country ILIKE :country"); params["country"] = f"%{country}%"
    if city:    where_parts.append("c.city ILIKE :city");       params["city"]    = f"%{city}%"
    if ib:      where_parts.append("c.ib_name ILIKE :ib");      params["ib"]      = f"%{ib}%"
    if agent:   where_parts.append("c.assigned_agent_id = :agent"); params["agent"] = int(agent)
    if kyc:     where_parts.append("c.kyc_status = :kyc");      params["kyc"]     = kyc
    if sources:
        src_list = [s.strip() for s in sources.split(",") if s.strip()]
        if src_list:
            where_parts.append(f"c.source IN ({','.join([f':src{i}' for i in range(len(src_list))])})")
            for i, s in enumerate(src_list): params[f"src{i}"] = s

    sort_col = {"score":"c.score DESC","balance":"c.balance DESC","deposits":"c.total_deposits DESC",
                "new":"c.created_at DESC","name":"c.name ASC"}.get(sort, "c.score DESC")

    where = " AND ".join(where_parts)
    rows = db.execute(text(f"""
        SELECT c.login FROM clients c
        WHERE {where} AND c.phone IS NOT NULL AND c.phone != ''
        ORDER BY {sort_col}
    """), params).fetchall()
    return {"logins": [r[0] for r in rows], "total": len(rows)}








