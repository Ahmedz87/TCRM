"""
connection_engine.py — "who is this person connected to, and how sure are we?"

Powers the Network/Risk connection intelligence:
  • score_connections(db, login=…|lead_id=…)  -> ranked list of connected accounts,
    each with a CONFIDENCE % and an x/10 score and the signals that fired.
  • connection_groups(db)                      -> connected-component groups across ALL
    signals, each with a deterministic VERDICT (IB-commission farming / bonus abuse /
    toxic trading / swap abuse / hedging ring) + money/IB/bonus stats.
  • group_stats(db, logins)                    -> the money/trading/IB summary for a set.

Confidence model — noisy-OR over the signals that link two accounts:
    conf = 1 - Π(1 - weight_i)
A device match (CID) alone = 1.0 = 100% (10/10); weaker signals (IP, IB, city, payment)
stack toward — but don't trivially reach — 100%.

Signal strength (probability a true same-person/related link exists given the shared token):
    cid 1.00 · mqid 0.97 · email 0.92 · phone/family 0.90 · ip 0.55 · payment 0.55 · ib 0.45 · city 0.30
Strong signals (device/ip/email/phone) FIND the connected accounts; ib/city/payment BOOST
the confidence of accounts already found (they're too broad to enumerate on their own).
"""
import re
from collections import defaultdict
from sqlalchemy import text

SIGNAL_WEIGHT = {
    "cid": 1.00, "mqid": 0.97, "email": 0.92, "similar_email": 0.80, "phone": 0.90, "family": 0.90,
    # reweighted per desk (Jul 2026): IB/agent and city matter MORE than IP; IP is the weakest signal
    "ib": 0.55, "city": 0.45, "payment": 0.55, "ip": 0.30,
}
SIGNAL_LABEL = {
    "cid": "Same device (CID)", "mqid": "Same device (MetaQuotes ID)", "email": "Same email",
    "similar_email": "Similar email", "phone": "Same phone", "family": "Family / same phone",
    "ip": "Same IP address", "payment": "Same payment method", "ib": "Same IB / agent", "city": "Same city",
}
# Signal display priority (CID, IB, City, Family, payment, IP …) — used to pick the headline reason.
SIGNAL_ORDER = ["cid", "mqid", "email", "similar_email", "family", "phone", "ib", "payment", "ip", "city"]

# Connection-tab ORDER requested by the desk: device(CID) first, then IB, City, Family, Email, IP,
# Payment. Lower number = shown first. Used to pick each ring's PRIMARY link and to rank the tab.
LINK_PRIORITY = {"cid": 1, "mqid": 1, "ib": 2, "city": 3, "family": 4, "phone": 4,
                 "email": 5, "similar_email": 5, "payment": 6, "ip": 7, "name": 8}  # IP lowest


def _norm_name(s):
    """Normalise a person name for same-identity comparison: lowercase, keep latin+arabic letters,
    sort the tokens — so 'Ahmed Zaman', 'Zaman Ahmed', 'ahmed  zaman' all collapse to the same key."""
    toks = re.sub("[^a-z؀-ۿ ]", " ", (s or "").lower()).split()
    return " ".join(sorted(toks))

# SQL: normalise an email's LOCAL part → lowercase, drop +tag, remove dots. So ahmed.zaman,
# ahme.dzaman, a.h.m.e.dzaman, ahmedzaman+test all collapse to "ahmedzaman" (Gmail treats dots as
# identical anyway). Used for similar-email linking. Pass the column name in.
def _norm_email_sql(col):
    return r"replace(regexp_replace(lower(split_part(coalesce(%s,''),'@',1)), '\+.*$', '', 'g'), '.', '')" % col


def _norm_email(e):
    e = (e or "").strip().lower()
    loc = e.split("@", 1)[0] if "@" in e else e
    return loc.split("+", 1)[0].replace(".", "")

# IP / device tokens shared by more than this many logins are treated as noise (NAT, shared PC bank).
MAX_TOKEN_FANOUT = 25


def _phone9(p):
    d = re.sub(r"[^0-9]", "", p or "")
    return d[-9:] if len(d) >= 9 else d


def _noisy_or(weights):
    prod = 1.0
    for w in weights:
        prod *= (1.0 - min(0.999, w))
    return 1.0 - prod


def _confidence(signals):
    """signals: set of signal keys. Device match forces ~100%."""
    if "cid" in signals:
        return 100, 10
    conf = _noisy_or([SIGNAL_WEIGHT.get(s, 0.2) for s in signals])
    pct = int(round(conf * 100))
    pct = max(1, min(99, pct))
    return pct, max(1, round(pct / 10))


