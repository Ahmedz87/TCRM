"""
abuse_engine.py — v3.  Fewer, deeper, PROVABLE abuse detection for TNFX.

Design goals (from desk feedback):
  1. FEWER cases  — only flag when several independent signals agree. A lone
     account with two opposite trades is NOT a case; a ring of device-linked
     bonus accounts hedging each other IS.
  2. DEEPER       — catch the clever ones: bonus rings (linked accounts hedging
     each other) and chip-dumping (one account deliberately feeds money to a
     linked account). Not just single-account heuristics.
  3. PROVABLE     — every case stores STRUCTURED evidence (evidence_json): the
     exact opposing trade legs, the signals that fired with their weights, the
     money flow, and the device/IP/phone links. The UI renders this as a story.

Detector types (clear, named):
  bonus_ring     linked accounts (shared device/phone) hedging each other on bonus
  bonus_cashout  took bonus, barely traded, withdrew >= deposits ("double & dash")
  chip_dump      linked accounts transferring money via paired opposite trades
  swap_carry     swap-free (Islamic) account farming overnight carry
  toxic_arb      near-perfect win-rate on ultra-short holds (feed-lag arbitrage)

Score = sum of fired-signal weights (cap 100). Severity: >=75 critical, >=60 high,
>=50 medium, <50 not flagged.  Idempotent UPSERT on (abuse_type, login_a, symbol).
Grounded against the live data (see git history of diag scripts): swap field is
~empty -> overnight derived structurally; is_islamic from group_name -IS token;
01-05 UTC is the busiest window so 'night' alone is not a signal.
"""
import json
from bisect import bisect_right
from collections import defaultdict, deque
from sqlalchemy import text

FLAG_THRESHOLD = 50


def severity_for(score):
    if score >= 75: return "critical"
    if score >= 60: return "high"
    if score >= 50: return "medium"
    return None


def _swapfree_sql(col):
    return (f"('-' || REPLACE(UPPER(COALESCE({col},'')),'\\','-') || '-' LIKE '%-IS-%' "
            f"OR UPPER(COALESCE({col},'')) LIKE '%SWAP%')")


# ── schema ──────────────────────────────────────────────────────────────────────
def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS abuse_cases (
            id                BIGSERIAL PRIMARY KEY,
            abuse_type        VARCHAR(64),
            severity          VARCHAR(16),
            login_a           BIGINT,
            login_b           BIGINT,
            all_logins        TEXT,
            symbol            VARCHAR(32),
            risk_score        INTEGER DEFAULT 0,
            confidence        INTEGER DEFAULT 0,
            network_score     INTEGER DEFAULT 0,
            evidence          TEXT,
            total_deposits    DOUBLE PRECISION DEFAULT 0,
            exposure          DOUBLE PRECISION DEFAULT 0,
            status            VARCHAR(16) DEFAULT 'open',
            auto_action       VARCHAR(32),
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW(),
            auto_action_taken BOOLEAN DEFAULT FALSE
        )
    """))
    # structured evidence for the investigation UI
    db.execute(text("ALTER TABLE abuse_cases ADD COLUMN IF NOT EXISTS evidence_json TEXT"))
    db.execute(text("ALTER TABLE abuse_cases ADD COLUMN IF NOT EXISTS hot BOOLEAN DEFAULT FALSE"))
    db.execute(text("ALTER TABLE abuse_cases ADD COLUMN IF NOT EXISTS kpis TEXT"))
    db.execute(text("CREATE INDEX IF NOT EXISTS abuse_cases_type_idx ON abuse_cases(abuse_type)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS abuse_cases_sev_idx  ON abuse_cases(severity)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS abuse_cases_la_idx   ON abuse_cases(login_a)"))
    # dedup key includes login_b so pair-based types (margin_partner/chip_dump) with a
    # shared winner on the same symbol don't collapse into one row. Drop the old
    # (type,login_a,symbol) index if present.
    db.execute(text("DROP INDEX IF EXISTS abuse_cases_uq"))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS abuse_cases_uq2 "
                    "ON abuse_cases(abuse_type, login_a, COALESCE(login_b,0), COALESCE(symbol,''))"))
    db.execute(text(f"""
        UPDATE trading_accounts SET is_islamic = {_swapfree_sql('group_name')}
        WHERE is_islamic IS DISTINCT FROM {_swapfree_sql('group_name')}
    """))
    db.commit()


def save_case(db, abuse_type, logins, symbol, score, confidence, net_score,
              evidence_text, evidence_obj, deposits, exposure, hot=False):
    sev = severity_for(score)
    if not sev:
        return False
    login_a = logins[0]
    login_b = logins[1] if len(logins) > 1 else None
    kpis = json.dumps((evidence_obj or {}).get("kpis") or [])
    db.execute(text("""
        INSERT INTO abuse_cases
            (abuse_type, severity, login_a, login_b, all_logins, symbol,
             risk_score, confidence, network_score, evidence, evidence_json, hot, kpis,
             total_deposits, exposure, status, created_at, updated_at)
        VALUES (:t,:sev,:la,:lb,:al,:sym,:risk,:conf,:ns,:ev,:ej,:hot,:kpis,:dep,:exp,'open',NOW(),NOW())
        ON CONFLICT (abuse_type, login_a, COALESCE(login_b,0), COALESCE(symbol,'')) DO UPDATE SET
            severity=EXCLUDED.severity, risk_score=EXCLUDED.risk_score,
            confidence=EXCLUDED.confidence, network_score=EXCLUDED.network_score,
            evidence=EXCLUDED.evidence, evidence_json=EXCLUDED.evidence_json, hot=EXCLUDED.hot,
            kpis=EXCLUDED.kpis, total_deposits=EXCLUDED.total_deposits, exposure=EXCLUDED.exposure,
            all_logins=EXCLUDED.all_logins, login_b=EXCLUDED.login_b, updated_at=NOW()
        WHERE abuse_cases.status NOT IN ('resolved','frozen')
    """), {"t": abuse_type, "sev": sev, "la": login_a, "lb": login_b,
           "al": ",".join(str(x) for x in logins), "sym": symbol,
           "risk": int(round(score)), "conf": int(confidence), "ns": int(net_score),
           "ev": evidence_text, "ej": json.dumps(evidence_obj), "hot": bool(hot),
           "kpis": kpis, "dep": float(deposits or 0), "exp": float(exposure or 0)})
    return True


def score_signals(signals):
    """signals: list of dicts with weight + hit. Returns (score, fired_count)."""
    score = sum(s["weight"] for s in signals if s.get("hit"))
    fired = sum(1 for s in signals if s.get("hit"))
    return min(100, score), fired


# ── linking: build REAL clusters from shared device(cid/mqid) + phone ───────────
def build_clusters(db):
    """Connected components of accounts that share a device (cid/mqid), an IP, or a
    phone number. Returns list of dicts {members:set, links:[(a,b,reason,value)]}.
    IP is included but weak — it only matters when corroborated by a trade pattern."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb

    links = []  # (login_a, login_b, reason, value)
    # device + ip sharing from account_identifiers
    rows = db.execute(text("""
        SELECT identifier_type, identifier_value, array_agg(DISTINCT login) AS logins
        FROM account_identifiers
        WHERE identifier_type IN ('cid','mqid','ip') AND identifier_value NOT IN ('0','')
        GROUP BY identifier_type, identifier_value
        HAVING COUNT(DISTINCT login) BETWEEN 2 AND 15
    """)).fetchall()
    for typ, val, members in rows:
        members = sorted(set(members))
        for i in range(len(members)):
            for j in range(i+1, len(members)):
                union(members[i], members[j])
                links.append((members[i], members[j], typ, val))
    # shared phone (strong: same person/household) from clients
    prows = db.execute(text("""
        SELECT phone, array_agg(DISTINCT login) AS logins
        FROM clients WHERE phone IS NOT NULL AND length(trim(phone)) >= 6
        GROUP BY phone HAVING COUNT(DISTINCT login) BETWEEN 2 AND 15
    """)).fetchall()
    for phone, members in prows:
        members = sorted(set(members))
        for i in range(len(members)):
            for j in range(i+1, len(members)):
                union(members[i], members[j])
                links.append((members[i], members[j], 'phone', phone))

    comp = defaultdict(set)
    for a, b, *_ in links:
        comp[find(a)].add(a); comp[find(a)].add(b)
    # attach links to their component
    out = []
    comp_links = defaultdict(list)
    for a, b, reason, val in links:
        comp_links[find(a)].append((a, b, reason, val))
    for root, members in comp.items():
        if 2 <= len(members) <= 15:
            out.append({"members": members, "links": comp_links[root]})
    return out


