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


def _entity_of(db, login, lead_id):
    if login:
        cn = db.execute(text("SELECT customer_no FROM clients WHERE login=:l"), {"l": login}).scalar()
        return f"C{cn}" if cn else None
    if lead_id:
        return f"L{lead_id}"
    return None


def _resolve_entities(db, ents):
    """entity-key -> {name, login, kind, score, state}. One representative login per client customer."""
    out = {}
    cns = [e[1:] for e in ents if e.startswith("C")]
    lids = [int(e[1:]) for e in ents if e.startswith("L")]
    if cns:
        for cn, nm, lg, st, sc, ctry in db.execute(text("""
            SELECT DISTINCT ON (customer_no) customer_no, name, login, relation_state,
                   COALESCE(network_score,0), country
            FROM clients WHERE customer_no = ANY(:c)
            ORDER BY customer_no, COALESCE(total_deposits,0) DESC, login
        """), {"c": cns}).fetchall():
            out[f"C{cn}"] = {"name": nm or f"#{lg}", "login": lg, "kind": "client",
                             "state": st, "score10": int(sc or 0), "country": ctry or ""}
    if lids:
        for lid, nm, st, sc, ctry in db.execute(text("""
            SELECT id, full_name, relation_state, COALESCE(network_score,0), country
            FROM leads WHERE id = ANY(:l)
        """), {"l": lids}).fetchall():
            out[f"L{lid}"] = {"name": nm or f"Lead #{lid}", "login": None, "kind": "lead",
                              "id": lid, "state": st, "score10": int(sc or 0), "country": ctry or ""}
    return out


