"""
abuse_detectors_v2.py — Rebuilt scoring-based abuse detection.

Three categories, each producing ONE score (0-100) per client:
  BONUS  — bonus credit + hedging behaviour, weighted by count/volume/PnL impact + drain
  SWAP   — swap-free/Islamic accounts farming overnight swap on carry symbols
  TOXIC  — night-hour trading on rare/exotic symbols with abnormal win rate

Each detector writes scored cases to abuse_cases. Severity is derived from the
score so 'critical' actually means act-now:
   score >= 75 -> critical
   score >= 55 -> high
   score >= 40 -> medium
   below 40    -> not flagged
"""
from sqlalchemy import text
from datetime import datetime
import json

# ── Severity from score ────────────────────────────────────────────────────────
def severity_for(score):
    if score >= 75: return "critical"
    if score >= 55: return "high"
    if score >= 40: return "medium"
    return None

FLAG_THRESHOLD = 40  # below this, not an abuse case


def _save_case(db, abuse_type, severity, logins, symbol, risk, confidence,
               net_score, evidence, deposits, exposure):
    """Insert or update a scored abuse case."""
    login_a = logins[0]
    login_b = logins[1] if len(logins) > 1 else None
    all_logins = ",".join(str(x) for x in logins)
    existing = db.execute(text("""
        SELECT id FROM abuse_cases
        WHERE abuse_type=:t AND login_a=:la AND COALESCE(symbol,'')=:s
          AND status NOT IN ('resolved')
        LIMIT 1
    """), {"t": abuse_type, "la": login_a, "s": symbol or ''}).fetchone()
    if existing:
        db.execute(text("""
            UPDATE abuse_cases SET severity=:sev, risk_score=:risk, confidence=:conf,
                network_score=:ns, evidence=:ev, total_deposits=:dep, exposure=:exp,
                all_logins=:al, login_b=:lb, updated_at=NOW()
            WHERE id=:id
        """), {"sev": severity, "risk": risk, "conf": confidence, "ns": net_score,
               "ev": evidence, "dep": deposits, "exp": exposure, "al": all_logins,
               "lb": login_b, "id": existing[0]})
    else:
        db.execute(text("""
            INSERT INTO abuse_cases
                (abuse_type, severity, login_a, login_b, all_logins, symbol,
                 risk_score, confidence, network_score, evidence,
                 total_deposits, exposure, status, created_at, updated_at)
            VALUES (:t,:sev,:la,:lb,:al,:sym,:risk,:conf,:ns,:ev,:dep,:exp,'open',NOW(),NOW())
        """), {"t": abuse_type, "sev": severity, "la": login_a, "lb": login_b,
               "al": all_logins, "sym": symbol, "risk": risk, "conf": confidence,
               "ns": net_score, "ev": evidence, "dep": deposits, "exp": exposure})


