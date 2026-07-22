"""
Authoritative IB commission from Plugit's yearly Commission Reports.

The Excel files (2023, 2024, 2025, 26) cover 2023-01-02 .. 2026-07-04. For THAT span the Excel
per-IB TotalComm (DirectComm + IndirectComm — the real number Plugit credited the wallet) is the
truth; our deals-based recompute under-counts, so we DON'T use it there. For dates OUTSIDE the span
(2021-2022, and anything after the last Excel date) we keep our computed commission from `deals`.

  total_commission = SUM(Excel TotalComm across the 4 files)          [covered: 2023-01-02..2026-07-04]
                   + computed(deals, FX/gold lots x ib_level)         [uncovered: < 2023-01-01 or > 2026-07-04]

Linked by ext_ib_id (Aggregated 'Wallet' col == ibs.ext_ib_id). Written onto each person's PRIMARY
ib record (same one payoff was consolidated onto) so Commission + Payoff + Net line up on one row.
Idempotent. Only touches ext_ib_id groups (IBs not in Plugit keep their computed commission).
"""
import openpyxl, sys, re
from collections import defaultdict
import db_config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FILES = [
    "C:/Broker-crm/IB setting/Commission Report 2023.xlsx",
    "C:/Broker-crm/IB setting/Commission Report 2024.xlsx",
    "C:/Broker-crm/IB setting/Commission Report 2025.xlsx",
    "C:/Broker-crm/IB setting/Commission Report 26.xlsx",
]
COVER_LO = "2023-01-01"     # excel authority starts here (first excel trade 2023-01-02)
COVER_HI = "2026-07-17"     # last excel trade; deals after this stay computed

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0
def wal(s):
    m = re.match(r"\s*(\d+)", str(s or "")); return int(m.group(1)) if m else None

