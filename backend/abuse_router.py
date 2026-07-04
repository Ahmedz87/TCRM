"""
abuse_router.py — Complete 3-System Abuse Detection Engine
System 1: Bonus Hedge Abuse (6 layers)
System 2: Swap Arbitrage Abuse (5 signals)  
System 3: Toxic Flow (Night Latency + General Latency + News + Midnight Exotic)
"""
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/abuse", tags=["Abuse Detection"])


def parse_logins(raw, fallback):
    """all_logins is stored comma-separated ('1,2,3'); older rows may be JSON.
    Return a list of ints either way, falling back to [fallback]."""
    if not raw:
        return [fallback] if fallback else []
    s = str(raw).strip()
    if s.startswith("["):
        try:
            return [int(x) for x in json.loads(s)]
        except Exception:
            pass
    out = [int(x) for x in s.split(",") if x.strip().lstrip("-").isdigit()]
    return out or ([fallback] if fallback else [])

# ── Constants ─────────────────────────────────────────────────────────────────

EXOTIC_SYMBOLS = [
    'XAGUSD.','XAGUSD.x','XAUUSD.','XAUUSD.v','XAUUSD.x','XAUUSD.c',
    'USDCNH.c','USDTRY','USTEC.U25','USTEC.H25','USTEC.M25','USTEC.U26',
    'JP225','AUS200','NGAS','EURAUD.','USDJPY.','USDJPY.c','CHFJPY.',
    'EURUSD.','GBPUSD.','USDCAD.c','GBPCAD.c','XAUEUR.c','UNIUSD',
]

NIGHT_EXOTIC_CONTAINS = ['MXN','TRY','ZAR','PLN','HUF','BRL']

SWAP_FREE_VECTOR = {
    'XAUUSD': 'buy', 'XAGUSD': 'buy',
    'USDJPY': 'sell', 'GBPJPY': 'sell',
    'USDTRY': 'buy', 'USDMXN': 'buy',
    'USDZAR': 'buy', 'EURMXN': 'buy',
}

SWAP_FREE_GROUPS = ['IS','Islamic','islamic','swap-free','swapfree']

CORRELATED_PAIRS = [
    ('EURUSD','GBPUSD',0.85,'same'),
    ('EURUSD','AUDUSD',0.70,'same'),
    ('XAUUSD','XAGUSD',0.90,'same'),
    ('USDJPY','USDCHF',0.80,'same'),
    ('DJ30','USTEC',0.92,'same'),
    ('USOIL','UKOIL',0.97,'same'),
]

MIDNIGHT_START = 0
MIDNIGHT_END   = 7200
NIGHT_START    = 10800  # 03:00 UTC
NIGHT_END      = 18000  # 05:00 UTC

# ── Helpers ───────────────────────────────────────────────────────────────────

def network_score_for_logins(db, logins: list) -> int:
    if len(logins) < 2:
        return 0
    score = 0
    ll = list(set(logins))
    cids = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT identifier_value FROM account_identifiers
            WHERE login=ANY(:l) AND identifier_type='cid'
            AND identifier_value != '0' AND identifier_value != ''
            GROUP BY identifier_value HAVING COUNT(DISTINCT login)>1
        ) x
    """), {"l": ll}).scalar() or 0
    if cids: score += 50

    ips = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT identifier_value FROM account_identifiers
            WHERE login=ANY(:l) AND identifier_type='ip'
            GROUP BY identifier_value HAVING COUNT(DISTINCT login)>1
        ) x
    """), {"l": ll}).scalar() or 0
    if ips: score += 35

    names = db.execute(text("""
        SELECT COUNT(DISTINCT name) FROM clients
        WHERE login=ANY(:l) AND name IS NOT NULL AND name!=''
    """), {"l": ll}).scalar() or 0
    if names == 1: score += 30

    ibs = db.execute(text("""
        SELECT COUNT(DISTINCT agent) FROM clients
        WHERE login=ANY(:l) AND agent>0
    """), {"l": ll}).scalar() or 0
    if ibs == 1: score += 15

    return min(score, 100)


def save_case(db, abuse_type, severity, logins, symbol, risk, confidence, net_score, evidence, deposits, exposure):
    login_a = logins[0] if logins else 0
    login_b = logins[1] if len(logins) > 1 else None
    existing = db.execute(text("""
        SELECT id FROM abuse_cases
        WHERE abuse_type=:t AND login_a=:la AND status NOT IN ('resolved')
        AND COALESCE(symbol,'')=COALESCE(:s,'')
        LIMIT 1
    """), {"t": abuse_type, "la": login_a, "s": symbol or ''}).fetchone()

    if existing:
        db.execute(text("""
            UPDATE abuse_cases SET risk_score=:r,confidence=:c,
            network_score=:n,evidence=:e,exposure=:ex,updated_at=NOW()
            WHERE id=:id
        """), {"r": risk,"c": confidence,"n": net_score,"e": evidence,"ex": exposure,"id": existing[0]})
    else:
        db.execute(text("""
            INSERT INTO abuse_cases
            (abuse_type,severity,login_a,login_b,all_logins,symbol,
             risk_score,confidence,network_score,evidence,
             total_deposits,exposure,status,created_at,updated_at)
            VALUES(:t,:sev,:la,:lb,:al,:sym,:r,:c,:n,:e,:dep,:ex,'open',NOW(),NOW())
        """), {
            "t": abuse_type,"sev": severity,"la": login_a,"lb": login_b,
            "al": json.dumps(logins),"sym": symbol or '',
            "r": risk,"c": confidence,"n": net_score,"e": evidence,
            "dep": deposits,"ex": exposure
        })


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM 1 — BONUS HEDGE ABUSE
# ══════════════════════════════════════════════════════════════════════════════

def detect_bonus_hedge_l1(db):
    """Layer 1: Classic same-symbol hedge between bonus accounts within 20 seconds."""
    rows = db.execute(text("""
        SELECT a.login, b.login, a.symbol,
               a.deal_time, b.deal_time,
               a.volume/10000.0, b.volume/10000.0,
               a.price,
               ABS(a.deal_time - b.deal_time) as diff
        FROM deals a
        JOIN deals b ON a.symbol=b.symbol
            AND a.login != b.login
            AND a.direction='buy' AND b.direction='sell'
            AND a.entry=0 AND b.entry=0
            AND ABS(a.deal_time-b.deal_time) <= 20
            AND a.deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*90
            AND a.deal_type='trade' AND b.deal_type='trade'
        WHERE a.login IN (
            SELECT DISTINCT login FROM transactions WHERE tx_type='bonus_deposit'
        )
        AND b.login IN (
            SELECT DISTINCT login FROM transactions WHERE tx_type='bonus_deposit'
        )
        ORDER BY a.deal_time DESC
        LIMIT 200
    """)).fetchall()

    seen = set()
    for r in rows:
        key = tuple(sorted([r[0],r[1]])) + (r[2],)
        if key in seen: continue
        seen.add(key)
        logins = [r[0],r[1]]
        ns = network_score_for_logins(db, logins)
        vol_ratio = min(r[5],r[6])/max(r[5],r[6]) if max(r[5],r[6])>0 else 0
        risk = min(int(75 + ns*0.15 + vol_ratio*10), 100)
        conf = min(int(80 + ns*0.1), 99)
        deps = db.execute(text("SELECT COALESCE(SUM(total_deposits),0) FROM clients WHERE login=ANY(:l)"), {"l": logins}).scalar() or 0
        bonus = db.execute(text("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE login=ANY(:l) AND tx_type='bonus_deposit'"), {"l": logins}).scalar() or 0
        sev = 'critical' if risk>=80 else 'high' if risk>=70 else 'medium'
        ev = (f"BONUS HEDGE L1: #{r[0]} BUY {r[5]:.2f}L and #{r[1]} SELL {r[6]:.2f}L "
              f"{r[2]} within {r[8]}s. Both accounts have active bonus. "
              f"Total bonus at risk: ${float(bonus):,.0f}. Network score: {ns}/100.")
        save_case(db,'bonus_hedge_l1',sev,logins,r[2],risk,conf,ns,ev,float(deps),float(bonus))