# ══════════════════════════════════════════════════════════════════════════════
# BONUS ABUSE — combined hedge score per client
# ══════════════════════════════════════════════════════════════════════════════
def detect_bonus(db):
    """
    For each client with bonus credit, find hedged trades (same symbol, opposite
    direction, close times within HEDGE_WINDOW seconds, similar volume) and score:

      hedge_count_ratio  = hedged_trades / total_trades
      hedge_volume_ratio = hedged_volume / total_volume
      hedge_pnl_ratio    = |pnl of hedged trades| / |pnl of all trades|
      drain_factor       = 1 if balance fell to near-0 after bonus, else partial
      bonus_factor       = bonus credit relative to deposits

    score = 100 * (0.30*count + 0.25*volume + 0.30*pnl + 0.15*drain), then
    nudged up by bonus_factor. Flag only if score >= FLAG_THRESHOLD.
    """
    HEDGE_WINDOW = 300  # seconds between opposite close times to count as hedge
    VOL_TOL = 0.5       # volume similarity tolerance (within 50%)

    # candidate accounts: have bonus credit
    accts = db.execute(text("""
        SELECT ta.login, ta.client_id, COALESCE(ta.credit,0) as credit,
               COALESCE(ta.balance,0) as balance,
               COALESCE(ta.total_deposits,0) as deposits
        FROM trading_accounts ta
        WHERE ta.credit > 0 AND ta.client_id IS NOT NULL
    """)).fetchall()

    for a in accts:
        login, client_id, credit, balance, deposits = a
        # pull this login's trades
        trades = db.execute(text("""
            SELECT symbol, direction, volume, profit, deal_time
            FROM deals
            WHERE login=:l AND direction IN ('buy','sell')
            ORDER BY symbol, deal_time
        """), {"l": login}).fetchall()
        if len(trades) < 2:
            continue

        total_trades = len(trades)
        total_volume = sum(t[2] or 0 for t in trades)
        total_pnl_abs = sum(abs(t[3] or 0) for t in trades) or 1

        # group by symbol, find opposite-direction near-time pairs
        by_symbol = {}
        for t in trades:
            by_symbol.setdefault(t[0], []).append(t)

        hedged_idx = set()
        hedged_volume = 0.0
        hedged_pnl_abs = 0.0
        hedge_pairs = 0

        for sym, ts in by_symbol.items():
            buys  = [(i, t) for i, t in enumerate(ts) if t[1] == 'buy']
            sells = [(i, t) for i, t in enumerate(ts) if t[1] == 'sell']
            used_sell = set()
            for bi, bt in buys:
                bvol = bt[2] or 0
                btime = bt[4] or 0
                for si, st_ in sells:
                    if si in used_sell:
                        continue
                    svol = st_[2] or 0
                    stime = st_[4] or 0
                    if abs((btime or 0) - (stime or 0)) <= HEDGE_WINDOW and \
                       svol > 0 and abs(bvol - svol) / max(bvol, svol) <= VOL_TOL:
                        used_sell.add(si)
                        hedge_pairs += 1
                        key_b = (sym, 'buy', bi); key_s = (sym, 'sell', si)
                        if key_b not in hedged_idx:
                            hedged_idx.add(key_b); hedged_volume += bvol
                            hedged_pnl_abs += abs(bt[3] or 0)
                        if key_s not in hedged_idx:
                            hedged_idx.add(key_s); hedged_volume += svol
                            hedged_pnl_abs += abs(st_[3] or 0)
                        break

        hedged_trades = len(hedged_idx)
        if hedged_trades == 0:
            continue

        count_ratio  = hedged_trades / total_trades
        volume_ratio = hedged_volume / (total_volume or 1)
        pnl_ratio    = hedged_pnl_abs / total_pnl_abs

        # drain: balance near 0 but had bonus -> classic "double and dash"
        drain = 1.0 if balance < (credit * 0.1) else max(0.0, 1 - balance / (credit + 1))
        bonus_factor = min(1.0, credit / (deposits + 1)) if deposits > 0 else 0.5

        score = 100 * (0.30*count_ratio + 0.25*volume_ratio + 0.30*pnl_ratio + 0.15*drain)
        score = min(100, score * (1 + 0.2*bonus_factor))

        sev = severity_for(score)
        if not sev:
            continue

        confidence = int(min(99, 50 + score/2))
        evidence = (
            f"Bonus client: {hedged_trades}/{total_trades} trades hedged "
            f"({count_ratio*100:.0f}% count, {volume_ratio*100:.0f}% volume, "
            f"{pnl_ratio*100:.0f}% of P&L). {hedge_pairs} hedge pairs. "
            f"Bonus credit ${credit:,.0f}, balance ${balance:,.0f}"
            + (", account drained" if drain > 0.8 else "") + "."
        )
        _save_case(db, 'bonus_hedge', sev, [login], None,
                   int(score), confidence, 0, evidence, float(deposits), float(credit))