def _subject(db, login=None, lead_id=None):
    """Resolve the subject's identifying tokens (device ids, ips, email, phone, city, IB)."""
    if login is not None:
        c = db.execute(text("""
            SELECT login, name, email, phone, city, country, agent
            FROM clients WHERE login=:l
        """), {"l": login}).fetchone()
        if not c:
            return None
        ids = db.execute(text("""
            SELECT identifier_type, identifier_value FROM account_identifiers
            WHERE login=:l AND identifier_value NOT IN ('0','')
        """), {"l": login}).fetchall()
        cids = [v for t, v in ids if t == "cid"]
        mqids = [v for t, v in ids if t == "mqid"]
        ips = [v for t, v in ids if t == "ip"]
        return {"kind": "client", "id": login, "login": login, "name": c[1] or f"#{login}",
                "email": (c[2] or "").lower().strip(), "email_norm": _norm_email(c[2]),
                "phone": c[3] or "", "phone9": _phone9(c[3]),
                "city": (c[4] or "").strip(), "country": c[5] or "", "agent": c[6] or 0,
                "cids": cids, "mqids": mqids, "ips": ips}
    if lead_id is not None:
        l = db.execute(text("""
            SELECT id, full_name, email, phone, city, country FROM leads WHERE id=:l
        """), {"l": lead_id}).fetchone()
        if not l:
            return None
        return {"kind": "lead", "id": lead_id, "login": None, "name": l[1] or f"lead#{lead_id}",
                "email": (l[2] or "").lower().strip(), "email_norm": _norm_email(l[2]),
                "phone": l[3] or "", "phone9": _phone9(l[3]),
                "city": (l[4] or "").strip(), "country": l[5] or "", "agent": 0,
                "cids": [], "mqids": [], "ips": []}
    return None


