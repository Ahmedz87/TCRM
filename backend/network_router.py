"""
network_router.py — Network connections, CID clusters, IP clusters, fraud groups
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import connection_engine as CE

router = APIRouter(prefix="/network", tags=["Network"])


@router.get("/connections")
def get_connections(login: int = Query(0), lead_id: int = Query(0),
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """Ranked connections for one client (login) or lead (lead_id), most-certain first,
    each with a confidence % + x/10 score + the signals that fired."""
    if not login and not lead_id:
        return {"subject": None, "connections": []}
    return CE.score_connections(db, login=login or None, lead_id=lead_id or None)


@router.get("/connection-groups")
def get_connection_groups(limit: int = Query(60, ge=1, le=120),
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """The 'Connections' tab: linked-account groups (device/ip/phone/email mix) ranked
    worst-first, each with money/IB stats and a deterministic verdict."""
    return {"groups": CE.connection_groups(db, limit=limit)}


@router.post("/connection-groups/analyze")
def analyze_group(data: dict, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """Optional Claude 4.8 deep-dive on a group's accounts. Falls back to the deterministic
    verdicts if the Anthropic key isn't configured."""
    logins = [int(x) for x in (data.get("logins") or []) if str(x).lstrip('-').isdigit()][:25]
    if not logins:
        return {"ok": False, "error": "no logins"}
    st = CE.group_stats(db, logins)
    verdicts = CE.classify_group(st)
    try:
        import ai_config
        if not ai_config.is_configured():
            return {"ok": True, "ai": False, "verdicts": verdicts,
                    "narrative": "Claude not configured — showing rule-based verdicts."}
        import anthropic, json as _json
        compact = {"totals": st["totals"], "dominant_ib": st["dominant_ib"],
                   "members": [{k: mm[k] for k in ("login", "name", "city", "ib_name", "deposits",
                                "withdrawals", "bonus", "pnl", "trades", "win_rate", "is_islamic",
                                "ib_commission")} for mm in st["members"]]}
        prompt = (
            "You are a forex-broker risk analyst. Below is a cluster of trading accounts that "
            "share a device/IP/phone/email (so they're operated by the same person or ring). "
            "In 4-6 sentences, explain plainly what they are most likely doing and why it costs the "
            "broker money. Call out: IB commission farming, bonus extraction, internal offsetting "
            "(one account deliberately loses to feed others), toxic/latency trading, or swap-free "
            "carry abuse — whichever fit. Be specific with the numbers. End with one line: "
            "'Recommended action: ...'.\n\nDATA:\n" + _json.dumps(compact, default=str))
        client = anthropic.Anthropic(api_key=ai_config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-opus-4-8", max_tokens=600,
            messages=[{"role": "user", "content": prompt}])
        narrative = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {"ok": True, "ai": True, "model": "claude-opus-4-8",
                "verdicts": verdicts, "narrative": narrative.strip()}
    except Exception as e:
        return {"ok": True, "ai": False, "verdicts": verdicts,
                "narrative": f"(AI deep-dive unavailable: {str(e)[:120]}) Showing rule-based verdicts."}