# ── Connected accounts (same logic as the Network page) ────────────────────────
# Strong links = shared device/network (ip, cid, mqid). Weak = family, ib.
STRONG_REASONS = ('ip', 'cid', 'mqid')

def _connected_accounts(db, login, strong_only=True):
    """Return {connected_login: reason} for accounts linked to `login`.
    Uses network_edges (both directions). strong_only keeps device/network links."""
    reasons = STRONG_REASONS if strong_only else STRONG_REASONS + ('family', 'ib')
    rows = db.execute(text("""
        SELECT login_b AS other, reason FROM network_edges
        WHERE login_a = :l AND reason = ANY(:reasons)
        UNION
        SELECT login_a AS other, reason FROM network_edges
        WHERE login_b = :l AND reason = ANY(:reasons)
    """), {"l": login, "reasons": list(reasons)}).fetchall()
    out = {}
    for other, reason in rows:
        if other and other != login:
            out[other] = reason
    return out


# ══════════════════════════════════════════════════════════════════════════════
# BONUS ABUSE — CROSS-ACCOUNT hedge farm (linked accounts hedging each other)
# ══════════════════════════════════════════════════════════════════════════════
def detect_bonus_cross(db):
    """
    A smarter bonus farm hedges ACROSS linked accounts:
      Account A (bonus) buys gold; linked Account B sells gold, same time/volume.
    Each account alone looks normal; together they're hedged at zero risk.

    For each bonus account, gather its strongly-linked accounts (shared IP/CID/
    device), then look for opposite-direction trades on the same symbol across
    the group within HEDGE_WINDOW and similar volume. Score the cluster.
    """
    HEDGE_WINDOW = 300
    VOL_TOL = 0.5

    bonus_accts = db.execute(text("""
        SELECT ta.login, COALESCE(ta.credit,0), COALESCE(ta.total_deposits,0)
        FROM trading_accounts ta
        WHERE ta.credit > 0 AND ta.client_id IS NOT NULL
    """)).fetchall()

    processed_clusters = set()

    for login, credit, deposits in bonus_accts:
        linked = _connected_accounts(db, login, strong_only=True)
        if not linked:
            continue
        group = tuple(sorted({login, *linked.keys()}))
        cluster_key = group
        if cluster_key in processed_clusters:
            continue
        processed_clusters.add(cluster_key)

        # pull trades for the whole group
        trades = db.execute(text("""
            SELECT login, symbol, direction, volume, profit, deal_time
            FROM deals
            WHERE login = ANY(:g) AND direction IN ('buy','sell')
            ORDER BY symbol, deal_time
        """), {"g": list(group)}).fetchall()
        if len(trades) < 4:
            continue

        # group by symbol; find opposite trades from DIFFERENT accounts, near in time
        by_symbol = {}
        for t in trades:
            by_symbol.setdefault(t[1], []).append(t)

        cross_pairs = 0
        cross_volume = 0.0
        involved = set()
        for sym, ts in by_symbol.items():
            buys  = [t for t in ts if t[2] == 'buy']
            sells = [t for t in ts if t[2] == 'sell']
            used = set()
            for bi, bt in enumerate(buys):
                bvol, btime, blogin = bt[3] or 0, bt[5] or 0, bt[0]
                for si, st_ in enumerate(sells):
                    if si in used:
                        continue
                    svol, stime, slogin = st_[3] or 0, st_[5] or 0, st_[0]
                    if blogin == slogin:
                        continue  # must be DIFFERENT accounts (cross-account)
                    if abs(btime - stime) <= HEDGE_WINDOW and svol > 0 and \
                       abs(bvol - svol) / max(bvol, svol) <= VOL_TOL:
                        used.add(si)
                        cross_pairs += 1
                        cross_volume += bvol + svol
                        involved.add(blogin); involved.add(slogin)
                        break

        if cross_pairs < 2:
            continue  # need a real pattern, not one coincidence

        total_trades = len(trades)
        total_volume = sum(t[3] or 0 for t in trades) or 1
        # cluster-level credit & deposits
        grp_meta = db.execute(text("""
            SELECT COALESCE(SUM(credit),0), COALESCE(SUM(total_deposits),0),
                   COALESCE(SUM(balance),0)
            FROM trading_accounts WHERE login = ANY(:g)
        """), {"g": list(group)}).fetchone()
        grp_credit, grp_deposits, grp_balance = float(grp_meta[0]), float(grp_meta[1]), float(grp_meta[2])

        pair_ratio = min(1.0, cross_pairs / (total_trades / 2))
        volume_ratio = min(1.0, cross_volume / total_volume)
        involve_ratio = len(involved) / len(group)
        drain = 1.0 if grp_balance < (grp_credit * 0.15) else max(0.0, 1 - grp_balance / (grp_credit + 1))

        score = 100 * (0.35*pair_ratio + 0.30*volume_ratio + 0.20*involve_ratio + 0.15*drain)
        score = min(100, score)
        sev = severity_for(score)
        if not sev:
            continue

        confidence = int(min(99, 55 + score/2))
        # describe how they're linked
        link_types = sorted(set(linked.values()))
        link_desc = "/".join(link_types)
        evidence = (
            f"Cross-account bonus farm: {len(involved)} of {len(group)} linked "
            f"accounts hedging each other on shared {link_desc}. "
            f"{cross_pairs} cross-account hedge pairs detected. "
            f"Group bonus ${grp_credit:,.0f}, deposits ${grp_deposits:,.0f}, "
            f"balance ${grp_balance:,.0f}"
            + (", drained" if drain > 0.8 else "") + "."
        )
        # network_score reflects link strength: cid/ip stronger than family
        net = 100 if any(r in ('cid','ip','mqid') for r in link_types) else 40
        _save_case(db, 'bonus_farm', sev, list(group), None,
                   int(score), confidence, net, evidence, grp_deposits, grp_credit)