def detect_bonus_hedge_l2(db):
    """Layer 2: Split volume hedge - aggregated net position within 60 minutes."""
    bonus_accounts = db.execute(text("""
        SELECT DISTINCT login FROM transactions WHERE tx_type='bonus_deposit'
    """)).fetchall()
    bonus_logins = [r[0] for r in bonus_accounts]
    if not bonus_logins:
        return

    # Find bonus accounts with large net positions in 60min windows
    rows = db.execute(text("""
        SELECT login, symbol,
               (deal_time/3600)*3600 as window_start,
               SUM(CASE WHEN direction='buy' THEN volume ELSE 0 END)/10000.0 as buy_vol,
               SUM(CASE WHEN direction='sell' THEN volume ELSE 0 END)/10000.0 as sell_vol,
               COUNT(*) as trade_count
        FROM deals
        WHERE deal_type='trade' AND entry=0
        AND login=ANY(:bl)
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*90
        GROUP BY login, symbol, (deal_time/3600)*3600
        HAVING COUNT(*) >= 3
        AND SUM(CASE WHEN direction='buy' THEN volume ELSE 0 END) > 0
        AND SUM(CASE WHEN direction='sell' THEN volume ELSE 0 END) > 0
        LIMIT 200
    """), {"bl": bonus_logins}).fetchall()

    # Find pairs with opposite net positions in same window
    windows: dict = {}
    for r in rows:
        key = (r[1], r[2])  # symbol, window
        if key not in windows:
            windows[key] = []
        windows[key].append(r)

    seen = set()
    for (symbol, window), accounts in windows.items():
        for i, a in enumerate(accounts):
            for b in accounts[i+1:]:
                if a[0] == b[0]: continue
                a_net = a[3] - a[4]  # buy - sell
                b_net = b[3] - b[4]
                if a_net * b_net >= 0: continue  # same direction = not a hedge
                ratio = min(abs(a_net), abs(b_net)) / max(abs(a_net), abs(b_net)) if max(abs(a_net), abs(b_net)) > 0 else 0
                if ratio < 0.60: continue  # too asymmetric
                key = tuple(sorted([a[0],b[0]])) + (symbol,window)
                if key in seen: continue
                seen.add(key)
                logins = [a[0], b[0]]
                ns = network_score_for_logins(db, logins)
                risk = min(int(70 + ns*0.15 + ratio*10), 100)
                conf = min(int(75 + ns*0.1), 95)
                deps = db.execute(text("SELECT COALESCE(SUM(total_deposits),0) FROM clients WHERE login=ANY(:l)"), {"l": logins}).scalar() or 0
                bonus = db.execute(text("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE login=ANY(:l) AND tx_type='bonus_deposit'"), {"l": logins}).scalar() or 0
                sev = 'critical' if risk>=80 else 'high' if risk>=70 else 'medium'
                ev = (f"BONUS HEDGE L2 (Split): #{a[0]} net {a_net:+.2f}L vs #{b[0]} net {b_net:+.2f}L "
                      f"on {symbol} in 60min window. {a[5]+b[5]} total trades split. "
                      f"Volume match ratio: {ratio:.0%}. Bonus at risk: ${float(bonus):,.0f}.")
                save_case(db,'bonus_hedge_l2',sev,logins,symbol,risk,conf,ns,ev,float(deps),float(bonus))


def detect_bonus_eer(db):
    """Layer 3: Equity Extraction Ratio - withdrew more than deposit+bonus."""
    rows = db.execute(text("""
        SELECT c.login, c.name, c.total_deposits, c.total_withdrawals,
               COALESCE(b.bonus_total,0) as bonus,
               c.total_withdrawals::float /
                 NULLIF(c.total_deposits + COALESCE(b.bonus_total,0), 0) as eer
        FROM clients c
        JOIN (
            SELECT login, SUM(amount) as bonus_total
            FROM transactions WHERE tx_type='bonus_deposit'
            GROUP BY login
        ) b ON b.login = c.login
        WHERE c.total_deposits > 50
        AND c.total_withdrawals > (c.total_deposits + COALESCE(b.bonus_total,0)) * 0.70
        ORDER BY eer DESC
        LIMIT 100
    """)).fetchall()

    for r in rows:
        eer = float(r[5] or 0)
        risk = int(min(50 + eer*35, 100))
        conf = int(min(55 + eer*25, 95))
        sev = 'critical' if eer>=1.0 else 'high' if eer>=0.85 else 'medium'
        ns = network_score_for_logins(db, [r[0]])
        ev = (f"BONUS EER: #{r[0]} ({r[1]}) deposited ${r[2]:,.0f} + ${r[4]:,.0f} bonus, "
              f"withdrew ${r[3]:,.0f} (EER={eer:.2f}x). "
              f"Withdrew {eer*100:.0f}% of deposit+bonus. Classic double-and-dash pattern.")
        save_case(db,'bonus_eer',sev,[r[0]],None,risk,conf,ns,ev,float(r[2]),float(r[3]))


def detect_bonus_farm(db):
    """Layer 4: Multi-account bonus farm - organized cluster all claiming bonuses."""
    rows = db.execute(text("""
        SELECT ai.identifier_value, ai.identifier_type,
               array_agg(DISTINCT ai.login) as logins,
               COUNT(DISTINCT ai.login) as acct_count
        FROM account_identifiers ai
        WHERE ai.identifier_type IN ('cid','ip')
        AND ai.identifier_value != '0' AND ai.identifier_value != ''
        AND ai.login IN (
            SELECT DISTINCT login FROM transactions WHERE tx_type='bonus_deposit'
        )
        GROUP BY ai.identifier_value, ai.identifier_type
        HAVING COUNT(DISTINCT ai.login) >= 3
        ORDER BY acct_count DESC
        LIMIT 50
    """)).fetchall()

    for r in rows:
        logins = list(r[2])[:10]
        count = r[3]
        ns = network_score_for_logins(db, logins)
        bonus = db.execute(text("""
            SELECT COALESCE(SUM(amount),0) FROM transactions
            WHERE login=ANY(:l) AND tx_type='bonus_deposit'
        """), {"l": logins}).scalar() or 0
        if float(bonus) < 50: continue
        risk = min(int(75 + count*5 + ns*0.1), 100)
        conf = min(int(80 + count*3), 99)
        sev = 'critical' if risk>=80 else 'high'
        deps = db.execute(text("SELECT COALESCE(SUM(total_deposits),0) FROM clients WHERE login=ANY(:l)"), {"l": logins}).scalar() or 0
        ev = (f"BONUS FARM: {count} accounts share {r[1].upper()} {r[0][:16]}..., "
              f"all with bonus deposits. Total bonus claimed: ${float(bonus):,.0f}. "
              f"Logins: {logins[:5]}. Organized multi-account bonus farming.")
        save_case(db,'bonus_farm','critical',logins,None,risk,conf,ns,ev,float(deps),float(bonus))


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM 2 — SWAP ARBITRAGE ABUSE
# ══════════════════════════════════════════════════════════════════════════════

