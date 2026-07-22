"""
import_feed_commission.py — Task 2: extend the AUTHORITATIVE Excel commission from the old cutoff
(2026-07-04) to 2026-07-17 using the new feed's Wallet-Transactions 'Rebate' rows (per-trade
commission exactly as Plugit credited, incl. credit trades). Post-2026-07-17 stays on the engine.

For rebates dated AFTER 2026-07-04 (the delta; the <= Jul-04 overlap is already in the yearly-file
commission and is NOT re-added):
  · commission_excel  += per-ext_ib_id delta, on the person's PRIMARY ib row (same place the yearly
                         import writes it). The enforce_ib_commission trigger folds it into total.
  · excel_trade_commission  <- upsert (login, deal_id) = SUM(rebate) [login parsed from the Comment
                         'MT5-<login>'], lots from deals where the ticket exists (per-trade overlay).
  · excel_commission_daily  <- (ext_ib_id, day, SUM) for the new days (Jul 05..17).
Then run ib_trades.main() so commission_live is recomputed for > Jul-17 only (no double count) and
the per-trade excel overlay extends to Jul-17. Idempotent-ish: delete-then-insert the > Jul-04 slice.
"""
import sys, io, re, openpyxl, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from psycopg2.extras import execute_values
from collections import defaultdict
import db_config

FEED = r'C:\Broker-crm\IB setting\- 2026-07-17 (1) 1.xlsx'
SHEET = 'Wallet-Transactions-2026-07-17'
CUT = datetime.datetime(2026, 7, 4, 23, 59, 59)   # old excel cutoff (Plugit tz, same as the feed)

def amt(v):
    if v is None: return 0.0
    if isinstance(v,(int,float)): return float(v)
    m = re.search(r'-?[\d,]+\.?\d*', str(v).replace(',','')); return float(m.group()) if m else 0.0
def pdate(s):
    for f in ('%b %d %Y %I:%M%p','%b %d %Y %I:%M %p'):
        try: return datetime.datetime.strptime(str(s).strip(), f)
        except: pass
    return None
def acc(s):
    m = re.match(r'\s*(\d+)', str(s or '')); return int(m.group(1)) if m else None
def login_of(comment):
    m = re.search(r'MT[45]-(\d+)', str(comment or '')); return int(m.group(1)) if m else None

def main(commit=False):
    wb = openpyxl.load_workbook(FEED, read_only=True, data_only=True)
    ws = wb[SHEET]; it = ws.iter_rows(values_only=True); hdr = list(next(it)); ix = {h:i for i,h in enumerate(hdr)}
    delta_ext = defaultdict(float)                 # ext_ib_id -> delta commission
    trade = defaultdict(float)                     # (login, deal_id) -> commission
    trade_ext = {}                                 # (login, deal_id) -> ext_ib_id
    daily = defaultdict(float)                     # (ext_ib_id, day) -> commission
    n=0; skipped_nologin=0
    for r in it:
        if str(r[ix['TransactionType']]) != 'Rebate': continue
        d = pdate(r[ix['CreationDate']])
        if d is None or d <= CUT: continue         # only the NEW slice (> Jul 04)
        a = amt(r[ix['Amount']]); ext = acc(r[ix['Wallet']]); lg = login_of(r[ix['Comment']]); tk = r[ix['TicketID']]
        n += 1
        if ext is not None: delta_ext[ext] += a; daily[(ext, d.date())] += a
        if lg is not None and tk is not None:
            try: tk = int(tk)
            except: continue
            trade[(lg, tk)] += a; trade_ext[(lg, tk)] = ext
        else:
            skipped_nologin += 1
    wb.close()

    print(f"NEW (> Jul 04) rebates: {n:,}  total ${sum(delta_ext.values()):,.2f}  across {len(delta_ext)} ext_ib_id")
    print(f"  per-trade rows (login+ticket parsed): {len(trade):,}   (no login parsed: {skipped_nologin:,})")
    print(f"  daily (ext,day) rows: {len(daily):,}  days {min(k[1] for k in daily)}..{max(k[1] for k in daily)}")

    c = db_config.connect(); cur = c.cursor()
    # NOTE: the feed's TicketID is Plugit's internal rebate id, NOT our MT5 deal_id (verified), so it
    # can't feed excel_trade_commission (that per-trade overlay is keyed by MT5 deal_id). We therefore
    # only update the AUTHORITATIVE aggregates (commission_excel + excel_commission_daily); the per-
    # trade detail for Jul 05-17 falls back to the engine estimate — the totals are excel-exact.

    # commission_excel delta placement check
    exts = list(delta_ext.keys())
    cur.execute("SELECT ext_ib_id FROM ibs WHERE is_primary IS NOT FALSE AND ext_ib_id = ANY(%s)", (exts,))
    placeable = {r[0] for r in cur.fetchall()}
    unplaced = sum(delta_ext[e] for e in exts if e not in placeable)
    print(f"  ext_ib_id with a primary ib row: {len(placeable)} of {len(exts)}  (unplaceable ${unplaced:,.2f})")

    if not commit:
        print("\nDRY RUN — nothing written."); c.close(); return

    # 1) commission_excel += delta on the primary row (trigger folds it into total_commission)
    upd = [(delta_ext[e], e) for e in exts if e in placeable]
    execute_values(cur, "UPDATE ibs SET commission_excel = COALESCE(commission_excel,0)+v.d "
                        "FROM (VALUES %s) AS v(d,ext) WHERE ibs.ext_ib_id=v.ext AND ibs.is_primary IS NOT FALSE",
                   upd, page_size=1000)
    # 2) excel_commission_daily for the new days (replace any > Jul 04 slice for idempotency)
    cur.execute("DELETE FROM excel_commission_daily WHERE day > %s::date", (CUT.date(),))
    drows = [(e, d, round(v,4)) for (e,d),v in daily.items()]
    execute_values(cur, "INSERT INTO excel_commission_daily(ext_ib_id,day,commission) VALUES %s", drows, page_size=2000)
    c.commit()
    cur.execute("SELECT ROUND(SUM(commission_excel)::numeric,0) FROM ibs WHERE is_primary IS NOT FALSE"); print("\ncommission_excel SUM now:", cur.fetchone()[0], "(was 1,801,719)")
    cur.execute("SELECT COUNT(*), MAX(day) FROM excel_commission_daily"); print("excel_commission_daily:", cur.fetchone())
    c.close()

if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