def score_connections(db, login=None, lead_id=None, limit=60):
    """Return the subject's connections ranked by confidence (most-certain first)."""
    subj = _subject(db, login=login, lead_id=lead_id)
    if not subj:
        return {"subject": None, "connections": []}

    # candidate client login -> {signal -> shared value}
    cand = defaultdict(dict)

    # ── strong: shared device/ip tokens (cid/mqid/ip) — clients only ──
    tokens = [("cid", v) for v in subj["cids"]] + [("mqid", v) for v in subj["mqids"]] + \
             [("ip", v) for v in subj["ips"]]
    if tokens:
        rows = db.execute(text("""
            SELECT identifier_type, identifier_value, array_agg(DISTINCT login) AS logins
            FROM account_identifiers
            WHERE (identifier_type, identifier_value) IN :pairs
            GROUP BY identifier_type, identifier_value
            HAVING COUNT(DISTINCT login) <= :fan
        """).bindparams(__import__("sqlalchemy").bindparam("pairs", expanding=True)),
            {"pairs": tokens, "fan": MAX_TOKEN_FANOUT}).fetchall()
        for typ, val, logins in rows:
            for lg in logins:
                if lg != subj["login"]:
                    cand[("client", lg)][typ] = val

    # ── strong: shared email (clients + leads) ──
    if subj["email"]:
        for lg, in db.execute(text(
            "SELECT login FROM clients WHERE LOWER(email)=:e AND login<>:self"),
            {"e": subj["email"], "self": subj["login"] or -1}).fetchall():
            cand[("client", lg)]["email"] = subj["email"]
        for (lid,) in db.execute(text(
            "SELECT id FROM leads WHERE LOWER(email)=:e AND id<>:self"),
            {"e": subj["email"], "self": subj["id"] if subj["kind"] == "lead" else -1}).fetchall():
            cand[("lead", lid)]["email"] = subj["email"]

    # ── SIMILAR email: same normalized local part (dots/+tags moved → same inbox, e.g. ahmed.zaman
    #    ≈ ahme.dzaman ≈ ahmedzaman) OR a ≤2-character typo (ahmedzaman ≈ ahmadzaman). Catches the
    #    relative/duplicate-email trick where a fraudster tweaks 1-4 letters. ──
    sne = subj.get("email_norm") or ""
    sco = re.sub(r"\d", "", sne)                       # letters-only core (ahmedzaman1 ≈ ahmedzaman)
    if len(sne) >= 4:
        nec = _norm_email_sql("email")
        core = f"regexp_replace({nec}, '[0-9]', '', 'g')"
        # DEEP similar-email match (not just a 2-char typo): normalized-equal (dots/+tags) OR same
        # letters-core (ignores digit suffixes) OR Levenshtein ≤3 (letters/order tweaks).
        cond = (f"( {nec} = :ne "
                f"OR (length(:sco) >= 5 AND {core} = :sco) "
                f"OR (length({nec}) >= 7 AND levenshtein({nec}, :ne) <= 3) )")
        p = {"ne": sne, "sco": sco}
        for lg, em in db.execute(text(f"""
            SELECT login, email FROM clients
            WHERE login<>:self AND email IS NOT NULL AND email<>'' AND {cond} LIMIT 120
        """), {**p, "self": subj["login"] or -1}).fetchall():
            if not cand[("client", lg)].get("email"):          # don't downgrade an exact match
                cand[("client", lg)]["similar_email"] = em
        for lid, em in db.execute(text(f"""
            SELECT id, email FROM leads
            WHERE id<>:self AND email IS NOT NULL AND email<>'' AND {cond} LIMIT 120
        """), {**p, "self": subj["id"] if subj["kind"] == "lead" else -1}).fetchall():
            if not cand[("lead", lid)].get("email"):
                cand[("lead", lid)]["similar_email"] = em

    # ── strong: shared phone (family) ──
    if subj["phone9"] and len(subj["phone9"]) >= 7:
        for lg, in db.execute(text("""
            SELECT login FROM clients
            WHERE RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p AND login<>:self
        """), {"p": subj["phone9"], "self": subj["login"] or -1}).fetchall():
            cand[("client", lg)]["family"] = subj["phone"]
        for (lid,) in db.execute(text("""
            SELECT id FROM leads
            WHERE RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p AND id<>:self
        """), {"p": subj["phone9"], "self": subj["id"] if subj["kind"] == "lead" else -1}).fetchall():
            cand[("lead", lid)]["family"] = subj["phone"]

    if not cand:
        return {"subject": _subject_brief(subj), "connections": []}

    client_logins = [cid for (k, cid) in cand if k == "client"]
    lead_ids = [lid for (k, lid) in cand if k == "lead"]

    # enrich candidates + add BOOSTER signals (ib / city / payment)
    cmeta = {}
    if client_logins:
        for r in db.execute(text("""
            SELECT c.login, c.name, c.city, c.country, c.agent, COALESCE(c.balance,0),
                   i.name AS ib_name
            FROM clients c LEFT JOIN ibs i ON i.agent_id=c.agent
            WHERE c.login=ANY(:l)
        """), {"l": client_logins}).fetchall():
            cmeta[("client", r[0])] = {"name": r[1] or f"#{r[0]}", "city": (r[2] or "").strip(),
                                       "country": r[3] or "", "agent": r[4] or 0,
                                       "balance": float(r[5] or 0), "ib_name": r[6] or ""}
    lmeta = {}
    if lead_ids:
        for r in db.execute(text("""
            SELECT id, full_name, city, country FROM leads WHERE id=ANY(:l)
        """), {"l": lead_ids}).fetchall():
            lmeta[("lead", r[0])] = {"name": r[1] or f"lead#{r[0]}", "city": (r[2] or "").strip(),
                                     "country": r[3] or "", "agent": 0, "balance": 0.0, "ib_name": ""}

    # payment methods (real ones) per subject + candidates, for the payment booster
    def real_methods(logins):
        if not logins:
            return set()
        rows = db.execute(text("""
            SELECT DISTINCT lower(trim(method)) FROM transactions
            WHERE login=ANY(:l) AND method IS NOT NULL AND trim(method)<>''
              AND tx_type IN ('deposit','withdrawal')
        """), {"l": logins}).fetchall()
        skip = {"deposit", "withdrawal", "credit", "bonus", "adjustment", ".", ""}
        return {m for (m,) in rows if m and m not in skip and "bonus" not in m and "adjust" not in m}
    subj_methods = real_methods([subj["login"]] if subj["login"] else [])

    out = []
    for key, sigs in cand.items():
        meta = cmeta.get(key) or lmeta.get(key)
        if not meta:
            continue
        # booster: same IB
        if subj["agent"] and meta["agent"] and subj["agent"] == meta["agent"]:
            sigs["ib"] = meta["ib_name"] or f"#{subj['agent']}"
        # booster: same city
        if subj["city"] and meta["city"] and subj["city"].lower() == meta["city"].lower():
            sigs["city"] = meta["city"]
        # collapse mqid into a device signal next to cid for scoring
        conf, x10 = _confidence(set(sigs.keys()))
        reasons = [{"type": s, "label": SIGNAL_LABEL.get(s, s), "value": str(v)[:40]}
                   for s, v in sorted(sigs.items(), key=lambda kv: SIGNAL_ORDER.index(kv[0]) if kv[0] in SIGNAL_ORDER else 99)]
        top = reasons[0]["type"] if reasons else ""
        out.append({
            "kind": key[0], "id": key[1], "login": key[1] if key[0] == "client" else None,
            "name": meta["name"], "city": meta["city"], "country": meta["country"],
            "ib_name": meta["ib_name"], "balance": meta["balance"],
            "confidence": conf, "score10": x10, "reasons": reasons, "top_reason": top,
            "signal_count": len(sigs),
        })

    # payment booster needs candidate methods in batch (client candidates only)
    if subj_methods and client_logins:
        cand_methods = defaultdict(set)
        for lg, m in db.execute(text("""
            SELECT login, lower(trim(method)) FROM transactions
            WHERE login=ANY(:l) AND method IS NOT NULL AND trim(method)<>''
              AND tx_type IN ('deposit','withdrawal')
        """), {"l": client_logins}).fetchall():
            cand_methods[lg].add(m)
        for o in out:
            if o["kind"] == "client":
                shared = subj_methods & cand_methods.get(o["id"], set())
                shared = {m for m in shared if m not in ("deposit", "withdrawal", "credit")}
                if shared and not any(r["type"] == "payment" for r in o["reasons"]):
                    sigset = {r["type"] for r in o["reasons"]} | {"payment"}
                    o["confidence"], o["score10"] = _confidence(sigset)
                    o["reasons"].append({"type": "payment", "label": SIGNAL_LABEL["payment"],
                                         "value": ", ".join(sorted(shared))[:40]})
                    o["signal_count"] = len(sigset)

    out.sort(key=lambda o: (o["confidence"], o["signal_count"], o["balance"]), reverse=True)
    return {"subject": _subject_brief(subj), "connections": out[:limit]}