def _link_strength(reasons):
    """Strongest device link present -> network_score and a label."""
    if 'cid' in reasons:   return 100, 'same device (CID)'
    if 'mqid' in reasons:  return 90,  'same device (MetaQuotes ID)'
    if 'phone' in reasons: return 80,  'same phone number'
    if 'ip' in reasons:    return 55,  'same IP address'
    return 40, 'linked'


def fifo_holds(deals):
    opens = deque(); holds = []
    for entry, direction, vol, profit, t in deals:
        if entry == 0:
            opens.append([t, vol or 0.0])
        elif entry == 1:
            rem = vol or 0.0
            while rem > 1e-9 and opens:
                o = opens[0]; take = min(rem, o[1])
                holds.append((o[0], t, take, t - o[0], (t//86400) != (o[0]//86400)))
                o[1] -= take; rem -= take
                if o[1] <= 1e-9: opens.popleft()
    return holds


def cluster_tradeable(db, members, cap=3000):
    """Return cluster members whose trade count is bounded (excludes mega-scalpers
    that would blow up memory on a full deals pull). Rings/dumps are small bonus
    accounts, not 50k-trade scalpers — so this also improves precision."""
    rows = db.execute(text("""
        SELECT login, count(*) FROM deals
        WHERE login=ANY(:l) AND direction IN ('buy','sell')
        GROUP BY login
    """), {"l": members}).fetchall()
    return [int(lg) for lg, c in rows if 0 < c <= cap]


def money_flow(db, logins):
    r = db.execute(text("""
        SELECT COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit'),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus_dep%'),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal'),0)
        FROM transactions WHERE login=ANY(:l)
    """), {"l": logins}).fetchone()
    dep, bonus, wd = float(r[0]), float(r[1]), float(r[2])
    credit = float(db.execute(text(
        "SELECT COALESCE(SUM(credit),0) FROM trading_accounts WHERE login=ANY(:l)"),
        {"l": logins}).scalar() or 0)
    return {"deposits": dep, "bonus": max(bonus, credit), "withdrawals": wd,
            "net_to_client": round(wd - dep, 2)}


def accounts_summary(db, logins):
    rows = db.execute(text("""
        SELECT c.login, c.name, c.country, COALESCE(ta.balance,c.balance,0),
               COALESCE(ta.credit,c.credit,0), COALESCE(c.total_deposits,0),
               COALESCE(c.total_withdrawals,0), c.group_name
        FROM clients c LEFT JOIN trading_accounts ta ON ta.login=c.login
        WHERE c.login=ANY(:l)
    """), {"l": logins}).fetchall()
    return [{"login": r[0], "name": r[1], "country": r[2], "balance": float(r[3]),
             "credit": float(r[4]), "deposits": float(r[5]), "withdrawals": float(r[6]),
             "group": r[7]} for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# 1. BONUS RING — linked accounts hedging each other while holding bonus
# ══════════════════════════════════════════════════════════════════════════════
def detect_bonus_ring(db, clusters):
    n = 0
    for cl in clusters:
        members = sorted(cl["members"])
        meta = db.execute(text("""
            SELECT COALESCE(SUM(credit),0), COALESCE(SUM(balance),0)
            FROM trading_accounts WHERE login=ANY(:l)
        """), {"l": members}).fetchone()
        credit, balance = float(meta[0]), float(meta[1])
        bonus_logins = [r[0] for r in db.execute(text("""
            SELECT DISTINCT login FROM transactions WHERE login=ANY(:l) AND tx_type ILIKE 'bonus%'
            UNION SELECT login FROM trading_accounts WHERE login=ANY(:l) AND credit>0
        """), {"l": members}).fetchall()]
        if len(bonus_logins) < 1 or (credit <= 0 and not bonus_logins):
            continue
        tradeable = cluster_tradeable(db, members)
        if len(tradeable) < 2:
            continue
        # cross-account hedge pairs on opening trades (bounded member set)
        opens = db.execute(text("""
            SELECT login, symbol, direction, volume, deal_time
            FROM deals WHERE login=ANY(:l) AND entry=0 AND direction IN ('buy','sell')
            ORDER BY symbol, deal_time LIMIT 40000
        """), {"l": tradeable}).fetchall()
        by_sym = defaultdict(list)
        for lg, s, d, v, t in opens:
            by_sym[s].append((lg, d, v or 0.0, t))
        proof = []; involved = set(); top_sym = None; top_n = 0
        for sym, ts in by_sym.items():
            buys = [x for x in ts if x[1] == 'buy']
            sells = [x for x in ts if x[1] == 'sell']
            used = set(); here = 0
            for b in buys:
                for i, s in enumerate(sells):
                    if i in used or s[0] == b[0]:
                        continue
                    gap = abs(b[3]-s[3])
                    if gap <= 15 and max(b[2], s[2]) > 0 and abs(b[2]-s[2])/max(b[2], s[2]) <= 0.4:
                        used.add(i); here += 1; involved.add(b[0]); involved.add(s[0])
                        if len(proof) < 30:
                            # ticket #76: these are OPENING legs only (entry=0), so the
                            # only cross-account timing available is the open-gap (s).
                            proof.append({"sym": sym, "a_login": b[0], "a_dir": "buy",
                                          "a_vol": round(b[2]/100, 2), "b_login": s[0],
                                          "b_dir": "sell", "b_vol": round(s[2]/100, 2),
                                          "a_open": int(b[3]), "b_open": int(s[3]),
                                          "open_gap_s": int(gap),
                                          "t": int(min(b[3], s[3])), "gap_s": int(gap)})
                        break
            if here > top_n:
                top_n = here; top_sym = sym
        cross_pairs = len(proof) if len(proof) < 30 else sum(1 for _ in proof)
        cross_pairs = top_n if top_n else len(proof)
        total_pairs = sum(1 for p in proof) + max(0, top_n - len([p for p in proof if p['sym']==top_sym]))
        total_pairs = len(proof)
        if total_pairs < 2:
            continue
        reasons = {r[2] for r in cl["links"]}
        net_score, link_label = _link_strength(reasons)
        drain = (credit > 0 and balance < credit * 0.2)
        mf = money_flow(db, members)
        signals = [
            {"icon": "🔗", "label": "Linked accounts", "weight": 28,
             "detail": f"{len(cl['members'])} accounts · {link_label}", "hit": True},
            {"icon": "🔄", "label": "Hedged each other", "weight": 30,
             "detail": f"{total_pairs} opposite pairs, ≤15s apart, matched volume", "hit": total_pairs >= 2},
            {"icon": "🎁", "label": "Bonus-funded", "weight": 22,
             "detail": f"${mf['bonus']:,.0f} bonus across the ring", "hit": mf['bonus'] > 0},
            {"icon": "💸", "label": "Drained / cashed out", "weight": 20,
             "detail": (f"withdrew ${mf['withdrawals']:,.0f}" if mf['withdrawals'] > 0
                        else "balance near zero") , "hit": drain or mf['withdrawals'] > mf['deposits']},
        ]
        score, fired = score_signals(signals)
        if score < FLAG_THRESHOLD or fired < 2:
            continue
        conf = int(min(99, 55 + score*0.4 + (10 if 'cid' in reasons or 'mqid' in reasons else 0)))
        members_l = sorted(involved | set(bonus_logins) or set(members))
        headline = (f"{len(cl['members'])} linked accounts hedged each other on {top_sym} "
                    f"while holding ${mf['bonus']:,.0f} bonus")
        ev_obj = {"headline": headline, "at_risk": mf['bonus'], "signals": signals,
                  "kpis": [{"label": "Accounts", "value": str(len(cl['members']))},
                           {"label": "Hedge pairs", "value": str(total_pairs)},
                           {"label": "Bonus", "value": f"${mf['bonus']:,.0f}"},
                           {"label": "Withdrawn", "value": f"${mf['withdrawals']:,.0f}"}],
                  "proof_pairs": proof, "money_flow": mf,
                  "links": [{"a": a, "b": b, "reason": r, "value": v} for a, b, r, v in cl["links"][:20]],
                  "accounts": accounts_summary(db, members)}
        text_ev = (f"BONUS RING — {headline}. {total_pairs} cross-account hedge pairs via "
                   f"{link_label}. Logins {members[:6]}.")
        if save_case(db, 'bonus_ring', members, top_sym, score, conf, net_score,
                     text_ev, ev_obj, mf['deposits'], mf['bonus']):
            n += 1
    db.commit()
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 2. CHIP DUMP — linked accounts transferring money via paired opposite CLOSES
# ══════════════════════════════════════════════════════════════════════════════
def detect_chip_dump(db, clusters):
    n = 0
    for cl in clusters:
        members = sorted(cl["members"])
        tradeable = cluster_tradeable(db, members, cap=4000)
        if len(tradeable) < 2:
            continue
        closes = db.execute(text("""
            SELECT login, symbol, direction, volume, profit, deal_time
            FROM deals WHERE login=ANY(:l) AND entry=1 AND direction IN ('buy','sell')
              AND profit IS NOT NULL AND profit <> 0
            ORDER BY symbol, deal_time LIMIT 40000
        """), {"l": tradeable}).fetchall()
        # opens for the same accounts, so each closed position can show its OPEN time/hold
        opens = db.execute(text("""
            SELECT login, symbol, deal_time
            FROM deals WHERE login=ANY(:l) AND entry=0 AND direction IN ('buy','sell')
            ORDER BY deal_time LIMIT 40000
        """), {"l": tradeable}).fetchall()
        opens_by = defaultdict(list)
        for lg, s, t in opens:
            opens_by[(lg, s)].append(t)
        def open_time(login, sym, close_t):
            arr = opens_by.get((login, sym))
            if not arr:
                return None
            i = bisect_right(arr, close_t) - 1   # latest open at/before the close
            return arr[i] if i >= 0 else None

        by_sym = defaultdict(list)
        for lg, s, d, v, p, t in closes:
            by_sym[s].append((lg, d, v or 0.0, p or 0.0, t))
        # ordered-pair transfer: loser_login -> winner_login amount
        transfer = defaultdict(float); count = defaultdict(int); proof = []
        for sym, ts in by_sym.items():
            for i in range(len(ts)):
                a = ts[i]
                for j in range(i+1, len(ts)):
                    b = ts[j]
                    if b[4] - a[4] > 60:
                        break
                    if a[0] == b[0] or a[1] == b[1]:
                        continue          # need different accounts, opposite directions
                    if (a[3] > 0) == (b[3] > 0):
                        continue          # need one winner + one loser
                    if max(a[2], b[2]) <= 0 or abs(a[2]-b[2])/max(a[2], b[2]) > 0.4:
                        continue          # matched size
                    win, lose = (a, b) if a[3] > 0 else (b, a)
                    amt = min(abs(win[3]), abs(lose[3]))
                    key = (lose[0], win[0])
                    transfer[key] += amt; count[key] += 1
                    if len(proof) < 30:
                        w_open = open_time(win[0], sym, win[4])
                        l_open = open_time(lose[0], sym, lose[4])
                        # ticket #76/#99: per-leg open→close hold (s) + cross-account
                        # open-gap / close-gap (s). deal_time is a bigint epoch so all
                        # of these are plain second differences.
                        open_gap = (abs(w_open - l_open) if (w_open and l_open) else None)
                        close_gap = int(abs(win[4] - lose[4]))
                        proof.append({"sym": sym,
                                      "a_login": win[0], "a_dir": win[1], "a_vol": round(win[2]/100, 2),
                                      "a_profit": round(win[3], 2), "a_close": int(win[4]),
                                      "a_open": int(w_open) if w_open else None,
                                      "a_hold": int(win[4]-w_open) if w_open else None,
                                      "b_login": lose[0], "b_dir": lose[1], "b_vol": round(lose[2]/100, 2),
                                      "b_profit": round(lose[3], 2), "b_close": int(lose[4]),
                                      "b_open": int(l_open) if l_open else None,
                                      "b_hold": int(lose[4]-l_open) if l_open else None,
                                      "open_gap_s": int(open_gap) if open_gap is not None else None,
                                      "close_gap_s": close_gap,
                                      "t": int(min(win[4], lose[4])), "gap_s": close_gap})
        if not transfer:
            continue
        (lose_l, win_l), amt = max(transfer.items(), key=lambda kv: kv[1])
        c = count[(lose_l, win_l)]
        if c < 4 or amt < 200:
            continue
        reasons = {r[2] for r in cl["links"]}
        net_score, link_label = _link_strength(reasons)
        mf = money_flow(db, [lose_l, win_l])
        signals = [
            {"icon": "🔗", "label": "Linked accounts", "weight": 26,
             "detail": link_label, "hit": True},
            {"icon": "🎯", "label": "One-way transfer", "weight": 34,
             "detail": f"#{lose_l} lost to #{win_l} in {c} paired trades", "hit": c >= 4},
            {"icon": "💵", "label": "Money moved", "weight": 24,
             "detail": f"~${amt:,.0f} shifted via matched opposite trades", "hit": amt >= 200},
            {"icon": "💸", "label": "Winner withdrew", "weight": 16,
             "detail": f"${mf['withdrawals']:,.0f} withdrawn from the pair",
             "hit": mf['withdrawals'] > 0},
        ]
        score, fired = score_signals(signals)
        if score < FLAG_THRESHOLD or fired < 2:
            continue
        conf = int(min(99, 60 + score*0.35))
        headline = (f"#{lose_l} systematically fed ~${amt:,.0f} to linked #{win_l} "
                    f"through {c} matched opposite trades")
        ev_obj = {"headline": headline, "at_risk": amt, "signals": signals,
                  "kpis": [{"label": "Transferred", "value": f"${amt:,.0f}"},
                           {"label": "Paired trades", "value": str(c)},
                           {"label": "Accounts", "value": "2"},
                           {"label": "Withdrawn", "value": f"${mf['withdrawals']:,.0f}"}],
                  "proof_pairs": proof, "money_flow": mf,
                  "links": [{"a": a, "b": b, "reason": r, "value": v} for a, b, r, v in cl["links"][:20]],
                  "accounts": accounts_summary(db, [lose_l, win_l])}
        text_ev = (f"CHIP DUMP — {headline} ({link_label}).")
        if save_case(db, 'chip_dump', [win_l, lose_l], None, score, conf, net_score,
                     text_ev, ev_obj, mf['deposits'], amt):
            n += 1
    db.commit()
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 3. BONUS CASH-OUT — bonus + barely traded + withdrew >= deposits
# ══════════════════════════════════════════════════════════════════════════════
def detect_bonus_cashout(db):
    n = 0
    rows = db.execute(text("""
        WITH t AS (
            SELECT login,
                   SUM(amount) FILTER (WHERE tx_type='deposit')         AS dep,
                   SUM(amount) FILTER (WHERE tx_type='withdrawal')       AS wd,
                   SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus_dep%') AS bonus
            FROM transactions GROUP BY login
        )
        SELECT login, COALESCE(dep,0), COALESCE(wd,0), COALESCE(bonus,0)
        FROM t
        WHERE COALESCE(bonus,0) > 0 AND COALESCE(dep,0) >= 30
          AND COALESCE(wd,0) >= COALESCE(dep,0) * 1.2     -- withdrew clearly MORE than deposited
        ORDER BY (COALESCE(wd,0)/NULLIF(COALESCE(dep,0),0)) DESC
        LIMIT 1500
    """)).fetchall()
    for login, dep, wd, bonus in rows:
        dep = float(dep); wd = float(wd); bonus = float(bonus)
        eer = wd / (dep + 1e-9)
        trades = int(db.execute(text(
            "SELECT count(*) FROM deals WHERE login=:l AND direction IN ('buy','sell')"),
            {"l": login}).scalar() or 0)
        # NOISE GATE: "took a bonus + withdrew more than deposited" alone is just a
        # winning client and floods the desk (~350 thin cases). A bonus cash-out is
        # only worth a case when there's a real tell on top: a GRAB & GO (barely
        # traded) OR HEAVY extraction (withdrew >=2x deposit). Require one — this drops
        # every base-only/medium row and keeps the convincing high/critical ones.
        if trades > 15 and eer < 2.0:
            continue
        # base = took bonus + withdrew the profit (both always true given the filter) = medium.
        # Only a bonus GRAB (barely traded) or heavy extraction escalates to high/critical.
        signals = [
            {"icon": "🎁", "label": "Took bonus", "weight": 22,
             "detail": f"${bonus:,.0f} bonus on ${dep:,.0f} deposit", "hit": bonus > 0},
            {"icon": "📤", "label": "Withdrew the profit", "weight": 30,
             "detail": f"withdrew ${wd:,.0f} ({eer*100:.0f}% of deposits)", "hit": eer >= 1.2},
            {"icon": "🚪", "label": "Barely traded (grab & go)", "weight": 28,
             "detail": f"only {trades} trades — took the bonus and left", "hit": trades <= 15},
            {"icon": "📈", "label": "Heavy extraction", "weight": 20,
             "detail": f"withdrew {eer*100:.0f}% of what they put in", "hit": eer >= 2.0},
        ]
        score, fired = score_signals(signals)
        if score < FLAG_THRESHOLD or fired < 2:
            continue
        conf = int(min(95, 55 + (eer-1)*30 + (15 if trades <= 15 else 0)))
        mf = {"deposits": dep, "bonus": bonus, "withdrawals": wd, "net_to_client": round(wd-dep, 2)}
        headline = f"#{login} took ${bonus:,.0f} bonus, made {trades} trades, withdrew ${wd:,.0f}"
        ev_obj = {"headline": headline, "at_risk": wd-dep, "signals": signals,
                  "kpis": [{"label": "Withdrew", "value": f"{eer*100:.0f}%"},
                           {"label": "Bonus", "value": f"${bonus:,.0f}"},
                           {"label": "Deposited", "value": f"${dep:,.0f}"},
                           {"label": "Trades", "value": str(trades)}],
                  "proof_pairs": [], "money_flow": mf, "links": [],
                  "accounts": accounts_summary(db, [login])}
        text_ev = f"BONUS CASH-OUT — {headline} ({eer*100:.0f}% of deposits)."
        if save_case(db, 'bonus_cashout', [login], None, score, conf, 0,
                     text_ev, ev_obj, dep, wd):
            n += 1
    db.commit()
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 4. SWAP CARRY — swap-free account farming overnight carry
# ══════════════════════════════════════════════════════════════════════════════
def detect_swap_carry(db):
    n = 0
    cand = db.execute(text(f"""
        WITH sf AS (
            SELECT login FROM clients WHERE {_swapfree_sql('group_name')}
            UNION SELECT login FROM trading_accounts WHERE is_islamic=true
        )
        SELECT d.login FROM deals d JOIN sf ON sf.login=d.login
        WHERE d.direction IN ('buy','sell')
        GROUP BY d.login HAVING count(*) BETWEEN 2 AND 400
    """)).fetchall()
    for (login,) in cand:
        deals = db.execute(text("""
            SELECT symbol, entry, direction, volume, profit, deal_time
            FROM deals WHERE login=:l AND direction IN ('buy','sell')
            ORDER BY symbol, deal_time
        """), {"l": login}).fetchall()
        by_sym = defaultdict(list)
        for sym, entry, d, v, p, t in deals:
            by_sym[sym].append((entry, d, v, p, t))
        total = 0; overnight = 0; nights = set(); per_sym = defaultdict(int); proof = []
        for sym, stream in by_sym.items():
            for o_t, c_t, vol, hold_s, is_on in fifo_holds(stream):
                total += 1
                if is_on and hold_s >= 4*3600:
                    overnight += 1; nights.add(c_t//86400); per_sym[sym] += 1
                    if len(proof) < 20:
                        proof.append({"login": login, "sym": sym, "dir": "hold",
                                      "vol": round(vol/100, 2), "profit": round(hold_s/3600, 1),
                                      "t": int(o_t)})
        if overnight < 8 or len(nights) < 4:
            continue
        ratio = overnight/total
        top_sym = max(per_sym, key=per_sym.get)
        pnl = float(db.execute(text(
            "SELECT COALESCE(SUM(profit),0) FROM deals WHERE login=:l AND entry=1"),
            {"l": login}).scalar() or 0)
        # carry farming only pays if the held positions are PROFITABLE — a swap-free
        # account holding overnight at a loss is just a losing holder, not an abuser.
        if pnl <= 0:
            continue
        signals = [
            {"icon": "🌙", "label": "Held overnight", "weight": 34,
             "detail": f"{overnight} positions across {len(nights)} nights (≥4h, crossed rollover)",
             "hit": overnight >= 8},
            {"icon": "💱", "label": "Swap-free account", "weight": 26,
             "detail": "Islamic group — pays no swap here", "hit": True},
            {"icon": "🎯", "label": "Carry concentration", "weight": 22,
             "detail": f"{ratio*100:.0f}% of closes held overnight, mostly {top_sym}", "hit": ratio >= 0.4},
            {"icon": "📈", "label": "Profitable carry", "weight": 18,
             "detail": f"net P&L ${pnl:,.0f}", "hit": pnl > 0},
        ]
        score, fired = score_signals(signals)
        if score < FLAG_THRESHOLD or fired < 2:
            continue
        conf = int(min(95, 50 + score*0.4))
        headline = (f"Swap-free #{login} held {top_sym} overnight {overnight}× across "
                    f"{len(nights)} nights")
        ev_obj = {"headline": headline, "at_risk": max(0.0, pnl), "signals": signals,
                  "kpis": [{"label": "Overnight", "value": f"{overnight}×"},
                           {"label": "Nights", "value": str(len(nights))},
                           {"label": "Held o/n", "value": f"{ratio*100:.0f}%"},
                           {"label": "P&L", "value": f"${pnl:,.0f}"}],
                  "proof_trades": proof, "money_flow": money_flow(db, [login]), "links": [],
                  "accounts": accounts_summary(db, [login])}
        text_ev = f"SWAP CARRY — {headline}; net P&L ${pnl:,.0f}."
        if save_case(db, 'swap_carry', [login], top_sym, score, conf, 0,
                     text_ev, ev_obj, money_flow(db, [login])['deposits'], max(0.0, pnl)):
            n += 1
    db.commit()
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 5. TOXIC ARB — near-perfect win-rate on ultra-short holds (feed-lag)
# ══════════════════════════════════════════════════════════════════════════════
def detect_toxic_arb(db):
    n = 0
    cand = db.execute(text("""
        SELECT login, count(*) trades,
               avg(CASE WHEN profit>0 THEN 1.0 ELSE 0 END) win_rate,
               sum(profit) pnl
        FROM deals WHERE entry=1 AND direction IN ('buy','sell')
        GROUP BY login
        HAVING count(*) >= 50
           AND avg(CASE WHEN profit>0 THEN 1.0 ELSE 0 END) >= 0.90
           AND sum(profit) > 0
        ORDER BY win_rate DESC
    """)).fetchall()
    for login, trades, win_rate, pnl in cand:
        win_rate = float(win_rate); pnl = float(pnl)
        stream = db.execute(text("""
            SELECT symbol, entry, direction, volume, profit, deal_time
            FROM deals WHERE login=:l AND direction IN ('buy','sell')
            ORDER BY symbol, deal_time
        """), {"l": login}).fetchall()
        by_sym = defaultdict(list); pnl_by_sym = defaultdict(float)
        for sym, entry, d, v, p, t in stream:
            by_sym[sym].append((entry, d, v, p, t))
            if entry == 1: pnl_by_sym[sym] += (p or 0)
        holds = []
        for sym, s in by_sym.items():
            holds += [h[3] for h in fifo_holds(s)]
        if not holds:
            continue
        avg_hold = sum(holds)/len(holds)
        short = sum(1 for h in holds if h <= 300)/len(holds)
        if avg_hold > 900:        # >15 min avg -> not feed-lag arb
            continue
        # night flavour
        night_frac = float(db.execute(text("""
            SELECT avg(CASE WHEN EXTRACT(HOUR FROM to_timestamp(deal_time))::int >= 21
                              OR EXTRACT(HOUR FROM to_timestamp(deal_time))::int < 1 THEN 1.0 ELSE 0 END)
            FROM deals WHERE login=:l AND entry=1 AND direction IN ('buy','sell')
        """), {"l": login}).scalar() or 0)
        top_sym = max(pnl_by_sym, key=pnl_by_sym.get) if pnl_by_sym else None
        proof = [{"login": login, "sym": r[0], "dir": r[1], "vol": round((r[2] or 0)/100, 2),
                  "profit": round(r[3] or 0, 2), "t": int(r[4])}
                 for r in db.execute(text("""
                     SELECT symbol, direction, volume, profit, deal_time FROM deals
                     WHERE login=:l AND entry=1 AND direction IN ('buy','sell')
                     ORDER BY profit DESC LIMIT 20"""), {"l": login}).fetchall()]
        signals = [
            {"icon": "🎯", "label": "Near-perfect win-rate", "weight": 34,
             "detail": f"{win_rate*100:.0f}% wins over {trades} closed trades", "hit": win_rate >= 0.90},
            {"icon": "⚡", "label": "Ultra-short holds", "weight": 30,
             "detail": f"avg {avg_hold/60:.1f} min · {short*100:.0f}% under 5 min", "hit": short >= 0.5},
            {"icon": "💰", "label": "Consistently profitable", "weight": 20,
             "detail": f"net ${pnl:,.0f}, mostly {top_sym}", "hit": pnl > 0},
            {"icon": "🌙", "label": "Rollover window", "weight": 16,
             "detail": f"{night_frac*100:.0f}% of trades in 21:00-01:00 UTC", "hit": night_frac >= 0.4},
        ]
        score, fired = score_signals(signals)
        if score < FLAG_THRESHOLD or fired < 2:
            continue
        conf = int(min(98, 60 + score*0.35))
        headline = (f"#{login}: {win_rate*100:.0f}% win-rate over {trades} trades, "
                    f"avg hold {avg_hold/60:.1f} min")
        ev_obj = {"headline": headline, "at_risk": pnl, "signals": signals,
                  "kpis": [{"label": "Win-rate", "value": f"{win_rate*100:.0f}%"},
                           {"label": "Avg hold", "value": f"{avg_hold/60:.1f}m"},
                           {"label": "Trades", "value": str(trades)},
                           {"label": "P&L", "value": f"${pnl:,.0f}"}],
                  "proof_trades": proof, "money_flow": money_flow(db, [login]), "links": [],
                  "accounts": accounts_summary(db, [login])}
        text_ev = f"TOXIC ARB — {headline}; net ${pnl:,.0f} (feed-lag arbitrage)."
        if save_case(db, 'toxic_arb', [login], top_sym, score, conf, 0,
                     text_ev, ev_obj, money_flow(db, [login])['deposits'], pnl):
            n += 1
    db.commit()
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 6. MARGIN-OUT PARTNER (🔥 HOT) — a trader blows up; a partner wins ~the same
#    amount on the same symbol, opposite side, in the same ±2 min. Bonus/credit
#    funded the loss while the partner's win is real, withdrawable money.
# ══════════════════════════════════════════════════════════════════════════════
def detect_margin_partner(db):
    n = 0
    WIN_LO, WIN_HI = 0.8, 1.25   # partner's win within 80% range of the loser's loss (a true mirror)
    VOL_TOL = 0.45               # partner volume within 45% of loser's (mirror position)
    # blow-up windows: a credit/bonus account loses big in a 5-min window
    events = db.execute(text("""
        WITH cr AS (
            SELECT DISTINCT login FROM trading_accounts WHERE credit > 0
            UNION SELECT DISTINCT login FROM transactions WHERE tx_type ILIKE 'bonus%'
        )
        SELECT d.login, SUM(d.profit) AS loss, SUM(d.volume) AS vol,
               MIN(d.deal_time) AS t0, MAX(d.deal_time) AS t1,
               (array_agg(d.symbol     ORDER BY d.volume DESC))[1] AS sym,
               (array_agg(d.direction  ORDER BY d.volume DESC))[1] AS dir
        FROM deals d JOIN cr ON cr.login = d.login
        WHERE d.entry = 1 AND d.direction IN ('buy','sell') AND d.profit < 0
        GROUP BY d.login, (d.deal_time/300)*300
        HAVING SUM(d.profit) <= -300 AND COUNT(*) >= 2
    """)).fetchall()

    # aggregate by (loser -> winner) so repeat offenders surface as one strong case
    pairs = defaultdict(lambda: {"events": 0, "loss": 0.0, "win": 0.0, "syms": set(),
                                 "legs": [], "vol_ok": 0})
    for loser, loss, vol, t0, t1, sym, dr in events:
        loss = abs(float(loss)); vol = float(vol or 0)
        if not sym or vol <= 0:
            continue
        opp = 'sell' if dr == 'buy' else 'buy'
        winner = db.execute(text("""
            SELECT login, SUM(profit) p, SUM(volume) v, COUNT(*) c,
                   MIN(deal_time) wt0, MAX(deal_time) wt1
            FROM deals
            WHERE entry=1 AND symbol=:s AND login<>:l AND direction=:opp
              AND deal_time BETWEEN :a AND :b AND profit > 0
            GROUP BY login
            HAVING SUM(profit) BETWEEN :lo AND :hi
            ORDER BY ABS(SUM(profit) - :loss) ASC LIMIT 1
        """), {"s": sym, "l": loser, "opp": opp, "a": t0-120, "b": t1+120,
               "lo": WIN_LO*loss, "hi": WIN_HI*loss, "loss": loss}).fetchone()
        if not winner:
            continue
        w_login, w_p, w_v, w_c = winner[0], float(winner[1]), float(winner[2] or 0), winner[3]
        w_t0, w_t1 = int(winner[4]), int(winner[5])
        vol_ok = max(vol, w_v) > 0 and abs(vol - w_v)/max(vol, w_v) <= VOL_TOL
        key = (loser, w_login)
        p = pairs[key]
        p["events"] += 1; p["loss"] += loss; p["win"] += w_p; p["syms"].add(sym)
        if vol_ok: p["vol_ok"] += 1
        if len(p["legs"]) < 20:
            # ticket #76/#99: a margin-out "leg" is a 5-min blow-up WINDOW, not a single
            # position, so per-leg hold = the window span (close-time minus first
            # close-time). close_gap_s = how far apart the two accounts' margin-out
            # windows are (0 if they overlap, else nearest-edge distance in seconds).
            # deal_time is a bigint epoch. No reliable per-position open here (winner is
            # a SUM over the window), so a_open/b_open stay absent.
            if w_t1 < t0:
                close_gap = int(t0 - w_t1)
            elif w_t0 > t1:
                close_gap = int(w_t0 - t1)
            else:
                close_gap = 0
            p["legs"].append({"sym": sym, "a_login": w_login, "a_dir": opp,
                              "a_vol": round(w_v/100, 2), "a_profit": round(w_p, 2),
                              "a_close": w_t1, "a_hold": int(w_t1 - w_t0),
                              "b_login": loser, "b_dir": dr, "b_vol": round(vol/100, 2),
                              "b_profit": round(-loss, 2),
                              "b_close": int(t1), "b_hold": int(t1 - t0),
                              "close_gap_s": close_gap,
                              "t": int(t0), "gap_s": int(t1-t0)})

    for (loser, winner), p in pairs.items():
        # require either a volume-matched mirror OR a repeat pattern (kills gold-noise coincidences)
        if p["vol_ok"] == 0 and p["events"] < 2:
            continue
        reasons = [r[1] for r in db.execute(text("""
            SELECT DISTINCT 1, identifier_type FROM account_identifiers x
            WHERE x.login=:a AND x.identifier_type IN ('cid','mqid')
              AND EXISTS (SELECT 1 FROM account_identifiers y WHERE y.login=:b
                          AND y.identifier_type=x.identifier_type
                          AND y.identifier_value=x.identifier_value
                          AND y.identifier_value NOT IN ('0',''))
        """), {"a": loser, "b": winner}).fetchall()]
        linked = bool(reasons)
        mf = money_flow(db, [winner, loser])
        broker_loss = min(p["loss"], (mf["bonus"] or p["loss"]))  # credit/bonus that funded the loss
        win_ratio = p["win"] / (p["loss"] + 1e-9)
        signals = [
            {"icon": "🔥", "label": "Win mirrors a blow-up", "weight": 34,
             "detail": f"#{winner} won ${p['win']:,.0f} as #{loser} lost ${p['loss']:,.0f} "
                       f"({win_ratio*100:.0f}%) — opposite side, same ±2 min", "hit": True},
            {"icon": "📐", "label": "Volume-matched mirror", "weight": 24,
             "detail": f"matched lot size on {p['vol_ok']}/{p['events']} events", "hit": p["vol_ok"] > 0},
            {"icon": "🔁", "label": "Repeat pattern", "weight": 22,
             "detail": f"{p['events']} margin-out transfers between this pair", "hit": p["events"] >= 2},
            {"icon": "🎁", "label": "Bonus/credit funded the loss", "weight": 16,
             "detail": f"loser held ${mf['bonus']:,.0f} bonus — broker eats it", "hit": mf["bonus"] > 0},
            {"icon": "🔗", "label": "Linked accounts", "weight": 12,
             "detail": "shared device" if linked else "no device link (possible cross-broker)",
             "hit": linked},
        ]
        score, fired = score_signals(signals)
        if score < FLAG_THRESHOLD or fired < 2:
            continue
        conf = int(min(98, 55 + score*0.4))
        net = 90 if linked else 40
        top_sym = sorted(p["syms"])[0] if p["syms"] else None
        headline = (f"#{winner} won ${p['win']:,.0f} the moment #{loser} margined out "
                    f"${p['loss']:,.0f} on {top_sym} — opposite-side mirror, {p['events']}×")
        ev_obj = {"headline": headline, "at_risk": broker_loss, "broker_loss": broker_loss,
                  "signals": signals,
                  "kpis": [{"label": "Match", "value": f"{win_ratio*100:.0f}%"},
                           {"label": "Loss", "value": f"${p['loss']:,.0f}"},
                           {"label": "Repeats", "value": f"{p['events']}×"},
                           {"label": "Broker loss", "value": f"${broker_loss:,.0f}"}],
                  "proof_pairs": p["legs"], "money_flow": mf,
                  "links": ([{"a": loser, "b": winner, "reason": "device", "value": ""}] if linked else []),
                  "accounts": accounts_summary(db, [winner, loser])}
        text_ev = (f"MARGIN-OUT PARTNER (HOT) — {headline}. Win {win_ratio*100:.0f}% of loss, "
                   f"vol-matched {p['vol_ok']}/{p['events']}.")
        if save_case(db, 'margin_partner', [winner, loser], top_sym, score, conf, net,
                     text_ev, ev_obj, mf['deposits'], broker_loss, hot=True):
            n += 1
    db.commit()
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 8. MATCHED PAIR (ticket #51 — desk weighted-signal scoring table)
#    Two DIFFERENT accounts run opposing legs that look like a coordinated match.
#    The desk handed over an EXACT signal/weight table; this detector implements it
#    verbatim and flags a (account_a, account_b, symbol) pair when the summed score
#    crosses the threshold. Signals (max 145):
#      same symbol .............. 20   shared CID/device ........ 20
#      opposite direction ....... 20   shared IP ................ 10
#      open-time match .......... 15   bonus >= 30% ............. 10
#      close-time match ......... 15   similar total exposure ... 15
#      same volume .............. 20
# ══════════════════════════════════════════════════════════════════════════════
MATCHED_PAIR_THRESHOLD = 60          # flag a pair at >=60 with >=3 signals fired
MP_TIME_TOL   = 120                  # seconds: open/close "match" window
MP_VOL_TOL    = 0.15                 # within 15% => "same volume"
MP_EXPO_TOL   = 0.20                 # within 20% => "similar total exposure"
MP_BONUS_FRAC = 0.30                 # bonus >= 30% of deposits => signal fires
MP_LEG_CAP    = 300                  # max opposing legs/side per symbol (bounds the O(n²) scan)

# the 9 weighted signals, EXACTLY as the desk specified (label + weight)
# Ticket #51: these are EXACTLY the desk's attached factor table (sum = 130), not tuned weights.
# Do not "improve" them — same_volume=15 and shared_cid=10 per the desk's sheet.
MP_WEIGHTS = {
    "same_symbol":   20,   # نفس الزوج
    "opposite_dir":  20,   # اتجاه معاكس
    "open_match":    15,   # تطابق وقت الفتح
    "close_match":   15,   # تطابق وقت الإغلاق
    "same_volume":   15,   # نفس الحجم
    "shared_cid":    10,   # مشترك CID / device
    "shared_ip":     10,   # مشترك IP
    "bonus_30":      10,   # Bonus +30%
    "similar_expo":  15,   # متشابه Total Exposure
}
MP_MAX_SCORE = sum(MP_WEIGHTS.values())   # 130 — the desk's max


def _shared_identifiers(db, login_a, login_b):
    """Return (shared_cid_or_device, shared_ip) booleans for two logins from
    account_identifiers. CID covers cid OR mqid (both are device fingerprints)."""
    rows = db.execute(text("""
        SELECT x.identifier_type
        FROM account_identifiers x
        JOIN account_identifiers y
          ON y.identifier_type = x.identifier_type
         AND y.identifier_value = x.identifier_value
        WHERE x.login = :a AND y.login = :b
          AND x.identifier_type IN ('cid','mqid','ip')
          AND x.identifier_value NOT IN ('0','')
        GROUP BY x.identifier_type
    """), {"a": login_a, "b": login_b}).fetchall()
    types = {r[0] for r in rows}
    return (('cid' in types or 'mqid' in types), ('ip' in types))


def detect_matched_pair(db, clusters):
    """Implements the desk's weighted-signal scoring table (ticket #51). Works over
    the same device/IP/phone clusters the rest of the engine builds, so candidate
    account pairs are already plausibly linked. For each opposing opening-trade pair
    between two DIFFERENT accounts on the same symbol it evaluates the 9 signals,
    sums their weights, and flags the (a,b,symbol) pair at >= threshold."""
    n = 0
    # memoize shared-identifier lookups: the same (a,b) pair recurs across many
    # symbols/legs, and _shared_identifiers hits the DB. Without this cache the call
    # fires inside the O(buys×sells) inner loop and the detector hangs on dense
    # clusters (~3.5k clusters). Cache key is the normalized (a<b) pair.
    sh_cache = {}
    # account-level credit/bonus (for the Bonus >=30% signal) — load once per cluster
    for cl in clusters:
        members = sorted(cl["members"])
        tradeable = cluster_tradeable(db, members, cap=4000)
        if len(tradeable) < 2:
            continue
        # opening legs (entry=0) with their FIFO-paired close time so we can score
        # both open-time AND close-time matching.
        rows = db.execute(text("""
            SELECT login, symbol, entry, direction, volume, deal_time
            FROM deals
            WHERE login=ANY(:l) AND entry IN (0,1) AND direction IN ('buy','sell')
            ORDER BY login, symbol, deal_time LIMIT 60000
        """), {"l": tradeable}).fetchall()
        # per (login,symbol) FIFO-pair opens->closes to get (open_t, close_t, vol, dir)
        positions = defaultdict(list)   # (login,symbol) -> list of dicts
        streams = defaultdict(list)
        for lg, s, entry, d, v, t in rows:
            streams[(lg, s)].append((entry, d, v or 0.0, t))
        for (lg, s), stream in streams.items():
            opens = deque()
            for entry, d, v, t in stream:
                if entry == 0:
                    opens.append({"dir": d, "vol": v, "open_t": t, "close_t": None})
                    positions[(lg, s)].append(opens[-1])
                elif entry == 1 and opens:
                    pos = opens.popleft()
                    if pos["close_t"] is None:
                        pos["close_t"] = t

        # index opening positions per symbol for cross-account matching
        by_sym = defaultdict(list)
        for (lg, s), poss in positions.items():
            for pos in poss:
                by_sym[s].append((lg, pos))

        # money / bonus per member (for the Bonus >=30% signal) — single query
        bonus_rows = db.execute(text("""
            SELECT c.login,
                   COALESCE((SELECT SUM(amount) FROM transactions t
                             WHERE t.login=c.login AND t.tx_type='deposit'),0) AS dep,
                   COALESCE(ta.credit,0) AS credit,
                   COALESCE((SELECT SUM(amount) FROM transactions t
                             WHERE t.login=c.login AND t.tx_type ILIKE 'bonus%'),0) AS bonus
            FROM clients c LEFT JOIN trading_accounts ta ON ta.login=c.login
            WHERE c.login=ANY(:l)
        """), {"l": tradeable}).fetchall()
        bonus_by = {}
        for lg, dep, credit, bns in bonus_rows:
            bonus_by[int(lg)] = {"dep": float(dep), "bonus": max(float(credit), float(bns))}

        # exposure per login = total opened volume (lots) on this symbol set
        expo_by = defaultdict(float)
        for (lg, s), poss in positions.items():
            for pos in poss:
                expo_by[lg] += pos["vol"]

        # evaluate candidate opposing pairs, aggregate the BEST pair per (a,b,symbol)
        best = {}   # (a,b,sym) -> dict(score, signals, legs, n_pairs)
        for sym, legs in by_sym.items():
            buys  = [(lg, p) for lg, p in legs if p["dir"] == "buy"]
            sells = [(lg, p) for lg, p in legs if p["dir"] == "sell"]
            # Bound the O(buys×sells) scan. A genuine matched-pair scheme is a few
            # linked accounts deliberately opening opposite legs — not a high-frequency
            # market (gold/EURUSD) with thousands of opposing legs per cluster, which
            # would hang the detector. Cap each side; legs are time-ordered so the
            # earliest (and any tightly-timed collusion) are kept.
            if len(buys) > MP_LEG_CAP or len(sells) > MP_LEG_CAP:
                buys = buys[:MP_LEG_CAP]
                sells = sells[:MP_LEG_CAP]
            for blg, bp in buys:
                for slg, sp in sells:
                    if blg == slg:
                        continue
                    a, b = (blg, slg) if blg < slg else (slg, blg)
                    pa, pb = (bp, sp) if blg < slg else (sp, bp)
                    # --- evaluate the 9 signals for this opposing pair ---
                    fired = {}
                    fired["same_symbol"]  = True            # same `sym` by construction
                    fired["opposite_dir"] = True            # buy vs sell by construction
                    fired["open_match"]   = abs(pa["open_t"] - pb["open_t"]) <= MP_TIME_TOL
                    fired["close_match"]  = (pa["close_t"] is not None and pb["close_t"] is not None
                                             and abs(pa["close_t"] - pb["close_t"]) <= MP_TIME_TOL)
                    va, vb = pa["vol"], pb["vol"]
                    fired["same_volume"]  = max(va, vb) > 0 and abs(va - vb)/max(va, vb) <= MP_VOL_TOL
                    sh = sh_cache.get((a, b))
                    if sh is None:
                        sh = _shared_identifiers(db, a, b)
                        sh_cache[(a, b)] = sh
                    cid_sh, ip_sh = sh
                    fired["shared_cid"]   = cid_sh
                    fired["shared_ip"]    = ip_sh
                    bx = bonus_by.get(a, {}); by_ = bonus_by.get(b, {})
                    bonus30 = (((bx.get("bonus", 0) >= MP_BONUS_FRAC * max(bx.get("dep", 0), 1e-9))
                                and bx.get("bonus", 0) > 0)
                               or ((by_.get("bonus", 0) >= MP_BONUS_FRAC * max(by_.get("dep", 0), 1e-9))
                                   and by_.get("bonus", 0) > 0))
                    fired["bonus_30"]     = bool(bonus30)
                    ea, eb = expo_by.get(a, 0.0), expo_by.get(b, 0.0)
                    fired["similar_expo"] = max(ea, eb) > 0 and abs(ea - eb)/max(ea, eb) <= MP_EXPO_TOL
                    score = sum(MP_WEIGHTS[k] for k, hit in fired.items() if hit)
                    nfired = sum(1 for hit in fired.values() if hit)
                    key = (a, b, sym)
                    prev = best.get(key)
                    if prev is None or score > prev["score"]:
                        # ticket #76/#99: per-leg open→close hold (s) + cross-account
                        # open-gap / close-gap (s) between the two accounts. deal_time is
                        # a bigint epoch, so these are plain second differences.
                        a_hold = (int(bp["close_t"] - bp["open_t"]) if bp["close_t"] else None)
                        b_hold = (int(sp["close_t"] - sp["open_t"]) if sp["close_t"] else None)
                        close_gap = (int(abs(bp["close_t"] - sp["close_t"]))
                                     if (bp["close_t"] and sp["close_t"]) else None)
                        leg = {"sym": sym,
                               "a_login": blg, "a_dir": "buy",  "a_vol": round(bp["vol"]/100, 2),
                               "a_open": int(bp["open_t"]),
                               "a_close": int(bp["close_t"]) if bp["close_t"] else None,
                               "a_hold": a_hold,
                               "b_login": slg, "b_dir": "sell", "b_vol": round(sp["vol"]/100, 2),
                               "b_open": int(sp["open_t"]),
                               "b_close": int(sp["close_t"]) if sp["close_t"] else None,
                               "b_hold": b_hold,
                               "open_gap_s": int(abs(bp["open_t"] - sp["open_t"])),
                               "close_gap_s": close_gap,
                               "t": int(min(bp["open_t"], sp["open_t"])),
                               "gap_s": int(abs(bp["open_t"] - sp["open_t"]))}
                        best[key] = {"score": score, "fired": fired, "leg": leg,
                                     "cid": cid_sh, "ip": ip_sh, "n_pairs": 1}
                    elif prev is not None:
                        prev["n_pairs"] += 1

        reasons = {r[2] for r in cl["links"]}
        net_score, link_label = _link_strength(reasons)
        for (a, b, sym), info in best.items():
            fired = info["fired"]
            if info["score"] < MATCHED_PAIR_THRESHOLD:
                continue
            nfired = sum(1 for v in fired.values() if v)
            if nfired < 3:
                continue
            # build the structured signals[] in the desk's exact order/labels
            SIG_META = [
                ("same_symbol",  "🎯", "Same symbol (نفس الزوج)"),
                ("opposite_dir", "↔️", "Opposite direction (اتجاه معاكس)"),
                ("open_match",   "🕐", "Open-time match (تطابق وقت الفتح)"),
                ("close_match",  "🕓", "Close-time match (تطابق وقت الإغلاق)"),
                ("same_volume",  "⚖️", "Same volume (نفس الحجم)"),
                ("shared_cid",   "🖥️", "Shared CID / device (مشترك CID)"),
                ("shared_ip",    "🌐", "Shared IP (مشترك IP)"),
                ("bonus_30",     "🎁", "Bonus ≥ 30% (Bonus +30%)"),
                ("similar_expo", "📊", "Similar Total Exposure (متشابه Total Exposure)"),
            ]
            leg = info["leg"]
            ea = expo_by.get(a, 0.0) / 100.0
            eb = expo_by.get(b, 0.0) / 100.0
            details = {
                "same_symbol":  f"both legs on {sym}",
                "opposite_dir": f"#{leg['a_login']} {leg['a_dir']} vs #{leg['b_login']} {leg['b_dir']}",
                "open_match":   (f"opens {leg['gap_s']}s apart" if fired["open_match"]
                                 else "opens not aligned"),
                "close_match":  ("closes within 2 min" if fired["close_match"]
                                 else "closes not aligned"),
                "same_volume":  (f"{leg['a_vol']} vs {leg['b_vol']} lots" ),
                "shared_cid":   ("same device fingerprint (CID/MQID)" if fired["shared_cid"]
                                 else "no shared device"),
                "shared_ip":    ("same IP address" if fired["shared_ip"] else "no shared IP"),
                "bonus_30":     ("a leg holds bonus ≥30% of its deposit" if fired["bonus_30"]
                                 else "no significant bonus"),
                "similar_expo": (f"{ea:,.1f} vs {eb:,.1f} lots total exposure"),
            }
            signals = [{"icon": ic, "label": lbl, "weight": MP_WEIGHTS[k],
                        "detail": details[k], "hit": bool(fired[k])}
                       for k, ic, lbl in SIG_META]
            score = info["score"]
            # severity bands on the desk's 130-max scale (ticket #51)
            sev_score = (100 if score >= 100 else 75 if score >= 85
                         else 60 if score >= 70 else 50)
            conf = int(min(98, 40 + score * 0.5))
            mf = money_flow(db, [a, b])
            headline = (f"#{a} and #{b} ran a matched opposite pair on {sym} "
                        f"(scoring {score}/{MP_MAX_SCORE} across {nfired} signals)")
            ev_obj = {"headline": headline, "at_risk": mf.get("bonus", 0),
                      "match_score": score, "max_score": MP_MAX_SCORE,
                      "signals": signals,
                      "kpis": [{"label": "Match score", "value": f"{score}/{MP_MAX_SCORE}"},
                               {"label": "Signals", "value": f"{nfired}/9"},
                               {"label": "Symbol", "value": sym},
                               {"label": "Shared device", "value": "yes" if info["cid"] else
                                ("IP only" if info["ip"] else "no")}],
                      "proof_pairs": [leg], "money_flow": mf,
                      "links": [{"a": la, "b": lb, "reason": r, "value": v}
                                for la, lb, r, v in cl["links"][:20]],
                      "accounts": accounts_summary(db, [a, b])}
            text_ev = (f"MATCHED PAIR — {headline}. Signals: "
                       + ", ".join(s["label"] for s in signals if s["hit"]) + ".")
            if save_case(db, 'matched_pair', [a, b], sym, sev_score, conf, net_score,
                         text_ev, ev_obj, mf['deposits'], mf.get("bonus", 0)):
                n += 1
        db.commit()
    return n


def build_account_flags(db):
    """Flatten open cases into a per-account flag table so the rest of the CRM
    (Transactions / Clients / IB) can show an abuse badge by login in one cheap
    join. Each login keeps its WORST case (severity, then exposure)."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS abuse_account_flags (
            login       BIGINT PRIMARY KEY,
            case_id     BIGINT,
            abuse_type  VARCHAR(64),
            severity    VARCHAR(16),
            hot         BOOLEAN DEFAULT FALSE,
            exposure    DOUBLE PRECISION DEFAULT 0,
            n_cases     INTEGER DEFAULT 1,
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    db.execute(text("DELETE FROM abuse_account_flags"))
    db.execute(text("""
        INSERT INTO abuse_account_flags (login, case_id, abuse_type, severity, hot, exposure, n_cases, updated_at)
        WITH exploded AS (
            SELECT trim(x)::bigint AS login, a.id AS case_id, a.abuse_type, a.severity,
                   COALESCE(a.hot,false) AS hot, COALESCE(a.exposure,0) AS exposure,
                   CASE a.severity WHEN 'critical' THEN 3 WHEN 'high' THEN 2 ELSE 1 END AS sevrank
            FROM abuse_cases a, unnest(string_to_array(a.all_logins, ',')) AS x
            WHERE a.status NOT IN ('resolved') AND trim(x) ~ '^[0-9]+$'
        ),
        ranked AS (
            SELECT login, case_id, abuse_type, severity, hot, exposure,
                   row_number() OVER (PARTITION BY login ORDER BY sevrank DESC, exposure DESC NULLS LAST) AS rn,
                   count(*)     OVER (PARTITION BY login) AS n
            FROM exploded
        )
        SELECT login, case_id, abuse_type, severity, hot, exposure, n, NOW()
        FROM ranked WHERE rn = 1
    """))
    db.commit()
    return db.execute(text("SELECT count(*) FROM abuse_account_flags")).scalar()


# ══════════════════════════════════════════════════════════════════════════════
# 7. HEDGE RATIO — any account where a meaningful share of trades are hedged
# ══════════════════════════════════════════════════════════════════════════════
def detect_hedge_ratio(db):
    """For EVERY trading account, what share of its opening trades are hedged — an
    opposite-direction open on the same symbol, similar volume, within 5 min (a
    self-hedge / locked position). Flag at >=25% and show the % and fraction (5/20).
    Uses a time-windowed sweep so it scales to all accounts."""
    n = 0
    HEDGE_WINDOW = 300
    VOL_TOL = 0.4
    accts = db.execute(text("""
        SELECT login, count(*) FROM deals
        WHERE entry=0 AND direction IN ('buy','sell')
        GROUP BY login HAVING count(*) BETWEEN 10 AND 2000
    """)).fetchall()
    for login, _tot in accts:
        # ticket #99: fetch opens AND closes so each hedged position can show its own
        # open->close hold (s) and the two legs' close-time gap — not just the open gap.
        rows = db.execute(text("""
            SELECT symbol, entry, direction, volume, deal_time FROM deals
            WHERE login=:l AND entry IN (0,1) AND direction IN ('buy','sell')
            ORDER BY symbol, deal_time
        """), {"l": login}).fetchall()
        # FIFO-pair opens->closes per symbol to assign each open its close_time
        by_sym = defaultdict(list)   # sym -> list of {dir,vol,open_t,close_t} (opens only)
        streams = defaultdict(list)
        for s, entry, d, v, t in rows:
            streams[s].append((entry, d, v or 0.0, t))
        for s, stream in streams.items():
            opendq = deque()
            for entry, d, v, t in stream:
                if entry == 0:
                    pos = {"dir": d, "vol": v, "open_t": t, "close_t": None}
                    opendq.append(pos); by_sym[s].append(pos)
                elif entry == 1 and opendq:
                    p = opendq.popleft()
                    if p["close_t"] is None:
                        p["close_t"] = t
        total_opens = sum(len(v) for v in by_sym.values())
        if total_opens < 10:
            continue

        hedged = 0; pairs = 0; per_sym = defaultdict(int); proof = []
        for sym, poss in by_sym.items():
            unmatched = {"buy": deque(), "sell": deque()}   # position dicts
            for pos in poss:
                d, v, t = pos["dir"], pos["vol"], pos["open_t"]
                opp = "sell" if d == "buy" else "buy"
                dq = unmatched[opp]
                while dq and t - dq[0]["open_t"] > HEDGE_WINDOW:
                    dq.popleft()
                hit = -1
                for k in range(len(dq)):
                    ov = dq[k]["vol"]
                    if max(v, ov) > 0 and abs(v - ov) / max(v, ov) <= VOL_TOL:
                        hit = k; break
                if hit >= 0:
                    op = dq[hit]; del dq[hit]
                    pairs += 1; hedged += 2; per_sym[sym] += 1
                    if len(proof) < 20:
                        bp = pos if d == "buy" else op     # the buy-leg position
                        sp = pos if d == "sell" else op    # the sell-leg position
                        a_hold = (int(bp["close_t"] - bp["open_t"]) if bp["close_t"] else None)
                        b_hold = (int(sp["close_t"] - sp["open_t"]) if sp["close_t"] else None)
                        close_gap = (int(abs(bp["close_t"] - sp["close_t"]))
                                     if (bp["close_t"] and sp["close_t"]) else None)
                        # ticket #76/#99: open-gap, per-leg open->close hold, and close-gap (s)
                        proof.append({"sym": sym, "a_login": login, "a_dir": "buy", "a_vol": round(bp["vol"]/100, 2),
                                      "b_login": login, "b_dir": "sell", "b_vol": round(sp["vol"]/100, 2),
                                      "a_open": int(bp["open_t"]), "a_close": int(bp["close_t"]) if bp["close_t"] else None,
                                      "a_hold": a_hold,
                                      "b_open": int(sp["open_t"]), "b_close": int(sp["close_t"]) if sp["close_t"] else None,
                                      "b_hold": b_hold,
                                      "open_gap_s": int(abs(bp["open_t"] - sp["open_t"])),
                                      "close_gap_s": close_gap,
                                      "t": int(min(bp["open_t"], sp["open_t"])),
                                      "gap_s": int(abs(bp["open_t"] - sp["open_t"]))})
                else:
                    unmatched[d].append(pos)

        if hedged < 4:
            continue
        ratio = hedged / total_opens
        if ratio < 0.25:
            continue
        top_sym = max(per_sym, key=per_sym.get) if per_sym else None
        score = min(100, 50 + (ratio - 0.25) * 120)   # 25%->50, 33%->60, 46%->75
        sev = severity_for(score)
        if not sev:
            continue
        conf = int(min(95, 55 + ratio * 40))
        mf = money_flow(db, [login])
        deposits = mf['deposits']
        signals = [
            {"icon": "🔁", "label": "Hedged trades", "weight": 50,
             "detail": f"{hedged}/{total_opens} opening trades are hedged ({ratio*100:.0f}%)", "hit": True},
            {"icon": "📊", "label": "Hedge pairs", "weight": 30,
             "detail": f"{pairs} opposite same-symbol pairs (≤5 min, matched volume)", "hit": pairs >= 2},
            {"icon": "🎯", "label": "Concentrated", "weight": 20,
             "detail": f"mostly {top_sym}", "hit": bool(top_sym)},
        ]
        headline = f"#{login} — {ratio*100:.0f}% of trades are hedged ({hedged}/{total_opens})"
        ev_obj = {"headline": headline, "at_risk": 0, "signals": signals,
                  "kpis": [{"label": "Hedged", "value": f"{ratio*100:.0f}%"},
                           {"label": "Trades", "value": f"{hedged}/{total_opens}"},
                           {"label": "Pairs", "value": str(pairs)},
                           {"label": "Symbol", "value": top_sym or "—"}],
                  "proof_pairs": proof, "money_flow": mf, "links": [],
                  "accounts": accounts_summary(db, [login])}
        text_ev = f"HEDGE RATIO — {headline} on {top_sym}."
        if save_case(db, 'hedge_ratio', [login], top_sym, score, conf, 0, text_ev, ev_obj, deposits, 0):
            n += 1
    db.commit()
    return n


# ── orchestrator ────────────────────────────────────────────────────────────────
def run_engine(db):
    # This is a long batch job that holds transactions through heavy Python-side work between
    # queries. The DB's protective 60s idle_in_transaction_session_timeout (added to stop the web
    # app's pool-poisoning hang) would intermittently abort us mid-run. Disable it for THIS session
    # only (the web app keeps the 60s default).
    try:
        db.execute(text("SET idle_in_transaction_session_timeout = 0"))
        db.commit()
    except Exception:
        db.rollback()
    ensure_schema(db)
    results = {}
    clusters = build_clusters(db)
    results["_clusters"] = len(clusters)
    for name, fn, needs_clusters in [
        ('bonus_ring',    detect_bonus_ring,   True),
        ('chip_dump',     detect_chip_dump,    True),
        ('bonus_cashout', detect_bonus_cashout, False),
        ('swap_carry',    detect_swap_carry,   False),
        ('toxic_arb',     detect_toxic_arb,    False),
        ('margin_partner', detect_margin_partner, False),
        ('hedge_ratio',   detect_hedge_ratio,  False),
        ('matched_pair',  detect_matched_pair, True),  # ticket #51 (re-enabled): the earlier
        # incomplete runs were the 60s idle-in-transaction timeout aborting the batch, now fixed by
        # the SET above — matched_pair runs fine and produces cases.
    ]:
        try:
            results[name] = fn(db, clusters) if needs_clusters else fn(db)
            db.commit()   # durably persist each detector's cases before the next one
                          # runs, so a slow/killed later detector never loses prior work
        except Exception as e:
            db.rollback(); results[name] = f"error: {str(e)[:180]}"
    try:
        results["_flagged_accounts"] = build_account_flags(db)
    except Exception as e:
        db.rollback(); results["_flagged_accounts"] = f"error: {str(e)[:120]}"
    return results