@router.get("/connections")
def get_connections(login: int = Query(0), lead_id: int = Query(0),
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """Who this client/lead is related to — read from the ONE ledger (entity_relations), so the popup,
    the badge and the Related/Unrelated tables can never disagree. Each row carries the signals that
    fired + the other party's x/10 + why."""
    if not login and not lead_id:
        return {"subject": None, "connections": []}
    me = _entity_of(db, login or None, lead_id or None)
    st = CE.stored_subject_score(db, login=login or None, lead_id=lead_id or None)
    base = {"subject": {"login": login or None, "lead_id": lead_id or None, **st},
            "score10": st["score10"], "level": st["level"], "colour": st["colour"], "reason": st["reason"],
            "connections": []}
    if not me:
        return base
    rows = db.execute(text("""
        SELECT CASE WHEN ent_a = :me THEN ent_b ELSE ent_a END AS other,
               signals, strength, top_reason, last_seen
        FROM entity_relations WHERE ent_a = :me OR ent_b = :me
    """), {"me": me}).fetchall()
    if not rows:
        return base
    meta = _resolve_entities(db, [r[0] for r in rows])
    conns = []
    for other, signals, strength, top_reason, last_seen in rows:
        m = meta.get(other, {"name": other, "login": None, "kind": "client", "score10": 0, "country": ""})
        reasons = [{"type": s, "label": CE.SIGNAL_LABEL.get(s, s), "value": ""} for s in (signals or [])]
        reasons.sort(key=lambda r: CE.LINK_PRIORITY.get(r["type"], 99))
        conns.append({**m, "reasons": reasons, "strength": strength, "top_reason": top_reason,
                      "since": str(last_seen)[:10] if last_seen else ""})
    # strongest links first (decisive, then more signals)
    conns.sort(key=lambda c: (c["strength"] != "decisive", -len(c["reasons"]), -c["score10"]))
    base["connections"] = conns
    return base


@router.get("/relations")
def list_relations(view: str = Query("related"), search: str = Query(""), state: str = Query(""),
                   kind: str = Query(""), sort: str = Query("time"), page: int = Query(1, ge=1),
                   page_size: int = Query(50, ge=1, le=200),
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """The two tables. view='related' → everyone WITH a relation (entity_status, with the reason);
    view='unrelated' → everyone clean (clients+leads with no relation). `total` always reflects the
    ACTIVE filters. Default sort = newest caught first."""
    off = (page - 1) * page_size
    if view == "related":
        w = ["is_related"]
        p: dict = {"lim": page_size, "off": off}
        if search:
            w.append("(name ILIKE :s OR ent ILIKE :s)"); p["s"] = f"%{search}%"
        if state:
            w.append("relation_state = :st"); p["st"] = state
        if kind:
            w.append("kind = :k"); p["k"] = kind
        wc = " AND ".join(w)
        total = db.execute(text(f"SELECT COUNT(*) FROM entity_status WHERE {wc}"), p).scalar() or 0
        order = {"time": "latest_at DESC NULLS LAST, network_score DESC",
                 "score": "network_score DESC, n_related DESC",
                 "links": "n_related DESC, network_score DESC"}.get(sort, "latest_at DESC NULLS LAST")
        rows = db.execute(text(f"""
            SELECT ent, name, kind, n_related, network_score, network_level, top_reason,
                   relation_state, has_decisive, bonus_status, latest_at
            FROM entity_status WHERE {wc}
            ORDER BY {order} LIMIT :lim OFFSET :off"""), p).fetchall()
        return {"view": "related", "total": total, "page": page, "page_size": page_size,
                "rows": [{"ent": r[0], "name": r[1] or r[0], "kind": r[2], "n_related": r[3],
                          "network_score": r[4] or 0, "network_level": r[5], "top_reason": r[6],
                          "state": r[7], "decisive": bool(r[8]), "bonus_status": r[9],
                          "since": str(r[10])[:10] if r[10] else "",
                          "login": (None if r[0].startswith("L") else _rep_login(db, r[0])),
                          "lead_id": (int(r[0][1:]) if r[0].startswith("L") else None)} for r in rows]}
    # unrelated — clean clients + leads (no relation). Depositors here are the NDA / FTD-pending set.
    p = {"lim": page_size, "off": off}
    cli_search = lead_search = st_flt_c = st_flt_l = ""
    if search:
        cli_search = "AND c.name ILIKE :s"; lead_search = "AND l.full_name ILIKE :s"; p["s"] = f"%{search}%"
    if state:
        st_flt_c = "AND COALESCE(c.relation_state,'unfunded_clean') = :st"
        st_flt_l = "AND COALESCE(l.relation_state,'unfunded_clean') = :st"; p["st"] = state
    # ts = the row's own time: a client's first deposit (or reg date), a lead's created_at → newest first
    total = db.execute(text(f"""
        SELECT (SELECT COUNT(DISTINCT c.customer_no) FROM clients c
                WHERE c.customer_no IS NOT NULL AND COALESCE(c.network_score,0)=0 {cli_search} {st_flt_c})
             + (SELECT COUNT(*) FROM leads l WHERE COALESCE(l.network_score,0)=0 {lead_search} {st_flt_l})
    """), p).scalar() or 0
    rows = db.execute(text(f"""
        SELECT ent, name, kind, login, lead_id, state, ts FROM (
            SELECT DISTINCT ON (c.customer_no) 'C'||c.customer_no AS ent, c.name AS name,
                   'client' AS kind, c.login AS login, NULL::bigint AS lead_id,
                   COALESCE(c.relation_state,'unfunded_clean') AS state,
                   COALESCE(NULLIF(c.first_deposit_at,''), NULLIF(c.reg_date,''), '') AS ts
            FROM clients c
            WHERE c.customer_no IS NOT NULL AND COALESCE(c.network_score,0)=0 {cli_search} {st_flt_c}
            ORDER BY c.customer_no, COALESCE(c.total_deposits,0) DESC
        ) cc
        UNION ALL
        SELECT 'L'||l.id, l.full_name, 'lead', NULL::bigint, l.id,
               COALESCE(l.relation_state,'unfunded_clean'), COALESCE(l.created_at::text,'')
        FROM leads l WHERE COALESCE(l.network_score,0)=0 {lead_search} {st_flt_l}
        ORDER BY ts DESC
        LIMIT :lim OFFSET :off
    """), p).fetchall()
    return {"view": "unrelated", "total": total, "page": page, "page_size": page_size,
            "rows": [{"ent": r[0], "name": r[1] or r[0], "kind": r[2], "login": r[3],
                      "lead_id": r[4], "state": r[5], "since": str(r[6])[:10] if r[6] else ""} for r in rows]}


def _rep_login(db, ent):
    if not ent.startswith("C"):
        return None
    return db.execute(text("SELECT login FROM clients WHERE customer_no=:c "
                           "ORDER BY COALESCE(total_deposits,0) DESC, login LIMIT 1"),
                      {"c": ent[1:]}).scalar()


@router.get("/relations/summary")
def relations_summary(db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    """Headline counts for the two-table page."""
    st = dict(db.execute(text("SELECT relation_state, COUNT(*) FROM entity_status GROUP BY 1")).fetchall())
    related = db.execute(text("SELECT COUNT(*) FROM entity_status WHERE is_related")).scalar() or 0
    decisive = db.execute(text("SELECT COUNT(*) FROM entity_status WHERE has_decisive")).scalar() or 0
    nda = db.execute(text("SELECT COUNT(DISTINCT customer_no) FROM clients WHERE is_nda")).scalar() or 0
    ftd_pending = db.execute(text("SELECT COUNT(DISTINCT customer_no) FROM clients "
                                  "WHERE relation_state='ftd_pending'")).scalar() or 0
    # the FULL clean side (not just NDA depositors) — clean clients + clean leads, so the two table
    # counts are comparable (related 81k vs clean ~149k, not the misleading "14k").
    clean = db.execute(text("""
        SELECT (SELECT COUNT(DISTINCT customer_no) FROM clients
                WHERE customer_no IS NOT NULL AND COALESCE(network_score,0)=0)
             + (SELECT COUNT(*) FROM leads WHERE COALESCE(network_score,0)=0)""")).scalar() or 0
    return {"related": related, "clean": clean, "decisive": decisive,
            "states": st, "nda": nda, "ftd_pending": ftd_pending}


@router.get("/bonus-eligibility")
def bonus_eligibility(login: int = Query(0), lead_id: int = Query(0),
                      db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    """Welcome-bonus check (BEFORE deposit). A lead/client with a DECISIVE or FAMILY relation to an
    existing customer can't claim the $50 bonus; a weak-only relation → manual review; else eligible."""
    me = _entity_of(db, login or None, lead_id or None)
    if not me:
        return {"eligible": True, "status": "eligible", "reason": ""}
    row = db.execute(text("""SELECT bonus_status, has_decisive, top_reason, is_related
                             FROM entity_status WHERE ent=:e"""), {"e": me}).fetchone()
    if not row:
        return {"eligible": True, "status": "eligible", "reason": "no relation found"}
    status = row[0] or ("blocked" if row[1] else ("review" if row[3] else "eligible"))
    return {"eligible": status == "eligible", "status": status, "reason": row[2] or ""}


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

        # PERF (Jul 7 2026 outage fix): this loop was O(n^3) — for EVERY connected account it
        # rescanned login_list × identifiers (line ~380) and deduped edges by scanning all_edges
        # linearly. One hot identifier shared by thousands of accounts pinned an AnyIO worker on
        # the GIL forever and hung the ENTIRE API (even /health). Now: precomputed source map +
        # edge-key set (O(1)) and hard caps — the graph is for a human to read, cap what we return.
        MAX_PER_IDENT = 100     # accounts pulled per shared IP/CID
        MAX_NODES = 400         # total graph size cap
        src_map = {}
        for i in identifiers:
            src_map.setdefault((i[1], i[2]), []).append(i[0])
        edge_keys = {e["key"] for e in all_edges}
        truncated = False

        # Step 2: Find all accounts using those IPs/CIDs
        for id_type, id_value in new_identifiers:
            if len(all_nodes) >= MAX_NODES:
                truncated = True
                break
            connected = db.execute(text("""
                SELECT DISTINCT ai.login, c.name, c.balance, c.country, c.city,
                       c.agent, ib.name as ib_name, ib.ib_code
                FROM account_identifiers ai
                LEFT JOIN clients c ON c.login = ai.login
                LEFT JOIN ibs ib ON ib.agent_id = c.agent
                WHERE ai.identifier_type = :t AND ai.identifier_value = :v
                AND ai.login != ALL(:exclude)
                LIMIT :cap
            """), {"t": id_type, "v": id_value, "exclude": list(visited_logins),
                   "cap": MAX_PER_IDENT}).fetchall()

            sources = src_map.get((id_type, id_value), [])
            for conn in connected:
                conn_login = conn[0]
                if conn_login and conn_login not in visited_logins:
                    if len(all_nodes) >= MAX_NODES:
                        truncated = True
                        break
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

                    for src in sources:
                        edge_key = f"{min(src, conn_login)}-{max(src, conn_login)}-{id_type}"
                        if edge_key not in edge_keys:
                            edge_keys.add(edge_key)
                            all_edges.append({
                                "key": edge_key,
                                "from": src, "to": conn_login,
                                "type": id_type, "value": id_value,
                                "layer": layer,
                            })

        current_layer_logins = new_logins_this_layer
        if truncated:
            break

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
