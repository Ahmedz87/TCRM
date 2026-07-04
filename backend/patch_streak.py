p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()

# Change 1: remove the eligibility filter that skips non-FX/Gold trades for streak
old1 = """    by_client = defaultdict(list)
    for client_id, login, symbol, volume, deal_time in rows:
        if not is_eligible(symbol):
            continue
        # MT5 volume is stored in units where 1.00 standard lot = 10,000
        # (the minimum 0.01 lot = volume 100). So lots = volume / 10,000.
        by_client[client_id].append((deal_time, symbol, float(volume or 0)/10000.0))"""
new1 = """    by_client = defaultdict(list)
    for client_id, login, symbol, volume, deal_time in rows:
        # MT5 volume: 1.00 standard lot = 10,000 (min 0.01 lot = volume 100)
        lots = float(volume or 0) / 10000.0
        eligible = is_eligible(symbol)   # only FX + Gold earn POINTS
        by_client[client_id].append((deal_time, symbol, lots, eligible))"""

# Change 2: unpack eligible in the loop, and only award points if eligible
old2 = """        for deal_time, symbol, lots in trades:"""
new2 = """        for deal_time, symbol, lots, eligible in trades:"""

old3 = """            pts = lots * _tier_rate(tier)
            balance += pts
            lifetime += pts
            ledger_rows.append((client_id, 'trade', pts, lots, tier, symbol, tdate))"""
new3 = """            if eligible:
                pts = lots * _tier_rate(tier)
                balance += pts
                lifetime += pts
                ledger_rows.append((client_id, 'trade', pts, lots, tier, symbol, tdate))"""

c = []
if old1 in s: s = s.replace(old1, new1); c.append("load-filter")
if old2 in s: s = s.replace(old2, new2); c.append("loop-unpack")
if old3 in s: s = s.replace(old3, new3); c.append("points-gate")
open(p, "w", encoding="utf-8").write(s)

import py_compile
try:
    py_compile.compile(p, doraise=True)
    print("Patched:", c, "- compiles OK")
except py_compile.PyCompileError as e:
    print("Patched:", c, "but COMPILE ERROR:", e)