def _subject_brief(subj):
    return {"kind": subj["kind"], "id": subj["id"], "login": subj["login"], "name": subj["name"],
            "city": subj["city"], "country": subj["country"]}


# ══════════════════════════════════════════════════════════════════════════════
# GROUP analysis — the "Connections" tab: a cluster of linked accounts + a verdict
# ══════════════════════════════════════════════════════════════════════════════
def group_stats(db, logins):
    """Money + trading + IB summary for a set of logins (per-member + totals)."""
    if not logins:
        return {"members": [], "totals": {}}
    rows = db.execute(text("""
        SELECT c.login, c.name, c.city, c.country, c.agent, c.group_name,
               COALESCE(c.credit,0), i.name AS ib_name,
               COALESCE(tx.dep,0), COALESCE(tx.wd,0), COALESCE(tx.bonus,0), tx.last_dep,
               COALESCE(dl.pnl,0), COALESCE(dl.trades,0), dl.winrate, COALESCE(dl.lots,0),
               COALESCE(ic.comm,0)
        FROM clients c
        LEFT JOIN ibs i ON i.agent_id=c.agent
        LEFT JOIN (
            SELECT login, SUM(amount) FILTER (WHERE tx_type='deposit') dep,
                   SUM(amount) FILTER (WHERE tx_type='withdrawal') wd,
                   SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus%') bonus,
                   MAX(tx_date) FILTER (WHERE tx_type='deposit') last_dep
            FROM transactions WHERE login=ANY(:l) GROUP BY login
        ) tx ON tx.login=c.login
        LEFT JOIN (
            SELECT login, SUM(profit) FILTER (WHERE entry=1) pnl,
                   COUNT(*) FILTER (WHERE entry=1 AND direction IN ('buy','sell')) trades,
                   AVG(CASE WHEN entry=1 AND profit>0 THEN 1.0 WHEN entry=1 THEN 0 END) winrate,
                   SUM(volume) FILTER (WHERE direction IN ('buy','sell'))/10000.0 lots
            FROM deals WHERE login=ANY(:l) GROUP BY login
        ) dl ON dl.login=c.login
        LEFT JOIN (
            SELECT client_login, SUM(commission_usd) comm
            FROM ib_commissions WHERE client_login=ANY(:l) GROUP BY client_login
        ) ic ON ic.client_login=c.login
        WHERE c.login=ANY(:l)
    """), {"l": logins}).fetchall()
    members = []
    T = {"deposits": 0.0, "withdrawals": 0.0, "bonus": 0.0, "pnl": 0.0, "lots": 0.0,
         "ib_commission": 0.0, "trades": 0}
    ibs = defaultdict(int)
    islamic = 0
    for r in rows:
        grp = r[5] or ""
        is_isl = ("-IS" in ("-" + grp.upper().replace("\\", "-") + "-")) or ("SWAP" in grp.upper())
        dep, wd, bonus, pnl = float(r[8] or 0), float(r[9] or 0), float(r[10] or 0), float(r[12] or 0)
        comm = float(r[16] or 0)
        m = {"login": r[0], "name": r[1] or f"#{r[0]}", "city": r[2] or "", "country": r[3] or "",
             "agent": r[4] or 0, "group": grp, "credit": float(r[6] or 0), "ib_name": r[7] or "",
             "deposits": dep, "withdrawals": wd, "bonus": bonus,
             "last_deposit": str(r[11]) if r[11] else "", "pnl": pnl, "trades": int(r[13] or 0),
             "win_rate": round(float(r[14]) * 100) if r[14] is not None else None,
             "lots": float(r[15] or 0), "ib_commission": comm, "is_islamic": is_isl}
        members.append(m)
        T["deposits"] += dep; T["withdrawals"] += wd; T["bonus"] += bonus; T["pnl"] += pnl
        T["lots"] += m["lots"]; T["ib_commission"] += comm; T["trades"] += m["trades"]
        if r[7]:
            ibs[r[7]] += 1
        if is_isl:
            islamic += 1
    T["net_to_clients"] = round(T["withdrawals"] - T["deposits"], 2)
    T = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in T.items()}
    members.sort(key=lambda x: x["deposits"] + x["withdrawals"], reverse=True)
    top_ib = sorted(ibs.items(), key=lambda kv: kv[1], reverse=True)
    return {"members": members, "totals": T, "islamic_count": islamic,
            "ib_names": [k for k, _ in top_ib],
            "dominant_ib": top_ib[0][0] if top_ib else "",
            "dominant_ib_share": (top_ib[0][1] / max(1, len(members))) if top_ib else 0}