def is_swap_free_account(db, login: int) -> bool:
    row = db.execute(text("""
        SELECT group_name FROM clients WHERE login=:l
    """), {"l": login}).fetchone()
    if not row: return False
    g = row[0] or ''
    return any(sf.lower() in g.lower() for sf in SWAP_FREE_GROUPS)


def detect_swap_profitable_hold(db):
    """Profitable position on high-carry symbol held > 24h without closing."""
    vector_conditions = " OR ".join([
        f"(symbol='{sym}' AND direction='{direction}')"
        for sym, direction in SWAP_FREE_VECTOR.items()
    ])

    rows = db.execute(text(f"""
        SELECT login, symbol, direction,
               volume/10000.0 as lots,
               price,
               deal_time,
               EXTRACT(EPOCH FROM NOW())::bigint - deal_time as held_seconds
        FROM deals
        WHERE deal_type='trade' AND entry=0
        AND ({vector_conditions})
        AND deal_time < EXTRACT(EPOCH FROM NOW())::bigint - 86400
        AND login IN (
            SELECT login FROM clients
            WHERE {' OR '.join([f"group_name ILIKE '%{sf}%'" for sf in SWAP_FREE_GROUPS])}
        )
        ORDER BY held_seconds DESC
        LIMIT 100
    """)).fetchall()

    for r in rows:
        login = r[0]
        held_hours = float(r[6]) / 3600
        risk = int(min(35 + held_hours/24*20, 100))
        conf = int(min(50 + held_hours/24*15, 90))
        sev = 'critical' if held_hours>=72 else 'high' if held_hours>=48 else 'medium'
        ns = network_score_for_logins(db, [login])
        deps = db.execute(text("SELECT COALESCE(total_deposits,0) FROM clients WHERE login=:l"), {"l": login}).scalar() or 0
        ev = (f"SWAP ABUSE: #{login} holds {r[2].upper()} {r[1]} {r[3]:.2f}L "
              f"for {held_hours:.1f} hours on swap-free account. "
              f"Normal traders close profitable positions within hours. "
              f"This account is farming swap from another broker.")
        save_case(db,'swap_profitable_hold',sev,[login],r[1],risk,conf,ns,ev,float(deps),0)


def detect_swap_consecutive_overnight(db):
    """Same high-carry symbol crossing midnight 3+ consecutive nights."""
    vector_symbols = list(SWAP_FREE_VECTOR.keys())

    rows = db.execute(text("""
        SELECT login, symbol,
               COUNT(DISTINCT DATE(TO_TIMESTAMP(deal_time))) as unique_days
        FROM deals
        WHERE deal_type='trade' AND entry=0
        AND symbol=ANY(:syms)
        AND login IN (
            SELECT login FROM clients
            WHERE group_name ILIKE '%IS%'
            OR group_name ILIKE '%islamic%'
            OR group_name ILIKE '%swap%'
        )
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
        GROUP BY login, symbol
        HAVING COUNT(DISTINCT DATE(TO_TIMESTAMP(deal_time))) >= 3
        ORDER BY unique_days DESC
        LIMIT 100
    """), {"syms": vector_symbols}).fetchall()

    for r in rows:
        login, symbol, nights = r[0], r[1], r[2]
        risk = min(int(50 + nights*8), 95)
        conf = min(int(55 + nights*5), 90)
        sev = 'critical' if nights>=5 else 'high' if nights>=3 else 'medium'
        ns = network_score_for_logins(db, [login])
        deps = db.execute(text("SELECT COALESCE(total_deposits,0) FROM clients WHERE login=:l"), {"l": login}).scalar() or 0
        ev = (f"SWAP OVERNIGHT: #{login} held {symbol} overnight for {nights} consecutive nights "
              f"on swap-free account. 3+ nights = confirmed swap farming pattern. "
              f"Not holding due to market view — collecting carry at another broker.")
        save_case(db,'swap_consecutive_overnight',sev,[login],symbol,risk,conf,ns,ev,float(deps),0)


def detect_swap_symbol_exclusivity(db):
    """Account ONLY trades high-carry symbols - swap farming signature."""
    vector_symbols = list(SWAP_FREE_VECTOR.keys())

    rows = db.execute(text("""
        SELECT login,
               COUNT(DISTINCT symbol) as total_symbols,
               SUM(CASE WHEN symbol=ANY(:syms) THEN 1 ELSE 0 END)::float /
                 COUNT(*) as carry_ratio,
               COUNT(*) as total_trades
        FROM deals
        WHERE deal_type='trade' AND entry=0
        AND login IN (
            SELECT login FROM clients
            WHERE group_name ILIKE '%IS%'
            OR group_name ILIKE '%islamic%'
        )
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
        GROUP BY login
        HAVING COUNT(*) >= 5
        AND SUM(CASE WHEN symbol=ANY(:syms) THEN 1 ELSE 0 END)::float / COUNT(*) >= 0.85
        ORDER BY carry_ratio DESC
        LIMIT 100
    """), {"syms": vector_symbols}).fetchall()

    for r in rows:
        login = r[0]
        carry_ratio = float(r[2] or 0)
        risk = int(min(40 + carry_ratio*40, 90))
        conf = int(min(45 + carry_ratio*35, 85))
        sev = 'high' if carry_ratio>=0.95 else 'medium'
        ns = network_score_for_logins(db, [login])
        deps = db.execute(text("SELECT COALESCE(total_deposits,0) FROM clients WHERE login=:l"), {"l": login}).scalar() or 0
        ev = (f"SWAP EXCLUSIVITY: #{login} trades {carry_ratio*100:.0f}% on high-carry symbols only "
              f"({r[3]} trades, {r[1]} unique symbols). Swap-free account exclusively "
              f"trading assets that pay positive swap at other brokers. "
              f"Real traders diversify across symbols.")
        save_case(db,'swap_symbol_exclusivity',sev,[login],None,risk,conf,ns,ev,float(deps),0)


