"""
retention_engine.py — rule-based client retention/risk scoring (Ticket #77).

Evaluates the AUTOMATABLE subset of the 119-rule catalog (retention_rules) against
real data, per CLIENT. A "client" is aggregated by phone+platform exactly like the
Clients list / portal (_client_logins) so a person's multiple same-platform accounts
score as one. For each client we build a compact financial+trading profile from:
    transactions  -> deposits / withdrawals timing, amounts, bonus flows
    deals         -> trade activity, gaps, volume, profit
    account_identifiers -> device/IP fingerprints (rule 93)
    trading_accounts / clients -> balance, reg_date

Sum of fired risk_points = retention_score. Band:
    >=70 Critical, >=45 High, >=25 Medium, >=1 Low, <=0 Trusted.
Top action = the suggested_action of the highest-points POSITIVE rule fired.

Output -> retention_flags (one row per client cluster key). Idempotent: the table is
recreated empty each full run (it is a derived cache, like abuse_account_flags).

PERFORMANCE / BOUNDING (logged, not silent):
  * Only clients with at least one transaction OR deal in the last LOOKBACK_DAYS are
    scored (dormant-but-never-active rows are skipped). Pass --all to score every
    client with a login.
  * --limit N scores only the first N client clusters (used for quick test runs).
  * Heavy per-client trade/tx scans are replaced by ONE pre-aggregated pass over
    transactions and deals keyed by login, joined in Python. No per-client SQL loop.

CLI:
  python retention_engine.py                 # full build (active clients)
  python retention_engine.py --limit 300     # quick bounded test
  python retention_engine.py --all           # every client with a login
"""
import sys
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy import text
from database import SessionLocal

LOOKBACK_DAYS = 120          # window for "active" client selection + recent-event rules
NOW = datetime.utcnow()
TODAY = NOW.date()


# ── banding ──────────────────────────────────────────────────────────────────
def band_for(score):
    if score >= 70:  return "Critical"
    if score >= 45:  return "High"
    if score >= 25:  return "Medium"
    if score >= 1:   return "Low"
    return "Trusted"