def classify_group(stats):
    """Deterministic verdicts on a connection group. Returns a list of {tag,severity,title,detail}."""
    m = stats["members"]; T = stats["totals"]
    n = len(m)
    verdicts = []
    if n < 2:
        return verdicts
    dep, wd, bonus = T["deposits"], T["withdrawals"], T["bonus"]
    comm = T["ib_commission"]

    # 1) IB-commission farming — one IB owns most of the group, earns commission, accounts
    #    are bonus-fed / net-negative depositors (the IB profits off introduced churn).
    if stats["dominant_ib"] and stats["dominant_ib_share"] >= 0.5 and comm > 0 and (bonus > 0 or T["net_to_clients"] > 0):
        verdicts.append({
            "tag": "ib_farming", "severity": "high",
            "title": f"IB commission farming — {stats['dominant_ib']}",
            "detail": (f"{int(round(stats['dominant_ib_share']*100))}% of this group is introduced by "
                       f"{stats['dominant_ib']}, who has earned ${comm:,.0f} commission while the group took "
                       f"${bonus:,.0f} in bonus and is net {'+' if T['net_to_clients']>=0 else ''}${T['net_to_clients']:,.0f} "
                       f"to clients. The IB is monetising introduced churn / bonus.")})

    # 2) Bonus abuse / extraction — bonus given and clients pulled out >= what they deposited.
    if bonus > 0 and wd >= dep * 0.95 and wd > 0:
        verdicts.append({
            "tag": "bonus_abuse", "severity": "critical" if wd >= dep * 1.1 else "high",
            "title": "Bonus extraction",
            "detail": (f"The group received ${bonus:,.0f} in bonus and withdrew ${wd:,.0f} against "
                       f"${dep:,.0f} deposited (net {'+' if T['net_to_clients']>=0 else ''}${T['net_to_clients']:,.0f} "
                       f"to clients) — bonus is being converted to withdrawable cash.")})

    # 3) Toxic / latency-style — a member with near-perfect win-rate on real volume.
    toxic = [x for x in m if (x["win_rate"] or 0) >= 85 and x["trades"] >= 40]
    if toxic:
        names = ", ".join(f"#{x['login']} ({x['win_rate']}%)" for x in toxic[:3])
        verdicts.append({
            "tag": "toxic", "severity": "high",
            "title": "Toxic / abnormal win-rate",
            "detail": (f"{len(toxic)} account(s) win >=85% of trades on real volume ({names}) - "
                       f"a signature of latency/feed arbitrage or offsetting, not normal trading.")
        })

    # 4) Swap-free farming — Islamic accounts trading actively (carry harvested swap-free).
    isl_traders = [x for x in m if x["is_islamic"] and x["trades"] >= 20]
    if stats["islamic_count"] >= 2 and isl_traders:
        verdicts.append({
            "tag": "swap_free", "severity": "medium",
            "title": "Swap-free (Islamic) cluster",
            "detail": (f"{stats['islamic_count']} accounts are swap-free and {len(isl_traders)} trade actively — "
                       f"review for overnight carry harvested without paying swap.")})

    # 5) Internal money shuffling — one member feeds others (one big loser, others win).
    losers = [x for x in m if x["pnl"] < -200]
    winners = [x for x in m if x["pnl"] > 200]
    if losers and winners and bonus > 0:
        biggest_loser = min(m, key=lambda x: x["pnl"])
        verdicts.append({
            "tag": "offsetting", "severity": "high",
            "title": "Offsetting inside the group",
            "detail": (f"#{biggest_loser['login']} is the designated loser (P&L ${biggest_loser['pnl']:,.0f}, "
                       f"bonus ${biggest_loser['bonus']:,.0f}) while {len(winners)} linked accounts win — "
                       f"the loss (funded by bonus) is moved to clean winners that can withdraw.")})

    if not verdicts:
        verdicts.append({"tag": "linked", "severity": "low", "title": "Linked accounts",
                         "detail": f"{n} accounts are linked but show no strong abuse pattern yet."})
    return verdicts