def detect_swap_farm_network(db):
    """Multiple swap-free accounts in network all holding carry positions."""
    vector_symbols = list(SWAP_FREE_VECTOR.keys())

    rows = db.execute(text("""
        SELECT ai.identifier_value, ai.identifier_type,
               array_agg(DISTINCT d.login) as logins,
               COUNT(DISTINCT d.login) as count
        FROM account_identifiers ai
        JOIN deals d ON d.login = ai.login
        WHERE ai.identifier_type IN ('cid','ip')
        AND ai.identifier_value != '0'
        AND d.symbol=ANY(:syms)
        AND d.deal_type='trade' AND d.entry=0
        AND d.login IN (
            SELECT login FROM clients
            WHERE group_name ILIKE '%IS%' OR group_name ILIKE '%islamic%'
        )
        AND d.deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
        GROUP BY ai.identifier_value, ai.identifier_type
        HAVING COUNT(DISTINCT d.login) >= 2
        LIMIT 50
    """), {"syms": vector_symbols}).fetchall()

    for r in rows:
        logins = list(r[2])[:10]
        count = r[3]
        ns = network_score_for_logins(db, logins)
        risk = min(int(70 + count*8 + ns*0.1), 100)
        conf = min(int(75 + count*5), 99)
        sev = 'critical' if risk>=80 else 'high'
        deps = db.execute(text("SELECT COALESCE(SUM(total_deposits),0) FROM clients WHERE login=ANY(:l)"), {"l": logins}).scalar() or 0
        ev = (f"SWAP FARM: {count} swap-free accounts share {r[1].upper()} {r[0][:16]}..., "
              f"all holding high-carry positions. Coordinated swap farming operation. "
              f"Logins: {logins[:5]}. Network score: {ns}/100.")
        save_case(db,'swap_coordinated_farm','critical',logins,None,risk,conf,ns,ev,float(deps),0)


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM 3 — TOXIC FLOW
# ══════════════════════════════════════════════════════════════════════════════

def detect_night_latency_arb(db):
    """Night Latency Arb: exotic/rare symbols 03:00-05:00 GMT, fast profitable trades."""
    # Build symbol filter for MXN, TRY, ZAR, PLN containing symbols
    night_symbol_conditions = " OR ".join([
        f"symbol ILIKE '%{c}%'" for c in NIGHT_EXOTIC_CONTAINS
    ])

    rows = db.execute(text(f"""
        SELECT login, symbol,
               COUNT(*) as trades,
               SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)::float/COUNT(*) as win_rate,
               SUM(profit) as total_profit
        FROM deals
        WHERE deal_type='trade' AND entry=1
        AND (deal_time % 86400) BETWEEN :ns AND :ne
        AND ({night_symbol_conditions})
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*90
        GROUP BY login, symbol
        HAVING COUNT(*) >= 3
        AND SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)::float/COUNT(*) >= 0.70
        ORDER BY win_rate DESC
        LIMIT 100
    """), {"ns": NIGHT_START, "ne": NIGHT_END}).fetchall()

    for r in rows:
        login, symbol = r[0], r[1]
        win_rate = float(r[3] or 0)
        trades = r[2]
        profit = float(r[4] or 0)
        risk = int(min(55 + win_rate*35 + min(trades,10)*1, 100))
        conf = int(min(55 + win_rate*30, 95))
        sev = 'critical' if risk>=80 else 'high' if risk>=65 else 'medium'
        ns = network_score_for_logins(db, [login])
        deps = db.execute(text("SELECT COALESCE(total_deposits,0) FROM clients WHERE login=:l"), {"l": login}).scalar() or 0
        ev = (f"NIGHT LATENCY ARB: #{login} traded {symbol} during 03:00-05:00 GMT rollover window "
              f"with {win_rate*100:.0f}% win rate over {trades} trades. "
              f"Total profit: ${profit:.2f}. Exotic symbols at NY close have stale prices. "
              f"Abuser exploits feed lag with faster institutional data source.")
        save_case(db,'night_latency_arb',sev,[login],symbol,risk,conf,ns,ev,float(deps),profit)


def detect_night_exotic_concentration(db):
    """Account concentrates 50%+ of all trades in night exotic window."""
    night_symbol_conditions = " OR ".join([
        f"symbol ILIKE '%{c}%'" for c in NIGHT_EXOTIC_CONTAINS
    ])

    rows = db.execute(text(f"""
        SELECT login,
               COUNT(*) FILTER (
                   WHERE (deal_time % 86400) BETWEEN :ns AND :ne
                   AND ({night_symbol_conditions})
               )::float / NULLIF(COUNT(*), 0) as night_exotic_ratio,
               COUNT(*) as total_trades,
               SUM(profit) FILTER (
                   WHERE (deal_time % 86400) BETWEEN :ns AND :ne
                   AND ({night_symbol_conditions})
               ) as night_profit
        FROM deals
        WHERE deal_type='trade' AND entry=1
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*90
        GROUP BY login
        HAVING COUNT(*) >= 5
        AND COUNT(*) FILTER (
            WHERE (deal_time % 86400) BETWEEN :ns AND :ne
            AND ({night_symbol_conditions})
        )::float / NULLIF(COUNT(*), 0) >= 0.50
        ORDER BY night_exotic_ratio DESC
        LIMIT 100
    """), {"ns": NIGHT_START, "ne": NIGHT_END}).fetchall()

    for r in rows:
        login = r[0]
        ratio = float(r[1] or 0)
        profit = float(r[3] or 0)
        risk = int(min(45 + ratio*45, 95))
        conf = int(min(50 + ratio*35, 90))
        sev = 'critical' if ratio>=0.80 else 'high' if ratio>=0.60 else 'medium'
        ns = network_score_for_logins(db, [login])
        deps = db.execute(text("SELECT COALESCE(total_deposits,0) FROM clients WHERE login=:l"), {"l": login}).scalar() or 0
        ev = (f"NIGHT CONCENTRATION: #{login} places {ratio*100:.0f}% of all trades "
              f"in night exotic window (03:00-05:00 GMT on rare symbols). "
              f"Night exotic profit: ${profit:.2f}. "
              f"Account exists primarily to exploit rollover pricing gaps.")
        save_case(db,'night_exotic_concentration',sev,[login],None,risk,conf,ns,ev,float(deps),profit)


def detect_toxic_latency_arb(db):
    """General latency arb: high win rate on ultra-short trades any time."""
    rows = db.execute(text("""
        SELECT a.login, a.symbol,
               COUNT(*) as trades,
               SUM(CASE WHEN a.profit>0 THEN 1 ELSE 0 END)::float/COUNT(*) as win_rate,
               SUM(a.profit) as total_profit,
               COUNT(DISTINCT a.volume) as unique_volumes,
               COUNT(*) as total_for_uniformity
        FROM deals a
        JOIN deals b ON b.login=a.login
            AND b.symbol=a.symbol
            AND b.entry=1
            AND b.deal_time > a.deal_time
            AND b.deal_time - a.deal_time <= 60
        WHERE a.deal_type='trade' AND a.entry=0
        AND a.deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
        GROUP BY a.login, a.symbol
        HAVING COUNT(*) >= 20
        AND SUM(CASE WHEN a.profit>0 THEN 1 ELSE 0 END)::float/COUNT(*) >= 0.75
        ORDER BY win_rate DESC
        LIMIT 50
    """)).fetchall()

    for r in rows:
        login, symbol = r[0], r[1]
        win_rate = float(r[3] or 0)
        trades = r[2]
        profit = float(r[4] or 0)
        lot_uniformity = r[5] / r[6] if r[6] > 0 else 1
        risk = int(min(55 + win_rate*30 + (1-lot_uniformity)*10, 100))
        conf = int(min(60 + win_rate*25, 95))
        sev = 'critical' if risk>=80 else 'high' if risk>=65 else 'medium'
        ns = network_score_for_logins(db, [login])
        deps = db.execute(text("SELECT COALESCE(total_deposits,0) FROM clients WHERE login=:l"), {"l": login}).scalar() or 0
        ev = (f"LATENCY ARB: #{login} on {symbol}: {win_rate*100:.0f}% win rate "
              f"over {trades} ultra-short trades (<60s). "
              f"Lot uniformity: {lot_uniformity:.0%} (bot signature if <10%). "
              f"Total profit: ${profit:.2f}. Exploiting broker feed delay.")
        save_case(db,'toxic_latency_arb',sev,[login],symbol,risk,conf,ns,ev,float(deps),profit)


