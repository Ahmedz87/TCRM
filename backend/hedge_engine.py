"""
hedge_engine.py — Overlap-based hedge detection across all MT5 accounts.

Builds clean positions (entry->exit join, direction from action), finds
time-overlapping opposite positions on related symbols (same symbol / base /
quote), and rolls up per trader.

Flag rules (a trader is flagged if ANY):
  - >20% of their positions are hedged
  - any hedge involves a CONNECTED account (network_edges)
  - their single biggest win OR biggest loss is a hedged position
"""
from sqlalchemy import text

# ── symbol normalization & relation ────────────────────────────────────────────
OIL = {"USOIL", "UKOIL", "BRENT", "WTI", "XBRUSD", "XTIUSD"}

def normalize_symbol(sym):
    if not sym:
        return ""
    s = sym.upper()
    for suf in (".C", ".R", ".M", ".PRO", "."):
        if s.endswith(suf):
            s = s[:-len(suf)]
    return s

def base_quote(sym):
    s = normalize_symbol(sym)
    if s in OIL:
        return ("OIL", "USD")
    if len(s) == 6 and s.isalpha():
        return (s[:3], s[3:])
    if s.endswith("USD") and len(s) > 3:
        return (s[:-3], "USD")
    return (s, None)

def relation(symA, symB):
    a, b = normalize_symbol(symA), normalize_symbol(symB)
    if a == b:
        return "same_symbol"
    ba, qa = base_quote(a); bb, qb = base_quote(b)
    if qa is None or qb is None:
        return None
    if ba == bb:
        return "same_base"
    if qa == qb:
        return "same_quote"
    return None

FLAG_RATIO = 0.20  # >20% hedged


def _positions_for(db, logins, since_ts):
    """Clean positions via entry->exit join. direction from entry action (0=buy,1=sell)."""
    rows = db.execute(text("""
        SELECT e.login, e.action AS entry_act, e.deal_time AS open_t,
               x.deal_time AS close_t, x.profit,
               COALESCE(x.volume, e.volume) AS vol,
               COALESCE(x.symbol, e.symbol) AS sym, e.position_id
        FROM deals e
        JOIN deals x ON e.position_id = x.position_id AND e.login = x.login
        WHERE e.login = ANY(:l) AND e.entry = 0 AND x.entry = 1
          AND e.platform='MT5' AND e.action IN (0,1)
          AND e.open_time IS NOT NULL
          AND e.deal_time >= :since
    """), {"l": list(logins), "since": since_ts}).fetchall()
    pos = []
    for login, act, ot, ct, profit, vol, sym, pid in rows:
        pos.append({
            "login": login, "dir": "buy" if act == 0 else "sell",
            "open": int(ot or 0), "close": int(ct or 0),
            "profit": float(profit or 0), "vol": float(vol or 0),
            "sym": sym, "pid": pid,
        })
    return pos


def _find_overlap_hedges(positions):
    """
    Efficient overlap hedge detection. Sort by open time; for each position,
    only compare with later positions that start before this one closes.
    Returns (hedged_index_set, listed_rows).
    """
    pos = sorted(range(len(positions)), key=lambda i: positions[i]["open"])
    hedged = set()
    listed = []
    n = len(pos)
    for ii in range(n):
        i = pos[ii]
        a = positions[i]
        for jj in range(ii + 1, n):
            j = pos[jj]
            b = positions[j]
            if b["open"] > a["close"]:
                break  # sorted: no further can overlap a
            if a["dir"] == b["dir"]:
                continue
            rel = relation(a["sym"], b["sym"])
            if not rel:
                continue
            # overlap guaranteed on lower bound; confirm upper
            if a["open"] <= b["close"] and b["open"] <= a["close"]:
                hedged.add(i); hedged.add(j)
                ov = min(a["close"], b["close"]) - max(a["open"], b["open"])
                buy = a if a["dir"] == "buy" else b
                sell = b if a["dir"] == "buy" else a
                listed.append({
                    "buy_login": buy["login"], "sell_login": sell["login"],
                    "buy_sym": buy["sym"], "sell_sym": sell["sym"], "relation": rel,
                    "buy_vol": buy["vol"], "sell_vol": sell["vol"],
                    "overlap_sec": ov, "cross": buy["login"] != sell["login"],
                    "buy_profit": buy["profit"], "sell_profit": sell["profit"],
                    "open": max(buy["open"], sell["open"]),
                })
    return hedged, listed


def _connected(db, login):
    rows = db.execute(text("""
        SELECT login_b, reason FROM network_edges WHERE login_a=:l
        UNION SELECT login_a, reason FROM network_edges WHERE login_b=:l
    """), {"l": login}).fetchall()
    return {r[0]: r[1] for r in rows if r[0] and r[0] != login}