def _risk_rank(severity):
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 0)


def refresh_account(db, login):
    """Wire a freshly-opened account into the network the moment it's created. score_connections()
    reads live, but the persisted network_edges layer (network graph + abuse views + clients.
    network_score) is refreshed here so the new account appears at once. Builds the immediately-known
    clients-table links (same phone = family, same name, same IB); device/IP edges are added by the
    bridge when the account first logs into MT. Idempotent + guarded."""
    if not login:
        return
    try:
        p = {"lg": int(login)}
        # same phone (last 9 digits) -> family/household
        db.execute(text("""
            INSERT INTO network_edges (login_a, login_b, reason, value)
            SELECT LEAST(a.login,b.login), GREATEST(a.login,b.login), 'family', a.phone
            FROM clients a JOIN clients b
              ON RIGHT(regexp_replace(COALESCE(b.phone,''),'[^0-9]','','g'),9) =
                 RIGHT(regexp_replace(COALESCE(a.phone,''),'[^0-9]','','g'),9)
             AND b.login <> a.login AND b.login IS NOT NULL
            WHERE a.login=:lg AND LENGTH(regexp_replace(COALESCE(a.phone,''),'[^0-9]','','g'))>=9
            ON CONFLICT DO NOTHING
        """), p)
        # same exact full name
        db.execute(text("""
            INSERT INTO network_edges (login_a, login_b, reason, value)
            SELECT LEAST(a.login,b.login), GREATEST(a.login,b.login), 'family', a.name
            FROM clients a JOIN clients b ON LOWER(TRIM(b.name))=LOWER(TRIM(a.name))
             AND b.login <> a.login AND b.login IS NOT NULL
            WHERE a.login=:lg AND LENGTH(TRIM(COALESCE(a.name,'')))>5
            ON CONFLICT DO NOTHING
        """), p)
        # same IB / agent
        db.execute(text("""
            INSERT INTO network_edges (login_a, login_b, reason, value)
            SELECT LEAST(a.login,b.login), GREATEST(a.login,b.login), 'ib', CAST(a.agent AS TEXT)
            FROM clients a JOIN clients b ON b.agent=a.agent AND b.login <> a.login AND b.login IS NOT NULL
            WHERE a.login=:lg AND a.agent>0
            ON CONFLICT DO NOTHING
        """), p)
        # recompute this login's network_score from its edges
        db.execute(text("""
            UPDATE clients c SET network_score = COALESCE((
                SELECT LEAST(100, SUM(CASE reason WHEN 'cid' THEN 50 WHEN 'mqid' THEN 45 WHEN 'ip' THEN 35
                            WHEN 'family' THEN 30 WHEN 'similar_email' THEN 20 WHEN 'city' THEN 15
                            WHEN 'ib' THEN 10 ELSE 5 END))
                FROM network_edges WHERE login_a=:lg OR login_b=:lg), 0)
            WHERE c.login=:lg
        """), p)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[connection] refresh_account({login}) failed: {e}", flush=True)