def _enrich_accounts(db, logins):
    """For a cluster's logins, pull the investigative profile per account (IB, city,
    deposits/withdrawals/bonus, last deposit, trading P&L + win-rate) plus ring totals,
    so back-office can see WHY a device/IP has many accounts without leaving the page."""
    if not logins:
        return [], {}
    rows = db.execute(text("""
        SELECT c.login, c.name, COALESCE(c.balance,0), c.country, c.city, c.agent,
               COALESCE(c.credit,0), i.name AS ib_name, c.group_name,
               COALESCE(tx.dep,0), COALESCE(tx.wd,0), COALESCE(tx.bonus,0), tx.last_dep,
               COALESCE(dl.pnl,0), COALESCE(dl.trades,0), dl.winrate
        FROM clients c
        LEFT JOIN ibs i ON i.agent_id = c.agent
        LEFT JOIN (
            SELECT login,
                   SUM(amount) FILTER (WHERE tx_type='deposit')          AS dep,
                   SUM(amount) FILTER (WHERE tx_type='withdrawal')        AS wd,
                   SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus%')      AS bonus,
                   MAX(tx_date) FILTER (WHERE tx_type='deposit')          AS last_dep
            FROM transactions WHERE login = ANY(:logins) GROUP BY login
        ) tx ON tx.login = c.login
        LEFT JOIN (
            SELECT login,
                   SUM(profit) FILTER (WHERE entry=1)                                       AS pnl,
                   COUNT(*) FILTER (WHERE entry=1 AND direction IN ('buy','sell'))          AS trades,
                   AVG(CASE WHEN entry=1 AND profit>0 THEN 1.0 WHEN entry=1 THEN 0 END)     AS winrate
            FROM deals WHERE login = ANY(:logins) GROUP BY login
        ) dl ON dl.login = c.login
        WHERE c.login = ANY(:logins)
    """), {"logins": logins}).fetchall()
    accs = []
    t_dep = t_wd = t_bonus = t_pnl = 0.0
    for a in rows:
        dep, wd, bonus, pnl = float(a[9] or 0), float(a[10] or 0), float(a[11] or 0), float(a[13] or 0)
        t_dep += dep; t_wd += wd; t_bonus += bonus; t_pnl += pnl
        accs.append({
            "login": a[0], "name": a[1] or f"#{a[0]}", "balance": float(a[2] or 0),
            "country": a[3] or "", "city": a[4] or "", "agent": a[5] or 0,
            "credit": float(a[6] or 0), "ib_name": a[7] or (f"#{a[5]}" if a[5] else ""),
            "group_name": a[8] or "", "deposits": dep, "withdrawals": wd, "bonus": bonus,
            "last_deposit": str(a[12]) if a[12] else "", "pnl": pnl, "trades": int(a[14] or 0),
            "win_rate": round(float(a[15]) * 100) if a[15] is not None else None,
        })
    accs.sort(key=lambda x: x["deposits"] + x["withdrawals"], reverse=True)
    totals = {"deposits": round(t_dep, 2), "withdrawals": round(t_wd, 2),
              "bonus": round(t_bonus, 2), "pnl": round(t_pnl, 2),
              "net_to_clients": round(t_wd - t_dep, 2),
              "ib_names": sorted({a["ib_name"] for a in accs if a["ib_name"]})}
    return accs, totals


@router.get("/stats")
def get_network_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    total_edges = db.execute(text("SELECT COUNT(*) FROM network_edges")).scalar() or 0
    cid_clusters = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT identifier_value FROM account_identifiers
            WHERE identifier_type='cid' AND identifier_value != '0' AND identifier_value != ''
            GROUP BY identifier_value HAVING COUNT(DISTINCT login) > 1
        ) x
    """)).scalar() or 0
    ip_clusters = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT identifier_value FROM account_identifiers
            WHERE identifier_type='ip'
            GROUP BY identifier_value HAVING COUNT(DISTINCT login) > 2
        ) x
    """)).scalar() or 0
    flagged = db.execute(text("""
        SELECT COUNT(DISTINCT login_a) FROM network_edges WHERE reason='cid'
    """)).scalar() or 0
    return {
        "total_edges": total_edges,
        "cid_clusters": cid_clusters,
        "ip_clusters": ip_clusters,
        "flagged_accounts": flagged,
    }