def _strong_link_to_hedger(db, login, connected):
    """True if login shares a STRONG link (ip/cid/mqid) with another account
    that is itself a heavy hedger. This is the real coordinated-farm signal."""
    strong = db.execute(text("""
        SELECT DISTINCT CASE WHEN login_a=:l THEN login_b ELSE login_a END AS other
        FROM network_edges
        WHERE (login_a=:l OR login_b=:l) AND reason IN ('ip','cid','mqid')
    """), {"l": login}).fetchall()
    others = [r[0] for r in strong if r[0] and r[0] != login]
    return others


def scan_account(db, login, since_ts):
    """
    Scan one account (+ connected accounts). Produce a 0-100 abuse SCORE.
    Only accounts scoring >= SCORE_THRESHOLD are flagged, so only the top tier
    of genuine abusers surfaces (not every part-time hedger).
    """
    connected = _connected(db, login)
    group = [login] + list(connected.keys())
    positions = _positions_for(db, group, since_ts)
    own = [p for p in positions if p["login"] == login]
    if len(own) < 5:
        return None

    hedged_idx, listed = _find_overlap_hedges(positions)
    own_pids = {p["pid"] for p in own}
    hedged_own_pids = {positions[i]["pid"] for i in hedged_idx if positions[i]["login"] == login}
    total_own = len(own_pids)
    hedged_own = len(hedged_own_pids)
    ratio = hedged_own / total_own if total_own else 0

    # bonus / balance context
    meta = db.execute(text("""
        SELECT COALESCE(credit,0), COALESCE(balance,0), COALESCE(total_deposits,0)
        FROM trading_accounts WHERE login=:l LIMIT 1
    """), {"l": login}).fetchone()
    credit = float(meta[0]) if meta else 0.0
    balance = float(meta[1]) if meta else 0.0
    deposits = float(meta[2]) if meta else 0.0

    has_bonus = credit > 0
    drain = 0.0
    if has_bonus:
        drain = 1.0 if balance < credit * 0.1 else max(0.0, 1 - balance / (credit + 1))

    # strong-link to another account that also hedges
    strong_others = _strong_link_to_hedger(db, login, connected)
    strong_hedge_link = False
    if strong_others:
        cnt = db.execute(text("""
            SELECT COUNT(*) FROM hedge_flagged_traders WHERE login = ANY(:o)
        """), {"o": strong_others}).fetchone()
        # may be empty on first pass; also treat any cross hedge as the signal
        strong_hedge_link = (cnt and cnt[0] > 0)
    cross_hedge = any(r["cross"] for r in listed)

    # biggest win/loss hedged (minor)
    own_sorted = sorted(own, key=lambda p: p["profit"])
    big_is_hedge = bool(own_sorted) and (
        own_sorted[0]["pid"] in hedged_own_pids or own_sorted[-1]["pid"] in hedged_own_pids)

    # ── SCORING ────────────────────────────────────────────────────────────────
    # ratio only meaningful above 0.4; rescale 0.4..1.0 -> 0..1
    ratio_factor = max(0.0, (ratio - 0.4) / 0.6)
    bonus_factor = min(1.0, credit / (deposits + 1)) if has_bonus else 0.0
    link_factor = 1.0 if (strong_hedge_link or (strong_others and cross_hedge)) else 0.0
    drain_factor = drain

    # Base score from hedging intensity
    score = 100 * (0.45 * ratio_factor + 0.25 * bonus_factor +
                   0.20 * link_factor + 0.10 * drain_factor)
    # Corroboration bumps
    if big_is_hedge:
        score += 3
    if has_bonus and ratio >= 0.6:
        score += 8   # the core abuse combo
    score = min(100, score)

    SCORE_THRESHOLD = 45  # only top tier
    if score < SCORE_THRESHOLD:
        return None

    hedged_vol = sum(positions[i]["vol"] for i in hedged_idx if positions[i]["login"] == login)
    total_vol = sum(p["vol"] for p in own) or 1

    reasons = []
    reasons.append(f"{ratio*100:.0f}% of positions hedged")
    if has_bonus:
        reasons.append(f"bonus ${credit:,.0f}" + (", drained" if drain > 0.8 else ""))
    if link_factor:
        reasons.append("strong link to another hedging account")
    if big_is_hedge:
        reasons.append("biggest win/loss is a hedge")

    return {
        "login": login,
        "score": int(round(score)),
        "total_positions": total_own,
        "hedged_positions": hedged_own,
        "hedged_ratio": ratio,
        "hedged_volume_ratio": hedged_vol / total_vol,
        "has_connected_hedge": bool(link_factor),
        "biggest_is_hedge": big_is_hedge,
        "has_bonus": has_bonus,
        "credit": credit,
        "connected_accounts": strong_others[:20],
        "reasons": reasons,
        "listed_trades": listed[:50],
        "listed_count": len(listed),
    }