def _parse_dt(s):
    """tx_date / reg_date are strings 'YYYY-MM-DD[ HH:MM:SS]'. Return datetime or None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


# ── schema ───────────────────────────────────────────────────────────────────
def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS retention_flags (
            id           BIGSERIAL PRIMARY KEY,
            client_key   VARCHAR(80) UNIQUE,    -- phone|platform cluster key
            client_id    INTEGER,
            login        INTEGER,
            name         VARCHAR(160),
            phone        VARCHAR(64),
            platform     VARCHAR(16),
            score        INTEGER DEFAULT 0,
            band         VARCHAR(16),
            fired_rules  TEXT,                  -- json: [{rule_id,points,category,description,action,days,detail}]
            fired_count  INTEGER DEFAULT 0,
            top_action   VARCHAR(64),
            top_days     VARCHAR(32),
            n_logins     INTEGER DEFAULT 1,
            total_deposits   DOUBLE PRECISION DEFAULT 0,
            total_withdrawals DOUBLE PRECISION DEFAULT 0,
            net_deposit  DOUBLE PRECISION DEFAULT 0,
            computed_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS retention_flags_band_idx  ON retention_flags(band)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS retention_flags_score_idx ON retention_flags(score DESC)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS retention_flags_login_idx ON retention_flags(login)"))
    db.commit()


# ── data load ────────────────────────────────────────────────────────────────
def load_clusters(db, score_all, limit):
    """Return cluster_key -> dict(client_id, login, name, phone, platform, logins[set])."""
    rows = db.execute(text("""
        SELECT id, login, name, phone, COALESCE(platform,'') AS platform, reg_date
        FROM clients
        WHERE login IS NOT NULL
        ORDER BY id
    """)).fetchall()
    clusters = {}           # key -> cluster dict
    login_to_key = {}
    for r in rows:
        cid, login, name, phone, platform, reg = r
        key = f"{phone or 'L'+str(login)}|{platform}"
        c = clusters.get(key)
        if not c:
            c = clusters[key] = {
                "client_id": cid, "login": login, "name": name,
                "phone": phone, "platform": platform, "logins": set(),
                "reg_date": reg,
            }
        c["logins"].add(login)
        login_to_key[login] = key
        # keep the earliest reg_date for the cluster
        if reg and (not c["reg_date"] or str(reg) < str(c["reg_date"])):
            c["reg_date"] = reg
    return clusters, login_to_key


def load_transactions(db, login_to_key):
    """Aggregate transactions per cluster. Returns key -> list of (dt, type, amount)."""
    by_key = defaultdict(list)
    cutoff = (NOW - timedelta(days=400)).strftime("%Y-%m-%d")  # broad window, string-range
    rows = db.execute(text("""
        SELECT login, tx_type, amount, tx_date
        FROM transactions
        WHERE tx_date >= :cut AND login IS NOT NULL
    """), {"cut": cutoff}).fetchall()
    for login, ttype, amount, tx_date in rows:
        key = login_to_key.get(login)
        if not key:
            continue
        dt = _parse_dt(tx_date)
        if dt:
            by_key[key].append((dt, ttype or "", float(amount or 0)))
    return by_key


def load_deals(db, login_to_key):
    """Per-cluster trade aggregates: first/last trade date, n trades, total volume,
    total profit, recent-window volume halves for the drop rule."""
    agg = defaultdict(lambda: {
        "n": 0, "vol": 0.0, "profit": 0.0, "last": None, "first": None,
        "vol_recent": 0.0, "vol_prev": 0.0,
    })
    recent_cut = int((NOW - timedelta(days=14)).timestamp())
    prev_cut = int((NOW - timedelta(days=28)).timestamp())
    rows = db.execute(text("""
        SELECT login, action, volume, profit, deal_time
        FROM deals
        WHERE action IN (0,1) AND login IS NOT NULL
    """)).fetchall()
    for login, action, volume, profit, deal_time in rows:
        key = login_to_key.get(login)
        if not key:
            continue
        a = agg[key]
        a["n"] += 1
        v = float(volume or 0)
        a["vol"] += v
        a["profit"] += float(profit or 0)
        dt_epoch = int(deal_time or 0)
        if dt_epoch:
            if a["last"] is None or dt_epoch > a["last"]:
                a["last"] = dt_epoch
            if a["first"] is None or dt_epoch < a["first"]:
                a["first"] = dt_epoch
            if dt_epoch >= recent_cut:
                a["vol_recent"] += v
            elif dt_epoch >= prev_cut:
                a["vol_prev"] += v
    return agg


def load_devices(db, login_to_key):
    """Per-cluster: count of distinct device fingerprints first-seen in the last 24h
    (for rule 93 'multiple devices within 24h')."""
    by_key = defaultdict(int)
    rows = db.execute(text("""
        SELECT login, count(*)
        FROM account_identifiers
        WHERE identifier_type IN ('cid','mqid')
          AND first_seen >= NOW() - INTERVAL '24 hours'
        GROUP BY login
    """)).fetchall()
    for login, c in rows:
        key = login_to_key.get(login)
        if key:
            by_key[key] += int(c)
    return by_key


# ── rule evaluation ──────────────────────────────────────────────────────────
def evaluate(cluster, txs, deals, devices, rules):
    """Return list of fired-rule dicts. `rules` maps rule_id -> rule meta dict."""
    fired = []

    def fire(rid, detail):
        r = rules.get(rid)
        if not r:
            return
        fired.append({
            "rule_id": rid, "points": r["risk_points"], "category": r["category"],
            "description": r["description"], "action": r["suggested_action"],
            "days": r["days_to_action"], "detail": detail,
        })

    deps = sorted([(dt, amt) for (dt, tt, amt) in txs if tt == "deposit"], key=lambda x: x[0])
    wds = sorted([(dt, amt) for (dt, tt, amt) in txs if tt == "withdrawal"], key=lambda x: x[0])
    bonus_dep = [(dt, amt) for (dt, tt, amt) in txs if (tt or "").startswith("bonus")]

    total_dep = sum(a for _, a in deps)
    total_wd = sum(a for _, a in wds)
    total_bonus = sum(a for _, a in bonus_dep)
    net = total_dep - total_wd

    d = deals or {}
    n_trades = d.get("n", 0)
    last_trade = datetime.utcfromtimestamp(d["last"]) if d.get("last") else None
    first_trade = datetime.utcfromtimestamp(d["first"]) if d.get("first") else None
    profit = d.get("profit", 0.0)

    # ── Deposit timing (rules 1-3): deposit then withdrawal within X hours ──
    if deps and wds:
        # nearest withdrawal after each deposit
        gaps = []
        for ddt, _ in deps:
            after = [wdt for wdt, _ in wds if wdt >= ddt]
            if after:
                gaps.append((min(after) - ddt).total_seconds() / 3600.0)
        if gaps:
            g = min(gaps)
            if g < 24:   fire(1, f"withdrawal {g:.1f}h after a deposit")
            elif g < 48: fire(2, f"withdrawal {g:.1f}h after a deposit")
            elif g < 72: fire(3, f"withdrawal {g:.1f}h after a deposit")

    # rule 4: >2 deposits within any 24h
    if len(deps) >= 3:
        dts = [dt for dt, _ in deps]
        for i in range(len(dts)):
            j = i
            while j < len(dts) and (dts[j] - dts[i]).total_seconds() <= 86400:
                j += 1
            if j - i > 2:
                fire(4, f"{j - i} deposits within 24h")
                break

    # rules 5/6: deposit without trading 24h / 72h (last deposit, no trade after it)
    if deps:
        last_dep_dt = deps[-1][0]
        traded_after = last_trade and last_trade >= last_dep_dt
        if not traded_after:
            hrs = (NOW - last_dep_dt).total_seconds() / 3600.0
            if hrs >= 72:   fire(6, f"no trade {hrs:.0f}h after last deposit")
            elif hrs >= 24: fire(5, f"no trade {hrs:.0f}h after last deposit")

    # rule 7: second deposit lower than first
    if len(deps) >= 2 and deps[1][1] < deps[0][1]:
        fire(7, f"2nd deposit ${deps[1][1]:.0f} < 1st ${deps[0][1]:.0f}")

    # ── Withdrawal rules ──
    reg_dt = _parse_dt(cluster.get("reg_date"))
    if wds:
        first_wd = wds[0][0]
        if reg_dt:
            age_at_first_wd = (first_wd - reg_dt).days
            if age_at_first_wd <= 7:    fire(8, f"first withdrawal {age_at_first_wd}d after signup")
            elif age_at_first_wd <= 14: fire(9, f"first withdrawal {age_at_first_wd}d after signup")
            # rule 46: new client (<14d) + early withdrawal
            if age_at_first_wd <= 14:
                fire(46, f"withdrawal {age_at_first_wd}d into a new account")
        # rules 12: >2 withdrawals within 7 days
        wdts = [dt for dt, _ in wds]
        for i in range(len(wdts)):
            cnt = sum(1 for x in wdts if 0 <= (x - wdts[i]).total_seconds() <= 7 * 86400)
            if cnt > 2:
                fire(12, f"{cnt} withdrawals within 7 days")
                break
        # rule 13: withdrawal without trading at all
        if n_trades == 0:
            fire(13, "withdrew with zero trades on record")

    # rules 10/11/16: withdraw vs balance. Use balance proxy = total_dep + profit (net funded).
    funded = total_dep + profit
    if total_wd > 0 and funded > 0:
        ratio = total_wd / funded
        if ratio >= 1.0:   fire(16, f"withdrew {ratio*100:.0f}% of funded balance")
        elif ratio >= 0.8: fire(11, f"withdrew {ratio*100:.0f}% of funded balance")
        elif ratio >= 0.5: fire(10, f"withdrew {ratio*100:.0f}% of funded balance")

    # ── Trading activity gaps (18/19) ──
    if n_trades > 0 and last_trade:
        gap_d = (NOW - last_trade).days
        if gap_d >= 7:   fire(19, f"no trades for {gap_d} days")
        elif gap_d >= 3: fire(18, f"no trades for {gap_d} days")
        # rule 24: rapid profit then stop (profitable + idle >=5d)
        if profit > 0 and gap_d >= 5:
            fire(24, f"+${profit:.0f} profit then stopped {gap_d}d")

    # rule 20: trading volume drop >60% (recent 14d vs prior 14d)
    if d.get("vol_prev", 0) > 0:
        drop = 1 - (d.get("vol_recent", 0) / d["vol_prev"])
        if drop > 0.6:
            fire(20, f"volume down {drop*100:.0f}% vs prior 2 weeks")

    # ── Net deposit bands (36-41) ──
    if total_dep > 0:
        net_pct = net / total_dep
        if net < 0:           fire(36, f"net deposit -${abs(net):.0f} (negative)")
        elif net_pct < 0.10:  fire(37, f"net deposit only {net_pct*100:.0f}% of deposits")
        elif net_pct < 0.30:  fire(38, f"net deposit {net_pct*100:.0f}% of deposits")
        elif net_pct > 0.70:  fire(41, f"healthy net {net_pct*100:.0f}% (trusted)")
        elif net_pct > 0.50:  fire(40, f"healthy net {net_pct*100:.0f}% (trusted)")

    # ── Account age (42-45) ──
    if reg_dt:
        age_d = (NOW - reg_dt).days
        if age_d < 7:     fire(42, f"account {age_d}d old")
        elif age_d < 14:  fire(43, f"account {age_d}d old")
        elif age_d > 180: fire(45, f"long-tenure account ({age_d}d)")
        elif age_d > 90:  fire(44, f"established account ({age_d}d)")
        # rule 47: old client (>180d) + normal behavior (positive net, has trades)
        if age_d > 180 and net >= 0 and n_trades > 0:
            fire(47, "long-standing client, healthy behavior")

    # ── Bonus (54,55,56,58,59) ──
    if total_bonus > 0:
        if n_trades == 0:
            fire(54, "bonus credited, no trades")
        if total_bonus > total_dep and total_dep > 0:
            fire(55, f"bonus ${total_bonus:.0f} > deposits ${total_dep:.0f}")
        if len(bonus_dep) >= 3:
            fire(58, f"{len(bonus_dep)} bonus events (repeated)")
        if net < 0:
            fire(59, "bonus used while net is negative")
        # rule 56: bonus + fast withdrawal (bonus then withdrawal within 72h)
        if wds:
            b_last = max(dt for dt, _ in bonus_dep)
            after = [wdt for wdt, _ in wds if wdt >= b_last]
            if after and (min(after) - b_last).total_seconds() / 3600.0 < 72:
                fire(56, "withdrawal <72h after bonus")

    # ── rule 60: repeated deposit-withdraw pattern (>=3 dep & >=3 wd interleaved) ──
    if len(deps) >= 3 and len(wds) >= 3:
        fire(60, f"{len(deps)} deposits / {len(wds)} withdrawals (churn pattern)")

    # ── rule 83: deposit -> wait -> withdraw, no trade ──
    if deps and wds and n_trades == 0:
        fire(83, "deposit then withdrawal with no trading in between")

    # ── Value / trusted (65,66,67,69) ──
    # high LTV (rule 65): large lifetime deposits + positive net
    if total_dep >= 50000 and net > 0:
        fire(65, f"high LTV: ${total_dep:.0f} lifetime deposits")
    # VIP (rule 66): very high deposits
    if total_dep >= 100000 and net > 0:
        fire(66, f"VIP: ${total_dep:.0f} lifetime deposits")
    # high historical profitability for the broker = trader net loss (rule 67)
    if profit <= -5000 and n_trades >= 50:
        fire(67, f"trader net -${abs(profit):.0f} (profitable for broker)")
    # long-term stable trading (rule 69): many trades, old account, positive net
    if n_trades >= 200 and reg_dt and (NOW - reg_dt).days > 180 and net >= 0:
        fire(69, f"{n_trades} trades over a long tenure (stable)")

    # ── rule 93: multiple devices within 24h ──
    if devices and devices >= 2:
        fire(93, f"{devices} new device fingerprints within 24h")

    return fired, {
        "total_dep": total_dep, "total_wd": total_wd, "net": net, "n_trades": n_trades,
    }


# ── main build ───────────────────────────────────────────────────────────────
def build(db, score_all=False, limit=None, verbose=True):
    t0 = time.time()
    db.execute(text("SET idle_in_transaction_session_timeout = 0"))
    ensure_schema(db)

    rules = {}
    for r in db.execute(text(
        "SELECT rule_id, category, description, risk_points, trigger_level, "
        "suggested_action, days_to_action FROM retention_rules WHERE automatable")).fetchall():
        rules[r[0]] = {
            "category": r[1], "description": r[2], "risk_points": r[3],
            "trigger_level": r[4], "suggested_action": r[5], "days_to_action": r[6],
        }
    if verbose:
        print(f"loaded {len(rules)} automatable rules")

    clusters, login_to_key = load_clusters(db, score_all, limit)
    if verbose:
        print(f"{len(clusters)} client clusters across {len(login_to_key)} logins")

    txs = load_transactions(db, login_to_key)
    deals = load_deals(db, login_to_key)
    devices = load_devices(db, login_to_key)
    if verbose:
        print(f"loaded tx for {len(txs)} clusters, deals for {len(deals)} clusters, "
              f"device events for {len(devices)} clusters; aggregation {time.time()-t0:.1f}s")

    # Select which clusters to score.
    keys = list(clusters.keys())
    if not score_all:
        active = [k for k in keys if k in txs or k in deals]
        skipped = len(keys) - len(active)
        keys = active
        if verbose:
            print(f"scoring {len(keys)} ACTIVE clusters (skipped {skipped} with no tx/deals "
                  f"in window; pass --all to include them)")
    if limit:
        keys = keys[:limit]
        if verbose:
            print(f"BOUNDED: scoring only first {len(keys)} clusters (--limit)")

    # Rebuild table from scratch (derived cache).
    db.execute(text("TRUNCATE retention_flags RESTART IDENTITY"))

    written = 0
    band_counts = defaultdict(int)
    batch = []
    for key in keys:
        c = clusters[key]
        fired, agg = evaluate(c, txs.get(key, []), deals.get(key), devices.get(key), rules)
        if not fired:
            continue
        score = sum(f["points"] for f in fired)
        band = band_for(score)
        band_counts[band] += 1
        # top action = highest-points POSITIVE rule
        pos = [f for f in fired if f["points"] > 0]
        top = max(pos, key=lambda f: f["points"]) if pos else None
        batch.append({
            "ck": key, "cid": c["client_id"], "login": c["login"], "name": c["name"],
            "phone": c["phone"], "platform": c["platform"] or None,
            "score": int(score), "band": band,
            "fired": json.dumps(fired), "fc": len(fired),
            "ta": top["action"] if top else None, "td": top["days"] if top else None,
            "nl": len(c["logins"]),
            "dep": agg["total_dep"], "wd": agg["total_wd"], "net": agg["net"],
        })
        if len(batch) >= 500:
            _flush(db, batch); written += len(batch); batch = []
    if batch:
        _flush(db, batch); written += len(batch)
    db.commit()

    if verbose:
        print(f"wrote {written} retention_flags in {time.time()-t0:.1f}s")
        for b in ("Critical", "High", "Medium", "Low", "Trusted"):
            print(f"  {b:9s}: {band_counts.get(b,0)}")
    return written


def _flush(db, batch):
    db.execute(text("""
        INSERT INTO retention_flags
            (client_key, client_id, login, name, phone, platform, score, band,
             fired_rules, fired_count, top_action, top_days, n_logins,
             total_deposits, total_withdrawals, net_deposit, computed_at)
        VALUES (:ck,:cid,:login,:name,:phone,:platform,:score,:band,
                :fired,:fc,:ta,:td,:nl,:dep,:wd,:net,NOW())
        ON CONFLICT (client_key) DO UPDATE SET
            score=EXCLUDED.score, band=EXCLUDED.band, fired_rules=EXCLUDED.fired_rules,
            fired_count=EXCLUDED.fired_count, top_action=EXCLUDED.top_action,
            top_days=EXCLUDED.top_days, total_deposits=EXCLUDED.total_deposits,
            total_withdrawals=EXCLUDED.total_withdrawals, net_deposit=EXCLUDED.net_deposit,
            computed_at=NOW()
    """), batch)


def main():
    score_all = "--all" in sys.argv
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    db = SessionLocal()
    try:
        build(db, score_all=score_all, limit=limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()