@router.get("/cid-clusters")
def get_cid_clusters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where = "WHERE identifier_type='cid' AND identifier_value != '0' AND identifier_value != ''"
    if search:
        where += f" AND (identifier_value ILIKE '%{search}%' OR CAST(login AS TEXT) LIKE '%{search}%')"

    clusters = db.execute(text(f"""
        SELECT identifier_value, COUNT(DISTINCT login) as account_count,
               array_agg(DISTINCT login) as logins
        FROM account_identifiers
        {where}
        GROUP BY identifier_value
        HAVING COUNT(DISTINCT login) > 1
        ORDER BY account_count DESC
        LIMIT :limit OFFSET :offset
    """), {"limit": page_size, "offset": (page-1)*page_size}).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT identifier_value FROM account_identifiers
            {where}
            GROUP BY identifier_value HAVING COUNT(DISTINCT login) > 1
        ) x
    """)).scalar() or 0

    result = []
    for c in clusters:
        cid = c[0]
        logins = c[2][:10] if c[2] else []
        accounts, totals = _enrich_accounts(db, logins)
        result.append({
            "cid": cid,
            "account_count": c[1],
            "accounts": accounts,
            "totals": totals,
        })

    return {"clusters": result, "total": total}


@router.get("/ip-clusters")
def get_ip_clusters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_accounts: int = Query(2, ge=2),
    search: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where = "WHERE identifier_type='ip'"
    if search:
        where += f" AND (identifier_value ILIKE '%{search}%' OR CAST(login AS TEXT) LIKE '%{search}%')"

    clusters = db.execute(text(f"""
        SELECT identifier_value, COUNT(DISTINCT login) as account_count,
               array_agg(DISTINCT login) as logins
        FROM account_identifiers
        {where}
        GROUP BY identifier_value
        HAVING COUNT(DISTINCT login) >= :min_acc
        ORDER BY account_count DESC
        LIMIT :limit OFFSET :offset
    """), {"min_acc": min_accounts, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT identifier_value FROM account_identifiers
            {where}
            GROUP BY identifier_value HAVING COUNT(DISTINCT login) >= :min_acc
        ) x
    """), {"min_acc": min_accounts}).scalar() or 0

    result = []
    for c in clusters:
        ip = c[0]
        logins = c[2][:10] if c[2] else []
        accounts, totals = _enrich_accounts(db, logins)
        result.append({
            "ip": ip,
            "account_count": c[1],
            "accounts": accounts,
            "totals": totals,
        })

    return {"clusters": result, "total": total}