def detect_midnight_exotic(db):
    """Midnight exotic arb: high win rate 00:00-02:00 UTC on exotic symbols."""
    rows = db.execute(text("""
        SELECT login, symbol,
               COUNT(*) as trades,
               SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)::float/COUNT(*) as win_rate,
               SUM(profit) as total_profit
        FROM deals
        WHERE deal_type='trade' AND entry=1
        AND (deal_time % 86400) BETWEEN :ms AND :me
        AND symbol=ANY(:syms)
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*90
        GROUP BY login, symbol
        HAVING COUNT(*) >= 5
        AND SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)::float/COUNT(*) >= 0.70
        ORDER BY win_rate DESC
        LIMIT 100
    """), {"ms": MIDNIGHT_START, "me": MIDNIGHT_END, "syms": EXOTIC_SYMBOLS}).fetchall()

    seen = set()
    for r in rows:
        login, symbol = r[0], r[1]
        win_rate = float(r[3] or 0)
        profit = float(r[4] or 0)

        # Check for hedge partner
        partners = db.execute(text("""
            SELECT DISTINCT b.login
            FROM deals a
            JOIN deals b ON a.symbol=b.symbol
                AND a.login != b.login
                AND a.direction != b.direction
                AND a.entry=0 AND b.entry=0
                AND ABS(a.deal_time - b.deal_time) <= 300
                AND (a.deal_time % 86400) BETWEEN :ms AND :me
            WHERE a.login=:l AND a.symbol=:s
            LIMIT 5
        """), {"l": login, "s": symbol, "ms": MIDNIGHT_START, "me": MIDNIGHT_END}).fetchall()

        logins = [login] + [p[0] for p in partners]
        key = tuple(sorted(logins)) + (symbol,)
        if key in seen: continue
        seen.add(key)

        ns = network_score_for_logins(db, logins)
        abuse_type = 'midnight_exotic_hedge' if len(logins)>1 else 'midnight_exotic_arb'
        risk = int(min(55 + win_rate*30 + (15 if len(logins)>1 else 0) + ns*0.1, 100))
        conf = int(min(60 + win_rate*25 + ns*0.1, 98))
        sev = 'critical' if risk>=80 else 'high' if risk>=65 else 'medium'
        deps = db.execute(text("SELECT COALESCE(SUM(total_deposits),0) FROM clients WHERE login=ANY(:l)"), {"l": logins}).scalar() or 0
        hedge_note = f" Partner accounts: {[p[0] for p in partners]}." if partners else ""
        ev = (f"MIDNIGHT EXOTIC: #{login} on {symbol}: {win_rate*100:.0f}% win rate "
              f"during 00:00-02:00 UTC ({r[2]} trades). Thin liquidity = stale prices. "
              f"Total profit: ${profit:.2f}.{hedge_note}")
        save_case(db, abuse_type, sev, logins, symbol, risk, conf, ns, ev, float(deps), profit)


# ══════════════════════════════════════════════════════════════════════════════
# OTHER DETECTORS (existing)
# ══════════════════════════════════════════════════════════════════════════════

def detect_device_cluster(db):
    rows = db.execute(text("""
        SELECT identifier_value, array_agg(DISTINCT login) as logins,
               COUNT(DISTINCT login) as count
        FROM account_identifiers
        WHERE identifier_type='cid' AND identifier_value != '0' AND identifier_value != ''
        GROUP BY identifier_value HAVING COUNT(DISTINCT login) >= 2
        ORDER BY count DESC LIMIT 100
    """)).fetchall()
    for r in rows:
        logins = list(r[1])[:10]; count = r[2]
        ns = network_score_for_logins(db, logins)
        risk = min(int(60 + count*10 + ns*0.2), 100)
        conf = min(int(70 + count*5), 99)
        sev = 'critical' if risk>=80 else 'high' if risk>=70 else 'medium'
        deps = db.execute(text("SELECT COALESCE(SUM(total_deposits),0) FROM clients WHERE login=ANY(:l)"), {"l": logins}).scalar() or 0
        ev = f"{count} accounts share device CID {r[0][:16]}... Logins: {logins}"
        save_case(db,'device_cluster',sev,logins,None,int(risk),int(conf),ns,ev,float(deps),0)


def detect_cpa_fraud(db):
    rows = db.execute(text("""
        SELECT c.login, c.name, c.total_deposits, c.total_withdrawals,
               c.total_withdrawals::float/NULLIF(c.total_deposits,0) as ratio
        FROM clients c
        WHERE c.total_deposits >= 50
        AND c.total_withdrawals >= c.total_deposits * 0.70
        ORDER BY ratio DESC LIMIT 100
    """)).fetchall()
    for r in rows:
        ratio = float(r[4] or 0)
        risk = int(min(50 + ratio*30, 95)); conf = int(min(50 + ratio*25, 90))
        sev = 'critical' if risk>=80 else 'high' if risk>=70 else 'medium'
        ns = network_score_for_logins(db, [r[0]])
        deps = float(r[2] or 0)
        ev = f"CPA Fraud: #{r[0]} deposited ${r[2]:,.0f} withdrew ${r[3]:,.0f} ({ratio*100:.0f}%)"
        save_case(db,'cpa_fraud',sev,[r[0]],None,risk,conf,ns,ev,deps,float(r[3]))


def detect_round_trip(db):
    rows = db.execute(text("""
        SELECT c.login, c.name, c.total_deposits, c.total_withdrawals
        FROM clients c
        WHERE c.total_deposits >= 100
        AND c.total_withdrawals >= c.total_deposits * 0.85
        ORDER BY c.total_deposits DESC LIMIT 50
    """)).fetchall()
    for r in rows:
        risk = 80; conf = 85; sev = 'critical'
        ns = network_score_for_logins(db, [r[0]])
        ev = f"Round trip: #{r[0]} dep=${r[2]:,.0f} with=${r[3]:,.0f} ({r[3]/r[2]*100:.0f}%)"
        save_case(db,'round_trip',sev,[r[0]],None,risk,conf,ns,ev,float(r[2]),float(r[3]))