# ---- 1. Excel TotalComm per ext_ib_id, summed across the 4 yearly files -------
excel_comm = defaultdict(float)
per_year = {}
for path in FILES:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    agname = next(s for s in wb.sheetnames if s.lower() == "aggregated")
    ag = wb[agname]
    hdr = [c.value for c in next(ag.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(hdr)}
    wi, ti = idx["Wallet"], idx["TotalComm"]
    ytot = 0.0
    for r in ag.iter_rows(min_row=2, values_only=True):
        ext = wal(r[wi])
        if ext is None: continue
        c = num(r[ti]); excel_comm[ext] += c; ytot += c
    per_year[path.split("/")[-1]] = ytot
    wb.close()
print("Excel commission per file:")
for f, t in per_year.items(): print(f"  {f}: ${t:,.0f}")
print(f"Excel TOTAL (2023-2026): ${sum(excel_comm.values()):,.0f}  across {len(excel_comm)} IBs")

con = db_config.connect(); cur = con.cursor()

# ---- 2. columns for transparency ---------------------------------------------
cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS commission_excel DOUBLE PRECISION")
cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS commission_computed DOUBLE PRECISION")
cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS commission_source TEXT")

# ---- 3. computed commission for the UNCOVERED period only (per ext_ib_id) -----
from build_ibs import FX_OR_GOLD
FX = FX_OR_GOLD.replace("%", "%%")   # escape the ILIKE 'XAU%' for psycopg2 param parsing
cur.execute(f"""
    SELECT i.ext_ib_id,
           SUM((d.volume/10000.0) * CASE WHEN {FX} THEN i.ib_level ELSE 1 END) AS comm
    FROM deals d
    JOIN clients c ON c.login = d.login
    JOIN ibs i     ON i.agent_id = c.agent
    WHERE d.action IN (0,1) AND d.volume > 0 AND i.ext_ib_id IS NOT NULL
      AND d.deal_date < %s
    GROUP BY i.ext_ib_id
""", (COVER_LO,))
# NOTE: post-cutoff (> COVER_HI) commission is NOT part of this static import anymore — it lives in
# ibs.commission_live, recomputed from ib_trades every 30 min (see ib_trades.EXCEL_CUTOFF).
uncovered = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
print(f"IBs with pre-2023 computed commission: {len(uncovered)}  "
      f"total ${sum(uncovered.values()):,.0f}")

# ---- 4. primary record per ext_ib_id + that person's consolidated payoff --------
cur.execute("""
    SELECT ext_ib_id,
        ARRAY_AGG(id ORDER BY COALESCE(total_commission,0) DESC,
            CASE WHEN starts_with(COALESCE(group_name,''),'IB') THEN 0 ELSE 1 END, id),
        COALESCE(SUM(total_payoff),0)
    FROM ibs WHERE ext_ib_id IS NOT NULL GROUP BY ext_ib_id
""")
primary, payoff_by_ext = {}, {}
for r in cur.fetchall():
    primary[r[0]] = r[1][0]; payoff_by_ext[r[0]] = float(r[2] or 0)

# ---- 5. write total = excel(covered) + pre-2023 onto the primary ----------------
# The IB commission wallet is COMMISSION-ONLY, and every Operation-Log payout is dated inside the
# Excel window — EXCEPT an early IB may have withdrawn a pre-2023 wallet balance during 2023-26.
# So any payoff ABOVE the Excel commission is provably pre-2023 commission. pre-2023 commission =
# max(our MT4/5 computed for pre-2023, payoff - excel). This keeps MT4/5 data where it's real and
# guarantees net (= commission - payoff) is never negative, per the desk: payoff comes FROM commission.
exts = set(primary) | set(excel_comm) | set(uncovered)
updated = 0
for ext in exts:
    pid = primary.get(ext)
    if pid is None:      # in Excel but no ibs record — skip (nothing to attach to)
        continue
    exc = excel_comm.get(ext, 0.0)
    computed_pre = uncovered.get(ext, 0.0)
    shortfall = max(0.0, payoff_by_ext.get(ext, 0.0) - exc)   # payout the Excel commission can't cover
    unc = max(computed_pre, shortfall)                         # pre-2023 commission (never negative net)
    total = exc + unc
    src = "excel+computed" if (exc > 0 and unc > 0) else ("excel" if exc > 0 else "computed")
    # Mark EVERY record in the group with a source (secondary MT4/MT5 rows -> 'excel_secondary',
    # zeroed) so the periodic build_ibs recompute PRESERVES them (commission_source IS NOT NULL)
    # and never re-splits commission back onto the secondary row.
    cur.execute("""UPDATE ibs SET total_commission=0, commission_excel=0, commission_computed=0,
                   commission_source='excel_secondary',
                   unpaid_commission = 0 - COALESCE(paid_commission,0) WHERE ext_ib_id=%s""", (ext,))
    cur.execute("""UPDATE ibs SET total_commission=%s, commission_excel=%s, commission_computed=%s,
                   commission_source=%s, unpaid_commission = %s - COALESCE(paid_commission,0)
                   WHERE id=%s""", (total, exc, unc, src, total, pid))
    updated += 1
con.commit()

# ---- 6. catch-all floor: NO IB can have withdrawn more commission than it earned -------------
# (covers IBs with payoff but no ext_ib_id / not in the Plugit report — their payoff was linked by
# email. The wallet is commission-only, so payoff is a hard floor on lifetime commission.) The added
# amount goes into commission_computed and gets a commission_source so the periodic refresh keeps it.
cur.execute("""
    UPDATE ibs SET
        commission_computed = COALESCE(commission_computed,0) + (COALESCE(total_payoff,0) - total_commission),
        total_commission    = COALESCE(total_payoff,0),
        commission_source   = COALESCE(commission_source, 'computed'),
        unpaid_commission   = COALESCE(total_payoff,0) - COALESCE(paid_commission,0)
    WHERE COALESCE(total_payoff,0) > total_commission
""")
con.commit()

# ---- 7. is_primary: one visible row per person (MT4+MT5 share ext_ib_id) --------
cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT TRUE")
cur.execute("UPDATE ibs SET is_primary = TRUE WHERE ext_ib_id IS NULL")
cur.execute("""
    WITH grp AS (
      SELECT ext_ib_id, (ARRAY_AGG(id ORDER BY COALESCE(total_commission,0) DESC,
         CASE WHEN starts_with(COALESCE(group_name,''),'IB') THEN 0 ELSE 1 END, id))[1] AS primary_id
      FROM ibs WHERE ext_ib_id IS NOT NULL GROUP BY ext_ib_id )
    UPDATE ibs SET is_primary = (ibs.id = grp.primary_id)
    FROM grp WHERE ibs.ext_ib_id = grp.ext_ib_id
""")
con.commit()

cur.execute("SELECT ROUND(SUM(total_commission)::numeric,0), ROUND(SUM(total_payoff)::numeric,0) FROM ibs WHERE ext_ib_id IS NOT NULL")
tc, tp = cur.fetchone()
print(f"\nUpdated {updated} IB persons.")
print(f"Total commission (ext IBs): ${tc:,.0f}   Total payoff: ${tp:,.0f}")
cur.execute("SELECT COUNT(*) FROM ibs WHERE total_commission>0 AND COALESCE(total_payoff,0) > total_commission")
print(f"IBs still net-negative (payoff > commission): {cur.fetchone()[0]}")
con.close()