def connection_groups(db, limit=60, min_size=2):
    """Connected-component groups across device(cid/mqid)/ip/phone/email, annotated with
    money/IB stats + a deterministic verdict. The Network 'Connections' tab."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    links = defaultdict(list)  # not used heavily; reason tracking
    # device + ip from account_identifiers (fan-out capped)
    for typ, val, members in db.execute(text("""
        SELECT identifier_type, identifier_value, array_agg(DISTINCT login) m
        FROM account_identifiers
        WHERE identifier_type IN ('cid','mqid','ip','email') AND identifier_value NOT IN ('0','')
        GROUP BY identifier_type, identifier_value
        HAVING COUNT(DISTINCT login) BETWEEN 2 AND :fan
    """), {"fan": MAX_TOKEN_FANOUT}).fetchall():
        ms = sorted(set(members))
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                union(ms[i], ms[j]); links[find(ms[i])].append((ms[i], ms[j], typ))
    # shared phone
    for phone, members in db.execute(text("""
        SELECT phone, array_agg(DISTINCT login) m FROM clients
        WHERE phone IS NOT NULL AND length(trim(phone))>=7
        GROUP BY phone HAVING COUNT(DISTINCT login) BETWEEN 2 AND :fan
    """), {"fan": MAX_TOKEN_FANOUT}).fetchall():
        ms = sorted(set(members))
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                union(ms[i], ms[j]); links[find(ms[i])].append((ms[i], ms[j], "phone"))
    # similar email — group by NORMALIZED local part (dots/+tags removed) so ahmed.zaman, ahme.dzaman,
    # ahmedzaman all link into one ring (exact-equality on the normalized inbox; safe, no false rings)
    _NE = _norm_email_sql("email")
    for nemail, members in db.execute(text(f"""
        SELECT {_NE} ne, array_agg(DISTINCT login) m FROM clients
        WHERE email IS NOT NULL AND email<>'' AND length({_NE})>=4
        GROUP BY {_NE} HAVING COUNT(DISTINCT login) BETWEEN 2 AND :fan
    """), {"fan": MAX_TOKEN_FANOUT}).fetchall():
        ms = sorted(set(members))
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                union(ms[i], ms[j]); links[find(ms[i])].append((ms[i], ms[j], "similar_email"))

    comp = defaultdict(set)
    for node in list(parent):
        comp[find(node)].add(node)
    comps = [(root, sorted(ms)) for root, ms in comp.items() if min_size <= len(ms) <= MAX_TOKEN_FANOUT]

    # ── PRE-RANK cheaply (no deals): one pass over transactions for dep/wd/bonus per login ──
    tx_by_login = {}
    for lg, dep, wd, bonus in db.execute(text("""
        SELECT login, COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit'),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal'),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus%'),0)
        FROM transactions GROUP BY login
    """)).fetchall():
        tx_by_login[lg] = (float(dep), float(wd), float(bonus))
    scored = []
    for root, members in comps:
        dep = wd = bonus = 0.0
        for lg in members:
            d, w, b = tx_by_login.get(lg, (0, 0, 0))
            dep += d; wd += w; bonus += b
        exposure = bonus + max(0.0, wd - dep)
        scored.append((exposure, len(members), root, members))
    # keep the most exposed components, then run the heavy per-group analysis only on those
    scored.sort(reverse=True, key=lambda x: (x[0], x[1]))
    top = scored[:max(limit * 2, limit)]

    # identity per member — distinguish ONE trader's own multiple accounts (same phone + same name)
    # from a ring of DIFFERENT people sharing a device/IP. The Connections tab should only show the
    # latter; a single trader's own accounts are normal (and, if abusing, belong on the Abuse page).
    all_member_logins = sorted({lg for _, _, _, ms in top for lg in ms})
    ident = {}
    if all_member_logins:
        for lg, ph, nm, em in db.execute(text("""
            SELECT login, RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9), name, email
            FROM clients WHERE login=ANY(:l)
        """), {"l": all_member_logins}).fetchall():
            ident[lg] = (ph if ph and len(ph) >= 7 else "", _norm_name(nm), _norm_email(em))

    groups = []
    for exposure, size, root, members in top:
        st = group_stats(db, members)
        verdicts = classify_group(st)
        sev = max((v["severity"] for v in verdicts), key=_risk_rank, default="low")
        reasons = sorted({r[2] for r in links.get(root, [])},
                         key=lambda s: SIGNAL_ORDER.index(s) if s in SIGNAL_ORDER else 99)
        phones = {ident.get(lg, ("", "", ""))[0] for lg in members if ident.get(lg, ("", "", ""))[0]}
        names = {ident.get(lg, ("", "", ""))[1] for lg in members if ident.get(lg, ("", "", ""))[1]}
        emails = {ident.get(lg, ("", "", ""))[2] for lg in members if ident.get(lg, ("", "", ""))[2]}
        n_people = max(len(phones), len(names)) or len(members)
        # ONE client's own accounts (exclude from the different-people rings):
        #  • single phone AND single (fuzzy) name  → same person, OR
        #  • single phone AND single email         → same person (no two DIFFERENT people share both).
        # Family = same phone but DIFFERENT names, which stays (len(names)>1).
        same_person = ((len(phones) <= 1 and len(names) <= 1 and bool(phones or names))
                       or (len(phones) <= 1 and len(emails) <= 1 and bool(phones) and bool(emails)))
        # primary link = the highest-priority signal that actually links this ring (CID first)
        primary = sorted(reasons, key=lambda s: LINK_PRIORITY.get(s, 99))[0] if reasons else "link"
        groups.append({
            "id": int(root), "size": len(members), "members": st["members"],
            "totals": st["totals"], "ib_names": st["ib_names"], "dominant_ib": st["dominant_ib"],
            "link_reasons": reasons, "primary_link": primary, "verdicts": verdicts, "severity": sev,
            "same_person": same_person, "n_people": n_people,
            "top_verdict": verdicts[0]["title"] if verdicts else "Linked accounts",
        })
    # Connections tab = rings of DIFFERENT people only (drop a single trader's own-account clusters)
    multi = [g for g in groups if not g["same_person"]]
    # ORDER as the desk asked: by link type (CID → IB → City → Family → Email → IP → Payment), then
    # by severity, then by money exposure — so device-linked rings surface first.
    multi.sort(key=lambda g: (LINK_PRIORITY.get(g["primary_link"], 99),
                              -_risk_rank(g["severity"]),
                              -(g["totals"].get("bonus", 0) + max(0, g["totals"].get("net_to_clients", 0)))))
    out_groups = multi[:limit]
    # attach the CONNECTION detail (what actually links the members) only to the groups we return
    for g in out_groups:
        g["links"] = group_links(db, [m["login"] for m in g["members"]])
    return out_groups


def group_links(db, logins):
    """The 'how are they connected' web: each shared identifier (device CID/MQID, IP, email, phone,
    same name) and the exact group members that share it. This is the CONNECTION evidence — shown
    before/alongside the abuse verdict so the desk sees the links first, doubt second."""
    if not logins:
        return []
    out = []
    for typ, val, m in db.execute(text("""
        SELECT identifier_type, identifier_value, array_agg(DISTINCT login ORDER BY login) m
        FROM account_identifiers
        WHERE login = ANY(:l) AND identifier_type IN ('cid','mqid','ip','email')
          AND identifier_value NOT IN ('0','')
        GROUP BY identifier_type, identifier_value
        HAVING COUNT(DISTINCT login) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": typ, "value": str(val)[:60], "logins": [int(x) for x in m]})
    for phone, m in db.execute(text("""
        SELECT phone, array_agg(DISTINCT login ORDER BY login) m FROM clients
        WHERE login = ANY(:l) AND phone IS NOT NULL AND length(trim(phone)) >= 7
        GROUP BY phone HAVING COUNT(DISTINCT login) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": "phone", "value": str(phone)[:60], "logins": [int(x) for x in m]})
    for nm, m in db.execute(text("""
        SELECT LOWER(TRIM(name)) nm, array_agg(DISTINCT login ORDER BY login) m FROM clients
        WHERE login = ANY(:l) AND length(trim(COALESCE(name,''))) > 5
        GROUP BY LOWER(TRIM(name)) HAVING COUNT(DISTINCT login) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": "name", "value": str(nm)[:60], "logins": [int(x) for x in m]})
    # similar/variant emails within the group (normalized inbox shared by ≥2 DIFFERENT raw emails)
    _NE = _norm_email_sql("email")
    for ne, m, ex in db.execute(text(f"""
        SELECT {_NE} ne, array_agg(DISTINCT login ORDER BY login) m, string_agg(DISTINCT lower(email), ', ') ex
        FROM clients WHERE login = ANY(:l) AND email IS NOT NULL AND email<>'' AND length({_NE})>=4
        GROUP BY {_NE} HAVING COUNT(DISTINCT login) >= 2 AND COUNT(DISTINCT lower(email)) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": "similar_email", "value": str(ex)[:70], "logins": [int(x) for x in m]})
    out.sort(key=lambda x: (SIGNAL_ORDER.index(x["type"]) if x["type"] in SIGNAL_ORDER else 99, -len(x["logins"])))
    return out