# ══════════════════════════════════════════════════════════════════════════════
# SWAP ABUSE — Islamic/swap-free accounts farming overnight swap
# ══════════════════════════════════════════════════════════════════════════════
def detect_swap(db):
    """
    Islamic (swap-free) accounts shouldn't pay swap, so holding positions
    overnight on positive-carry symbols is free carry. Score by:
      - share of trades that accrued swap (overnight holds)
      - concentration on a few carry symbols
      - total swap-free benefit captured
    """
    accts = db.execute(text("""
        SELECT ta.login, ta.client_id, COALESCE(ta.total_deposits,0)
        FROM trading_accounts ta
        WHERE ta.is_islamic = true AND ta.client_id IS NOT NULL
    """)).fetchall()

    for login, client_id, deposits in accts:
        rows = db.execute(text("""
            SELECT symbol,
                   COUNT(*) as trades,
                   COUNT(*) FILTER (WHERE swap != 0) as swap_trades,
                   COALESCE(SUM(volume),0) as vol,
                   COALESCE(SUM(profit),0) as pnl
            FROM deals
            WHERE login=:l AND direction IN ('buy','sell')
            GROUP BY symbol
        """), {"l": login}).fetchall()
        if not rows:
            continue
        total_trades = sum(r[1] for r in rows)
        overnight = sum(r[2] for r in rows)
        if total_trades < 5 or overnight == 0:
            continue
        overnight_ratio = overnight / total_trades
        # symbol concentration (top symbol share)
        top_share = max(r[1] for r in rows) / total_trades
        total_pnl = sum(r[4] for r in rows)

        score = 100 * (0.6*overnight_ratio + 0.4*top_share)
        if total_pnl <= 0:
            score *= 0.5  # only profitable carry is abuse-worthy
        sev = severity_for(score)
        if not sev:
            continue
        confidence = int(min(99, 45 + score/2))
        top_sym = max(rows, key=lambda r: r[1])[0]
        evidence = (
            f"Swap-free account: {overnight}/{total_trades} overnight holds "
            f"({overnight_ratio*100:.0f}%), concentrated on {top_sym} "
            f"({top_share*100:.0f}%). Net P&L ${total_pnl:,.0f}."
        )
        _save_case(db, 'swap_abuse', sev, [login], top_sym,
                   int(score), confidence, 0, evidence, float(deposits), float(total_pnl))