# ══════════════════════════════════════════════════════════════════════════════
# AUTO ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

def apply_auto_actions(db: Session):
    critical = db.execute(text("""
        SELECT id, all_logins FROM abuse_cases
        WHERE severity='critical' AND status='open' AND auto_action_taken=FALSE
    """)).fetchall()
    for row in critical:
        try:
            logins = json.loads(row[1]) if row[1] else []
            for login in logins:
                db.execute(text("UPDATE clients SET is_flagged=TRUE, flag_reason='abuse_critical' WHERE login=:l"), {"l": login})
                db.execute(text("UPDATE trading_accounts SET is_active=FALSE WHERE login=:l"), {"l": login})
        except: pass
    db.execute(text("""
        UPDATE abuse_cases SET auto_action_taken=TRUE, auto_action='freeze', status='frozen'
        WHERE severity='critical' AND status='open'
    """))
    db.execute(text("""
        UPDATE abuse_cases SET auto_action_taken=TRUE, auto_action='hold_wd', status='hold_wd'
        WHERE severity IN ('high','medium') AND status='open' AND auto_action_taken=FALSE
    """))
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_all_detectors(db: Session):
    """Run the advanced, data-grounded abuse engine (bonus / swap / toxic).
    See abuse_engine.py — six focused detectors, each scored 0-100 with clear
    evidence, tuned against the live data distribution. Creates the abuse_cases
    table and populates is_islamic on first run.
    """
    from abuse_engine import run_engine
    return run_engine(db)


