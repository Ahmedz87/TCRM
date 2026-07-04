"""
Commission Report 26.xlsx analyzer.

Two jobs the user asked for:
  1. CROSS-CHECK: does our commission math agree with the broker's Commission Report?
     - sum Details.Commission per IB  vs  Aggregated.TotalComm  vs  our ib_commissions/ibs.
  2. PROMOTION DETECTION: an IB's per-lot rate on a TIERED symbol (e.g. XAUUSD $7->$8)
     stepping up over time == the moment they were promoted a level. Record the date +
     from/to level as promotion events (-> ib_promotions table, shown in admin + portal).

Details.Wallet == ibs.ext_ib_id (verified 100%). Time like "May 31 2026 12:25AM"
(sometimes double-spaced). Level inferred by matching per-lot rate to commission_rates ladder.
"""
import openpyxl, sys, re, json, psycopg2
from collections import defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
XLSX = "C:/Broker-crm/IB setting/Commission Report 26.xlsx"
import db_config

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
ladder = defaultdict(dict)               # symbol -> {level: rate}
for sym, lv, cpl in cur.fetchall():
    ladder[sym][int(lv)] = float(cpl or 0)
# a symbol is "tiered" (discriminates level) if its 5..9 rates aren't all equal
def tiered(sym):
    d = ladder.get(sym)
    if not d: return False
    vals = [d[l] for l in (5,6,7,8,9) if l in d]
    return len(set(round(v,4) for v in vals)) >= 3
TIERED = {s for s in ladder if tiered(s)}

def infer_level(sym, rate):
    """nearest level whose ladder rate matches `rate` within 4%."""
    d = ladder.get(sym)
    if not d: return None
    best, bestdiff = None, 1e9
    for lv in (5,6,7,8,9):
        if lv not in d or d[lv] <= 0: continue
        diff = abs(d[lv] - rate) / d[lv]
        if diff < bestdiff: best, bestdiff = lv, diff
    return best if bestdiff <= 0.04 else None

# ---- Aggregated ---------------------------------------------------------
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
agg = {}   # wallet -> (ibcode, name, indirect, direct, total)
for r in wb["Aggregated"].iter_rows(min_row=2, values_only=True):
    w = wal(r[2])
    if w: agg[w] = (str(r[1]), r[0], num(r[4]), num(r[5]), num(r[6]))
print(f"Aggregated IBs: {len(agg)}   tiered symbols: {len(TIERED)}")

# ---- stream Details -----------------------------------------------------
det_comm = defaultdict(float)                        # wallet -> sum commission
det_vol  = defaultdict(float)
# per (wallet, day, sym) sums (only tiered symbols)
day_bucket = defaultdict(lambda: [0.0, 0.0])   # (wallet, day, sym) -> [comm, vol]
n = 0
for r in wb["Details"].iter_rows(min_row=2, values_only=True):
    w = wal(r[1])
    if not w: continue
    sym = str(r[5] or "").strip()
    vol = num(r[7]); comm = num(r[9]); dt = parse_dt(r[0])
    det_comm[w] += comm; det_vol[w] += vol
    n += 1
    if dt and sym in TIERED and vol > 0:
        cell = day_bucket[(w, dt.date().isoformat(), sym)]
        cell[0] += comm; cell[1] += vol
    if n % 100000 == 0:
        print(f"  ...{n} rows", flush=True)
wb.close()
print(f"Details rows: {n}")

# ---- collapse day buckets -> level per (wallet, day) --------------------
# for each wallet/day: take the level implied by the biggest-volume tiered symbol
wd_votes = defaultdict(lambda: defaultdict(float))   # (wallet,day) -> {level: volume}
for (w, d, sym), (c, v) in day_bucket.items():
    if v < 0.3: continue               # too small: rounding hides the step
    lv = infer_level(sym, c / v)
    if lv: wd_votes[(w, d)][lv] += v
wallet_day_level = defaultdict(dict)   # wallet -> {day: level}
for (w, d), votes in wd_votes.items():
    wallet_day_level[w][d] = max(votes, key=votes.get)

# ---- promotions = SUSTAINED level step-ups ------------------------------
# Per-day inference is noisy (small-lot rounding bounces the implied level).
# Stabilise on MONTH (volume-weighted level over the whole month), which is robust,
# then pin the exact promotion DAY = first day that month the higher level shows up.
month_bucket = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # (w,month) -> sym -> [c,v]
for (w, d, sym), (c, v) in day_bucket.items():
    month_bucket[(w, d[:7])][sym][0] += c
    month_bucket[(w, d[:7])][sym][1] += v