# ══════════════════════════════════════════════════════════════════════════════
# TOXIC ABUSE — night-hour trading on rare symbols with abnormal win rate
# ══════════════════════════════════════════════════════════════════════════════
def detect_toxic(db):
    """
    Latency/arbitrage style: trading rare/exotic symbols during illiquid night
    hours with an abnormally high win rate. Score by:
      - share of trades in night window (00:00-05:00 server time)
      - rarity of the symbols traded (low market-wide volume)
      - win rate on those night trades
    """
    NIGHT_START, NIGHT_END = 0, 5  # hours

    # market-wide symbol popularity (to define 'rare')
    pop = db.execute(text("""
        SELECT symbol, COUNT(*) c FROM deals
        WHERE direction IN ('buy','sell') GROUP BY symbol
    """)).fetchall()
    pop_map = {r[0]: r[1] for r in pop}
    if not pop_map:
        return
    median_pop = sorted(pop_map.values())[len(pop_map)//2]

    # candidate logins: those with night trades
    cand = db.execute(text(f"""
        SELECT login, COUNT(*) night_trades
        FROM deals
        WHERE direction IN ('buy','sell')
          AND EXTRACT(HOUR FROM to_timestamp(deal_time)) >= {NIGHT_START}
          AND EXTRACT(HOUR FROM to_timestamp(deal_time)) < {NIGHT_END}
        GROUP BY login
        HAVING COUNT(*) >= 10
    """)).fetchall()

    for login, night_trades in cand:
        rows = db.execute(text(f"""
            SELECT symbol, direction, profit, deal_time,
                   EXTRACT(HOUR FROM to_timestamp(deal_time)) as hr
            FROM deals
            WHERE login=:l AND direction IN ('buy','sell')
        """), {"l": login}).fetchall()
        total = len(rows)
        if total == 0:
            continue
        night = [r for r in rows if NIGHT_START <= (r[4] or 12) < NIGHT_END]
        if len(night) < 10:
            continue
        night_ratio = len(night) / total
        # rarity: average inverse-popularity of night symbols
        rare_hits = sum(1 for r in night if pop_map.get(r[0], 1e9) < median_pop)
        rarity = rare_hits / len(night)
        # win rate on night trades
        wins = sum(1 for r in night if (r[2] or 0) > 0)
        win_rate = wins / len(night)
        night_pnl = sum(r[2] or 0 for r in night)

        score = 100 * (0.35*night_ratio + 0.35*rarity + 0.30*max(0, win_rate-0.5)*2)
        sev = severity_for(score)
        if not sev:
            continue
        confidence = int(min(99, 45 + score/2))
        top_sym = max(set(r[0] for r in night), key=lambda s: sum(1 for r in night if r[0]==s))
        evidence = (
            f"Night trading: {len(night)}/{total} trades in 00:00-05:00 "
            f"({night_ratio*100:.0f}%), {rarity*100:.0f}% on rare symbols, "
            f"win rate {win_rate*100:.0f}%. Top: {top_sym}. Night P&L ${night_pnl:,.0f}."
        )
        _save_case(db, 'toxic_night', sev, [login], top_sym,
                   int(score), confidence, 0, evidence, 0.0, float(night_pnl))


def run_v2_detectors(db):
    results = {}
    for name, fn in [('bonus', detect_bonus), ('bonus_cross', detect_bonus_cross),
                     ('swap', detect_swap), ('toxic', detect_toxic)]:
        try:
            fn(db); db.commit(); results[name] = 'ok'
        except Exception as e:
            db.rollback(); results[name] = f'error: {str(e)[:150]}'
    return results