# ══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats")
def get_abuse_stats(
    system: str = Query(""),
    abuse_type: str = Query(""),
    severity: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where_parts = []
    params: dict = {}
    if system == "bonus":
        where_parts.append("abuse_type ILIKE 'bonus%'")
    elif system == "swap":
        where_parts.append("abuse_type ILIKE 'swap%'")
    elif system == "toxic":
        where_parts.append("abuse_type ILIKE 'toxic%'")
    if abuse_type:
        where_parts.append("abuse_type = :abuse_type")
        params["abuse_type"] = abuse_type
    if severity:
        where_parts.append("severity = :severity")
        params["severity"] = severity
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    row = db.execute(text(f"""
        SELECT COUNT(*) as total,
            COUNT(*) FILTER (WHERE severity='critical') as critical,
            COUNT(*) FILTER (WHERE severity='high') as high,
            COUNT(*) FILTER (WHERE severity='medium') as medium,
            COUNT(*) FILTER (WHERE status='open') as pending,
            COUNT(*) FILTER (WHERE status='frozen') as frozen,
            COUNT(*) FILTER (WHERE status='resolved') as resolved,
            COUNT(*) FILTER (WHERE status='hold_wd') as hold_wd,
            COUNT(*) FILTER (WHERE abuse_type ILIKE 'bonus%') as bonus_cases,
            COUNT(*) FILTER (WHERE abuse_type ILIKE 'swap%') as swap_cases,
            COUNT(*) FILTER (WHERE abuse_type ILIKE 'toxic%') as toxic_cases
        FROM abuse_cases {where}
    """), params).fetchone()
    if not row:
        return {"total":0,"critical":0,"high":0,"medium":0,"pending":0,"frozen":0,"resolved":0,"hold_wd":0,"bonus_cases":0,"swap_cases":0,"toxic_cases":0}
    return {"total":row[0],"critical":row[1],"high":row[2],"medium":row[3],"pending":row[4],"frozen":row[5],"resolved":row[6],"hold_wd":row[7],"bonus_cases":row[8],"swap_cases":row[9],"toxic_cases":row[10]}


@router.get("/type-counts")
def get_type_counts(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Per-detector counts for the investigation-UI filter chips."""
    rows = db.execute(text("""
        SELECT abuse_type, COUNT(*) AS total,
               COUNT(*) FILTER (WHERE severity='critical') AS critical,
               COUNT(*) FILTER (WHERE COALESCE(hot,FALSE)) AS hot,
               COALESCE(SUM(exposure),0) AS exposure
        FROM abuse_cases WHERE status NOT IN ('resolved')
        GROUP BY abuse_type ORDER BY total DESC
    """)).fetchall()
    return {
        "types": [{"abuse_type": r[0], "total": r[1], "critical": r[2], "hot": r[3],
                   "exposure": float(r[4] or 0)} for r in rows],
        "total": sum(r[1] for r in rows),
        "critical": sum(r[2] for r in rows),
        "hot": sum(r[3] for r in rows),
        "exposure": float(sum((r[4] or 0) for r in rows)),
    }


@router.post("/flags")
def abuse_flags(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Given a list of logins, return which are involved in an open abuse case
    (worst case per login). Used to overlay abuse badges on Transactions / Clients /
    IB pages without rewriting their queries."""
    logins = [int(x) for x in (data.get("logins") or []) if str(x).lstrip('-').isdigit()]
    if not logins or not db.execute(text("SELECT to_regclass('public.abuse_account_flags')")).scalar():
        return {"flags": {}}
    rows = db.execute(text("""
        SELECT login, case_id, abuse_type, severity, hot, n_cases
        FROM abuse_account_flags WHERE login = ANY(:l)
    """), {"l": logins}).fetchall()
    return {"flags": {str(r[0]): {"case_id": r[1], "abuse_type": r[2], "severity": r[3],
                                  "hot": bool(r[4]), "n_cases": r[5]} for r in rows}}


@router.get("/cases")
def get_abuse_cases(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    severity: str = Query(""), abuse_type: str = Query(""),
    status: str = Query(""), search: str = Query(""),
    system: str = Query(""), hot: str = Query(""), login: int = Query(0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where = ["1=1"]
    params: dict = {"limit": page_size, "offset": (page-1)*page_size}

    if severity: where.append("a.severity=:sev"); params["sev"] = severity
    if abuse_type: where.append("a.abuse_type=:at"); params["at"] = abuse_type
    if hot in ("1", "true", "yes"): where.append("a.hot=TRUE")
    if login:
        # every case this account is involved in (winner, loser, or ring member)
        where.append("(a.login_a=:lg OR a.login_b=:lg OR ','||a.all_logins||',' LIKE :lgpat)")
        params["lg"] = login; params["lgpat"] = f"%,{login},%"
    if status: where.append("a.status=:st"); params["st"] = status
    if search:
        where.append("(CAST(a.login_a AS TEXT) LIKE :s OR CAST(a.login_b AS TEXT) LIKE :s OR a.symbol ILIKE :s OR a.abuse_type ILIKE :s)")
        params["s"] = f"%{search}%"
    if system == 'bonus':
        where.append("a.abuse_type ILIKE 'bonus%'")
    elif system == 'swap':
        where.append("a.abuse_type ILIKE 'swap%'")
    elif system == 'toxic':
        where.append("a.abuse_type ILIKE 'toxic%'")

    wc = " AND ".join(where)
    rows = db.execute(text(f"""
        SELECT a.id, a.abuse_type, a.severity, a.login_a, a.login_b, a.all_logins,
               a.symbol, a.risk_score, a.confidence, a.network_score,
               a.evidence, a.total_deposits, a.exposure, a.status,
               a.auto_action, a.created_at, a.updated_at,
               c.name as client_name, COALESCE(a.hot,FALSE) as hot, a.kpis
        FROM abuse_cases a
        LEFT JOIN clients c ON c.login=a.login_a
        WHERE {wc}
        ORDER BY COALESCE(a.hot,FALSE) DESC,
                 CASE a.severity WHEN 'critical' THEN 3 WHEN 'high' THEN 2 ELSE 1 END DESC,
                 a.exposure DESC NULLS LAST, a.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total_params = {k:v for k,v in params.items() if k not in ['limit','offset']}
    total = db.execute(text(f"SELECT COUNT(*) FROM abuse_cases a WHERE {wc}"), total_params).scalar() or 0

    return {
        "cases": [{
            "id":r[0],"abuse_type":r[1],"severity":r[2],
            "login_a":r[3],"login_b":r[4],
            "all_logins":parse_logins(r[5], r[3]),
            "symbol":r[6],"risk_score":r[7],"confidence":r[8],
            "network_score":r[9],"evidence":r[10],
            "total_deposits":float(r[11] or 0),"exposure":float(r[12] or 0),
            "status":r[13],"auto_action":r[14],
            "created_at":str(r[15]),"updated_at":str(r[16]),
            "client_name":r[17] or f"#{r[3]}",
            "hot":bool(r[18]),
            "kpis": json.loads(r[19]) if r[19] else [],
        } for r in rows],
        "total": total
    }


@router.get("/cases/{case_id}")
def get_case_detail(case_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    row = db.execute(text("SELECT * FROM abuse_cases WHERE id=:id"), {"id": case_id}).fetchone()
    if not row: return {"error": "Not found"}

    logins = parse_logins(row[5], row[3])

    # structured evidence (v3 engine) — the investigation UI renders this
    evidence_obj = None
    ej = db.execute(text("SELECT evidence_json FROM abuse_cases WHERE id=:id"), {"id": case_id}).scalar()
    if ej:
        try: evidence_obj = json.loads(ej)
        except Exception: evidence_obj = None

    abuse_type = row[1]
    symbol = row[6]

    # NOTE: clients has no is_islamic column (only trading_accounts does) — the
    # swap-free flag is filled from ta_map below.
    accounts = db.execute(text("""
        SELECT login, name, balance, equity, total_deposits, total_withdrawals,
               country, group_name, credit
        FROM clients WHERE login=ANY(:l)
    """), {"l": logins}).fetchall()
    # fall back to trading_accounts for credit/islamic if clients lacks it
    ta = db.execute(text("""
        SELECT login, COALESCE(credit,0), COALESCE(is_islamic,false), COALESCE(balance,0)
        FROM trading_accounts WHERE login=ANY(:l)
    """), {"l": logins}).fetchall()
    ta_map = {t[0]: t for t in ta}

    # ── Proof trades: pull the actual trades that triggered this case ──────────
    proof = []
    if abuse_type.startswith("bonus") or abuse_type.startswith("toxic"):
        # deals has no open_price (each row is one execution at `price`); show price.
        trows = db.execute(text("""
            SELECT login, symbol, direction, volume, price, profit,
                   swap, to_char(to_timestamp(deal_time),'YYYY-MM-DD HH24:MI') as t
            FROM deals
            WHERE login=ANY(:l) AND direction IN ('buy','sell')
            ORDER BY ABS(profit) DESC NULLS LAST
            LIMIT 40
        """), {"l": logins}).fetchall()
        proof = [{
            "login": r[0], "symbol": r[1], "direction": r[2], "volume": float(r[3] or 0),
            "open_price": 0, "close_price": float(r[4] or 0),
            "profit": float(r[5] or 0), "swap": float(r[6] or 0), "time": r[7]
        } for r in trows]
    elif abuse_type.startswith("swap"):
        # swap field is ~empty on this server, so show the closed positions
        # (the overnight holds) ordered by P&L instead.
        trows = db.execute(text("""
            SELECT login, symbol, direction, volume, price, profit, swap,
                   to_char(to_timestamp(deal_time),'YYYY-MM-DD HH24:MI') as t
            FROM deals
            WHERE login=ANY(:l) AND entry=1 AND direction IN ('buy','sell')
            ORDER BY ABS(profit) DESC NULLS LAST LIMIT 40
        """), {"l": logins}).fetchall()
        proof = [{
            "login": r[0], "symbol": r[1], "direction": r[2], "volume": float(r[3] or 0),
            "open_price": 0, "close_price": float(r[4] or 0),
            "profit": float(r[5] or 0), "swap": float(r[6] or 0), "time": r[7]
        } for r in trows]

    # ── Recommended action based on type + severity ───────────────────────────
    sev = row[2]
    rec = "Monitor"
    if sev == "critical":
        rec = "Freeze accounts & claw back bonus" if abuse_type.startswith("bonus") else "Freeze & review trades"
    elif sev == "high":
        rec = "Hold withdrawals & investigate"
    elif sev == "medium":
        rec = "Flag for monitoring"

    return {
        "id":row[0],"abuse_type":abuse_type,"severity":sev,
        "login_a":row[3],"login_b":row[4],"all_logins":logins,
        "symbol":symbol,"risk_score":row[7],"confidence":row[8],
        "network_score":row[9],"evidence":row[10],
        "total_deposits":float(row[11] or 0),"exposure":float(row[12] or 0),
        "status":row[13],"auto_action":row[14],
        "created_at":str(row[15]),"updated_at":str(row[16]),
        "recommendation": rec,
        "accounts":[{
            "login":a[0],"name":a[1],"balance":float(a[2] or 0),"equity":float(a[3] or 0),
            "total_deposits":float(a[4] or 0),"total_withdrawals":float(a[5] or 0),
            "country":a[6],"group":a[7],
            "credit": float(a[8] or 0) if len(a) > 8 and a[8] is not None else (float(ta_map[a[0]][1]) if a[0] in ta_map else 0),
            "is_islamic": bool(a[9]) if len(a) > 9 and a[9] is not None else (bool(ta_map[a[0]][2]) if a[0] in ta_map else False),
        } for a in accounts],
        "proof_trades": proof,
        "connections": _case_connections(db, logins) if len(logins) > 1 else [],
        "evidence_obj": evidence_obj,
    }


@router.get("/cases/{case_id}/network")
def get_case_network(case_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Relationship graph for a case — loaded lazily so the case file opens instantly."""
    row = db.execute(text("SELECT abuse_type, all_logins, login_a FROM abuse_cases WHERE id=:id"), {"id": case_id}).fetchone()
    if not row:
        return {"nodes": [], "edges": []}
    logins = parse_logins(row[1], row[2])
    return case_network(db, logins, row[0])


def case_network(db, logins, abuse_type):
    """Build a small relationship graph around the case accounts for the back-office
    team: nodes = accounts, edges = how they're linked (shared device / phone / IP /
    IB / family) plus the abuse link itself. 1 hop out, capped for readability."""
    logins = list(dict.fromkeys(int(x) for x in logins))
    case_set = set(logins)
    STRENGTH = {"cid": 5, "mqid": 5, "device": 5, "phone": 4, "agent": 3, "family": 3, "ip": 2, "abuse": 6}
    edges: dict = {}

    def add(a, b, reason, value):
        if a == b:
            return
        k = (min(a, b), max(a, b))
        st = STRENGTH.get(reason, 1)
        if k not in edges or st > edges[k]["strength"]:
            edges[k] = {"reason": reason, "value": value or "", "strength": st}

    nodes = set(logins)

    # shared device / IP tokens (exact type+value match), 1 hop to neighbours
    for typ, val, members in db.execute(text("""
        SELECT identifier_type, identifier_value, array_agg(DISTINCT login) AS m
        FROM account_identifiers
        WHERE (identifier_type, identifier_value) IN (
            SELECT identifier_type, identifier_value FROM account_identifiers
            WHERE login = ANY(:l) AND identifier_type IN ('cid','mqid','ip')
              AND identifier_value NOT IN ('0','')
        ) AND identifier_type IN ('cid','mqid','ip')
        GROUP BY identifier_type, identifier_value
        HAVING COUNT(DISTINCT login) > 1
        LIMIT 80
    """), {"l": logins}).fetchall():
        members = sorted(set(members))
        anchor = next((m for m in members if m in case_set), members[0])
        for m in members:
            if len(nodes) < 28 or m in nodes:
                add(anchor, m, typ, val); nodes.add(m)

    # shared phone number
    for phone, members in db.execute(text("""
        SELECT phone, array_agg(DISTINCT login) AS m FROM clients
        WHERE phone IN (SELECT phone FROM clients WHERE login=ANY(:l) AND length(trim(phone)) >= 6)
        GROUP BY phone HAVING COUNT(DISTINCT login) > 1 LIMIT 30
    """), {"l": logins}).fetchall():
        members = sorted(set(members))
        anchor = next((m for m in members if m in case_set), members[0])
        for m in members:
            if len(nodes) < 28 or m in nodes:
                add(anchor, m, "phone", phone); nodes.add(m)

    # family / same-IB links (already-derived network_edges)
    for a, b, reason, val in db.execute(text("""
        SELECT login_a, login_b, reason, value FROM network_edges
        WHERE (login_a = ANY(:l) OR login_b = ANY(:l)) AND reason IN ('family','ib')
        LIMIT 40
    """), {"l": logins}).fetchall():
        if a in nodes or b in nodes:
            add(a, b, "agent" if reason == "ib" else "family", val); nodes.add(a); nodes.add(b)

    # the abuse relationship itself (winner <-> loser / ring members)
    for i in range(min(len(logins), 6)):
        for j in range(i + 1, min(len(logins), 6)):
            add(logins[i], logins[j], "abuse", abuse_type)

    # assemble nodes: ALWAYS keep the case accounts, then the neighbours most
    # strongly tied to them (so the graph never drops the accounts under review).
    deg: dict = {}; tie: dict = {}
    for (a, b), v in edges.items():
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
        if a in case_set: tie[b] = max(tie.get(b, 0), v["strength"])
        if b in case_set: tie[a] = max(tie.get(a, 0), v["strength"])
    neighbours = sorted([n for n in (set(deg) | nodes) if n not in case_set],
                        key=lambda n: (tie.get(n, 0), deg.get(n, 0)), reverse=True)
    keep = (list(logins) + neighbours)[:26]
    nset = set(keep)
    meta = {m[0]: (m[1], m[2]) for m in db.execute(text(
        "SELECT login, name, country FROM clients WHERE login=ANY(:n)"), {"n": keep}).fetchall()}
    node_objs = [{"login": n, "name": (meta.get(n, ('', ''))[0] or ''),
                  "country": (meta.get(n, ('', ''))[1] or ''), "is_case": n in case_set}
                 for n in keep]
    edge_objs = [{"a": a, "b": b, "reason": v["reason"], "value": v["value"]}
                 for (a, b), v in edges.items() if a in nset and b in nset]
    return {"nodes": node_objs, "edges": edge_objs}


def _case_connections(db, logins):
    """Return the network links between the accounts in this case (shared IP/CID/etc)."""
    rows = db.execute(text("""
        SELECT login_a, login_b, reason, value FROM network_edges
        WHERE login_a = ANY(:l) AND login_b = ANY(:l)
        ORDER BY CASE reason WHEN 'cid' THEN 1 WHEN 'ip' THEN 2 WHEN 'mqid' THEN 3
                              WHEN 'family' THEN 4 ELSE 5 END
        LIMIT 100
    """), {"l": logins}).fetchall()
    seen = set(); out = []
    for a, b, reason, value in rows:
        key = (min(a, b), max(a, b), reason)
        if key in seen:
            continue
        seen.add(key)
        out.append({"login_a": a, "login_b": b, "reason": reason, "value": value or ""})

    # Fallback: the abuse engine links accounts via account_identifiers (shared
    # cid/ip), which may not be in network_edges. Derive those links directly so
    # the "how they're connected" panel is populated for farm/cluster cases.
    if not out:
        ids = db.execute(text("""
            SELECT identifier_type, identifier_value, array_agg(DISTINCT login) AS logins
            FROM account_identifiers
            WHERE login = ANY(:l) AND identifier_type IN ('cid','ip','mqid')
              AND identifier_value NOT IN ('0','')
            GROUP BY identifier_type, identifier_value
            HAVING COUNT(DISTINCT login) > 1
        """), {"l": logins}).fetchall()
        for reason, value, lg in ids:
            lg = sorted(set(lg))
            for i in range(len(lg)):
                for j in range(i + 1, len(lg)):
                    key = (lg[i], lg[j], reason)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"login_a": lg[i], "login_b": lg[j],
                                "reason": reason, "value": value or ""})
    return out


@router.post("/cases/{case_id}/action")
def take_action(case_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    action = data.get("action")
    status_map = {"freeze":"frozen","hold_wd":"hold_wd","resolve":"resolved","clear":"resolved","review":"reviewing"}
    new_status = status_map.get(action, "reviewing")
    db.execute(text("UPDATE abuse_cases SET status=:s, updated_at=NOW() WHERE id=:id"), {"s":new_status,"id":case_id})
    if action == "freeze":
        row = db.execute(text("SELECT all_logins, login_a FROM abuse_cases WHERE id=:id"), {"id":case_id}).fetchone()
        logins = parse_logins(row[0], row[1]) if row else []
        for login in logins:
            db.execute(text("UPDATE clients SET is_flagged=TRUE, flag_reason='abuse_freeze' WHERE login=:l"), {"l":login})
            db.execute(text("UPDATE trading_accounts SET is_active=FALSE WHERE login=:l"), {"l":login})
    db.commit()
    return {"message": f"Action '{action}' applied", "status": new_status}


@router.post("/run-detection")
def run_detection(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    def task():
        from database import SessionLocal
        _db = SessionLocal()
        try:
            # NOTE: deliberately does NOT auto-freeze/disable accounts. On this LIVE
            # system the desk reviews each case and freezes manually from the UI.
            run_all_detectors(_db)
        finally:
            _db.close()
    background_tasks.add_task(task)
    return {"message": "Detection started in background"}