wallet_month_level = defaultdict(dict)     # wallet -> {month: level}
for (w, m), syms in month_bucket.items():
    votes = defaultdict(float)
    for sym, (c, v) in syms.items():
        if v < 1.0: continue                # need >=1 lot/month to trust the rate
        lv = infer_level(sym, c / v)
        if lv: votes[lv] += v
    if votes:
        wallet_month_level[w][m] = max(votes, key=votes.get)

promotions = []      # (wallet, date, from_level, to_level)
level_history = {}   # wallet -> [(month, level)] compressed monthly staircase
for w, ml in wallet_month_level.items():
    seq = sorted(ml.items())                # (month, level) ascending
    compressed = []
    for m, lv in seq:
        if not compressed or compressed[-1][1] != lv:
            compressed.append((m, lv))
    level_history[w] = compressed
    running = compressed[0][1]
    for i in range(1, len(compressed)):
        lv = compressed[i][1]
        if lv > running:                    # sustained promotion to a new high
            month = compressed[i][0]
            # exact day = earliest day that month whose day-level >= lv
            days = sorted(d for d, dlv in wallet_day_level.get(w, {}).items()
                          if d[:7] == month and dlv >= lv)
            day = days[0] if days else month + "-01"
            promotions.append((w, day, running, lv))
            running = lv

# ---- cross-check totals -------------------------------------------------
cur.execute("SELECT ext_ib_id, total_commission, ib_level FROM ibs WHERE ext_ib_id IS NOT NULL")
our = {str(x[0]): (num(x[1]), x[2]) for x in cur.fetchall()}
rows = []
for w, (ibcode, name, ind, direct, total) in agg.items():
    dc = det_comm.get(w, 0.0)
    ours, ourlv = our.get(w, (None, None))
    rows.append((w, name, total, dc, ours, ourlv))
# summary numbers
agg_total = sum(x[2] for x in rows)                       # report TotalComm
det_total = sum(det_comm.values())
our_total = sum(v[0] for v in our.values() if v[0])
matched = [x for x in rows if x[4] is not None]           # IBs we also have in our DB
close = sum(1 for x in rows if x[2] and abs((x[3]-x[2])/x[2]) < 0.02)  # details vs report agree

print("\n===== CROSS-CHECK =====")
print(f"Report TotalComm (Aggregated): ${agg_total:,.0f}")
print(f"Details sum(Commission):       ${det_total:,.0f}")
print(f"Our ibs.total_commission:      ${our_total:,.0f}")
print(f"IBs where Details==Report(<2%): {close}/{len(rows)}")
# biggest divergences our-vs-report
div = [(x[0], x[1], x[4], x[2]) for x in rows if x[4] is not None and x[2]]
div.sort(key=lambda t: -abs((t[2] or 0) - t[3]))
print("\nTop 12 our-vs-report gaps (wallet, name, ours, report):")
for w, nm, ours, rep in div[:12]:
    print(f"  {w:>10} {str(nm)[:24]:24} ours=${(ours or 0):>10,.0f}  report=${rep:>10,.0f}")

print(f"\n===== PROMOTIONS =====")
print(f"IBs with a detected level step-up: {len(set(p[0] for p in promotions))}")
print(f"Total promotion events: {len(promotions)}")
for w, day, fl, tl in sorted(promotions, key=lambda p: p[1])[:20]:
    print(f"  {day}  IB {w:>10} ({str(agg.get(w,('','?'))[1])[:20]})  L{fl} -> L{tl}")

out = {
    "promotions": [{"wallet": w, "date": d, "from_level": fl, "to_level": tl} for w,d,fl,tl in promotions],
    "level_history": {w: [{"date": d, "level": lv} for d, lv in h] for w, h in level_history.items()},
    "crosscheck": {"report_total": agg_total, "details_total": det_total, "our_total": our_total,
                   "agree_close": close, "matched": len(matched)},
}
with open("C:/Broker-crm/backend/commission_report_result.json", "w", encoding="utf-8") as f:
    json.dump(out, f)
print("\nwrote commission_report_result.json")
con.close()