@router.get("/account/{login}")
def get_account_network(
    login: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Get all connections for this account
    edges = db.execute(text("""
        SELECT ne.login_b as connected, ne.reason, ne.value, c.name, c.balance, c.country
        FROM network_edges ne
        LEFT JOIN clients c ON c.login = ne.login_b
        WHERE ne.login_a = :login
        UNION
        SELECT ne.login_a as connected, ne.reason, ne.value, c.name, c.balance, c.country
        FROM network_edges ne
        LEFT JOIN clients c ON c.login = ne.login_a
        WHERE ne.login_b = :login
        ORDER BY reason
    """), {"login": login}).fetchall()

    identifiers = db.execute(text("""
        SELECT identifier_type, identifier_value, seen_count, last_seen
        FROM account_identifiers WHERE login = :login
        ORDER BY seen_count DESC
    """), {"login": login}).fetchall()

    return {
        "login": login,
        "connections": [{"login": e[0], "reason": e[1], "value": e[2], "name": e[3] or f"#{e[0]}", "balance": float(e[4] or 0), "country": e[5] or ""} for e in edges],
        "identifiers": [{"type": i[0], "value": i[1], "seen_count": i[2] or 0, "last_seen": str(i[3]) if i[3] else ""} for i in identifiers],
    }


@router.get("/traverse/{login}")
def traverse_network(
    login: int,
    layers: int = Query(3, ge=1, le=4),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Multi-layer network traversal:
    Layer 1: Find IPs/CIDs used by login → find other accounts using those IPs/CIDs
    Layer 2: Find IPs/CIDs used by layer-1 accounts → find new accounts
    Layer 3: Repeat for layer-2 accounts
    """
    visited_logins = {login}
    visited_identifiers = set()
    all_nodes = {}
    all_edges = []

    # Get root account info
    root = db.execute(text("""
        SELECT c.login, c.name, c.balance, c.country, c.city, c.agent,
               ib.name as ib_name, ib.ib_code
        FROM clients c
        LEFT JOIN ibs ib ON ib.agent_id = c.agent
        WHERE c.login = :l
    """), {"l": login}).fetchone()

    if not root:
        return {"error": "Account not found"}

    all_nodes[login] = {
        "login": login, "name": root[1] or f"#{login}",
        "balance": float(root[2] or 0), "country": root[3] or "",
        "city": root[4] or "", "ib": root[6] or "", "ib_code": root[7] or "",
        "layer": 0, "type": "root"
    }

    current_layer_logins = {login}

    for layer in range(1, layers + 1):
        if not current_layer_logins:
            break

        login_list = list(current_layer_logins)
        new_logins_this_layer = set()

        # Step 1: Get all IPs and CIDs used by current layer accounts
        identifiers = db.execute(text("""
            SELECT DISTINCT login, identifier_type, identifier_value
            FROM account_identifiers
            WHERE login = ANY(:logins)
            AND identifier_value != '0' AND identifier_value != ''
        """), {"logins": login_list}).fetchall()

        new_identifiers = set()
        for ident in identifiers:
            key = (ident[1], ident[2])
            if key not in visited_identifiers:
                new_identifiers.add(key)
                visited_identifiers.add(key)

        if not new_identifiers:
            break

        # Step 2: Find all accounts using those IPs/CIDs
        for id_type, id_value in new_identifiers:
            connected = db.execute(text("""
                SELECT DISTINCT ai.login, c.name, c.balance, c.country, c.city,
                       c.agent, ib.name as ib_name, ib.ib_code
                FROM account_identifiers ai
                LEFT JOIN clients c ON c.login = ai.login
                LEFT JOIN ibs ib ON ib.agent_id = c.agent
                WHERE ai.identifier_type = :t AND ai.identifier_value = :v
                AND ai.login != ALL(:exclude)
            """), {"t": id_type, "v": id_value, "exclude": list(visited_logins)}).fetchall()

            for conn in connected:
                conn_login = conn[0]
                if conn_login and conn_login not in visited_logins:
                    visited_logins.add(conn_login)
                    new_logins_this_layer.add(conn_login)

                    if conn_login not in all_nodes:
                        all_nodes[conn_login] = {
                            "login": conn_login,
                            "name": conn[1] or f"#{conn_login}",
                            "balance": float(conn[2] or 0),
                            "country": conn[3] or "",
                            "city": conn[4] or "",
                            "ib": conn[6] or "",
                            "ib_code": conn[7] or "",
                            "layer": layer,
                            "type": id_type,
                            "connect_via": id_value,
                        }

                    # Find the source login(s) that share this identifier
                    sources = [l for l in login_list if any(
                        i[0] == l and i[1] == id_type and i[2] == id_value
                        for i in identifiers
                    )]
                    for src in sources:
                        edge_key = f"{min(src, conn_login)}-{max(src, conn_login)}-{id_type}"
                        if not any(e.get("key") == edge_key for e in all_edges):
                            all_edges.append({
                                "key": edge_key,
                                "from": src, "to": conn_login,
                                "type": id_type, "value": id_value,
                                "layer": layer,
                            })

        current_layer_logins = new_logins_this_layer

    # Also add same-family connections (same phone prefix, city, IB)
    all_login_list = list(all_nodes.keys())
    if len(all_login_list) > 1:
        family_edges = db.execute(text("""
            SELECT login_a, login_b, reason, value
            FROM network_edges
            WHERE login_a = ANY(:logins) AND login_b = ANY(:logins)
            AND reason IN ('family','ib')
        """), {"logins": all_login_list}).fetchall()

        for fe in family_edges:
            edge_key = f"{min(fe[0],fe[1])}-{max(fe[0],fe[1])}-{fe[2]}"
            if not any(e.get("key") == edge_key for e in all_edges):
                all_edges.append({
                    "key": edge_key,
                    "from": fe[0], "to": fe[1],
                    "type": fe[2], "value": fe[3] or "",
                    "layer": -1,
                })

    return {
        "root": login,
        "nodes": list(all_nodes.values()),
        "edges": [e for e in all_edges if "key" in e],
        "stats": {
            "total_accounts": len(all_nodes),
            "total_edges": len(all_edges),
            "layers": layers,
        }
    }
