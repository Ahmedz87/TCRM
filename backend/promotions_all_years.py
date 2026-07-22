"""
Detect IB level PROMOTIONS across ALL four Commission Reports (2023,2024,2025,26).

Same method as the 2026-only run, but over the full 2023-01 .. 2026-07 timeline so a promotion
is caught in whatever year it happened. A per-lot commission-rate step-up on a TIERED symbol
(gold/majors: XAUUSD L5=$5,L6=$7,L7=$7.5,L8=$8,L9=$9) == a level promotion.

Per-day inference is noisy (small-lot rounding), so we stabilise on MONTH (volume-weighted,
>=1 lot/mo) -> monthly level staircase -> record each SUSTAINED step-up (running max increases),
pinned to the exact day that month the higher level first appears. Writes commission_report_result.json
(promotions + level_history); run ib_promotions_persist.py after to load ib_promotions.
"""
import openpyxl, sys, re, json
from collections import defaultdict
from datetime import datetime
import db_config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FILES = [
    "C:/Broker-crm/IB setting/Commission Report 2023.xlsx",
    "C:/Broker-crm/IB setting/Commission Report 2024.xlsx",
    "C:/Broker-crm/IB setting/Commission Report 2025.xlsx",
    "C:/Broker-crm/IB setting/Commission Report 26.xlsx",
]

def wal(s):
    m = re.match(r"\s*(\d+)", str(s or "")); return m.group(1) if m else None
def num(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0
def parse_dt(s):
    s = re.sub(r"\s+", " ", str(s or "").strip())
    for fmt in ("%b %d %Y %I:%M%p", "%b %d %Y %I:%M %p"):
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    return None

# ---- rate ladders -------------------------------------------------------
con = db_config.connect(); cur = con.cursor()
cur.execute("SELECT symbol, ib_level, comm_per_lot FROM commission_rates")
ladder = defaultdict(dict)
for sym, lv, cpl in cur.fetchall():
    ladder[sym][int(lv)] = float(cpl or 0)
def tiered(sym):
    d = ladder.get(sym)
    if not d: return False
    vals = [d[l] for l in (5,6,7,8,9) if l in d]
    return len({round(v,4) for v in vals}) >= 3
TIERED = {s for s in ladder if tiered(s)}
def infer_level(sym, rate):
    d = ladder.get(sym)
    if not d: return None
    best, bestdiff = None, 1e9
    for lv in (5,6,7,8,9):
        if lv not in d or d[lv] <= 0: continue
        diff = abs(d[lv] - rate) / d[lv]
        if diff < bestdiff: best, bestdiff = lv, diff
    return best if bestdiff <= 0.04 else None
# aggregated IB names for display
cur.execute("SELECT ext_ib_id, name FROM ibs WHERE ext_ib_id IS NOT NULL")
names = {str(r[0]): r[1] for r in cur.fetchall()}
print(f"tiered symbols: {len(TIERED)}")

# ---- stream every Details* sheet across all 4 files ---------------------
month_bucket = defaultdict(lambda: [0.0, 0.0])   # (wallet, 'YYYY-MM', sym) -> [comm, vol]
day_bucket   = defaultdict(lambda: [0.0, 0.0])   # (wallet, 'YYYY-MM-DD', sym) -> [comm, vol]
grand = 0
for path in FILES:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    n = 0
    for sh in wb.sheetnames:
        if not sh.lower().startswith("details"): continue
        for r in wb[sh].iter_rows(min_row=2, values_only=True):
            w = wal(r[1])
            if not w: continue
            sym = str(r[5] or "").strip()
            if sym not in TIERED: continue
            vol = num(r[7]); comm = num(r[9]); dt = parse_dt(r[0])
            if not dt or vol <= 0: continue
            iso = dt.date().isoformat()
            mb = month_bucket[(w, iso[:7], sym)]; mb[0] += comm; mb[1] += vol
            db_ = day_bucket[(w, iso, sym)];      db_[0] += comm; db_[1] += vol
            n += 1
    wb.close()
    grand += n
    print(f"  {path.split('/')[-1]}: {n} tiered rows  (cum {grand})", flush=True)

# ---- monthly volume-weighted level --------------------------------------
mvotes = defaultdict(lambda: defaultdict(float))   # (wallet, month) -> {level: vol}
for (w, m, sym), (c, v) in month_bucket.items():
    if v < 1.0: continue
    lv = infer_level(sym, c / v)
    if lv: mvotes[(w, m)][lv] += v
wallet_month_level = defaultdict(dict)
for (w, m), votes in mvotes.items():
    wallet_month_level[w][m] = max(votes, key=votes.get)

# day level (to pin the exact promotion day)
dvotes = defaultdict(lambda: defaultdict(float))
for (w, d, sym), (c, v) in day_bucket.items():
    if v < 0.3: continue
    lv = infer_level(sym, c / v)
    if lv: dvotes[(w, d)][lv] += v
wallet_day_level = defaultdict(dict)
for (w, d), votes in dvotes.items():
    wallet_day_level[w][d] = max(votes, key=votes.get)

# ---- level changes: PROMOTIONS (up) and DEMOTIONS (down) -----------------
# Walk each IB's monthly level staircase and record EVERY sustained transition. IB levels are not
# fixed — an IB promoted to L9 whose rate later falls back to L8 was DEMOTED, so the timeline must
# show both directions (else it looks inconsistent with the IB's current level).
events = []      # (wallet, date, from_level, to_level, direction)
level_history = {}
for w, ml in wallet_month_level.items():
    seq = sorted(ml.items())
    compressed = []
    for m, lv in seq:
        if not compressed or compressed[-1][1] != lv:
            compressed.append((m, lv))
    level_history[w] = compressed
    for i in range(1, len(compressed)):
        prev = compressed[i-1][1]; lv = compressed[i][1]
        if lv == prev:
            continue
        month = compressed[i][0]
        up = lv > prev
        # exact day = first day that month the day-level reaches the new level
        days = sorted(d for d, dlv in wallet_day_level.get(w, {}).items()
                      if d[:7] == month and (dlv >= lv if up else dlv <= lv))
        day = days[0] if days else month + "-01"
        events.append((w, day, prev, lv, "promotion" if up else "demotion"))

promos = [e for e in events if e[4] == "promotion"]
demos = [e for e in events if e[4] == "demotion"]
print(f"\nlevel-change events: {len(events)}  (promotions {len(promos)}, demotions {len(demos)})")
print(f"IBs with any change: {len({e[0] for e in events})}")
for w, day, fl, tl, d in sorted(events, key=lambda e: e[1])[:30]:
    arrow = "->" if d == "promotion" else "=>DOWN"
    print(f"  {day}  IB {w:>10} ({str(names.get(w,'?'))[:18]:18})  L{fl} {arrow} L{tl}  [{d}]")

out = {
    "promotions": [{"wallet": w, "date": d, "from_level": fl, "to_level": tl, "direction": dir}
                   for w, d, fl, tl, dir in events],
    "level_history": {w: [{"date": d, "level": lv} for d, lv in h] for w, h in level_history.items()},
}
with open("C:/Broker-crm/backend/commission_report_result.json", "w", encoding="utf-8") as f:
    json.dump(out, f)
print("\nwrote commission_report_result.json")
con.close()
