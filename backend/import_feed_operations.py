"""
import_feed_operations.py — Task 1 (payoffs) + Task 4 (TNFX->IB deposits) from the new Plugit feed.

Reads the 'OperationLogs' sheet of the new feed and INCREMENTALLY adds any approved operation not
already in ib_operations (dedup by order_id, else by ext+amount+op_date+type+to_account). Then:
  · total_payoff = SUM(approved withdrawals + transfers)  — EXCLUDES Wallet Deposit
  · tnfx_support = SUM(approved Wallet Deposit)           — money TNFX PAID INTO the IB wallet
    (campaign / target / office support), tracked separately, NOT counted as a payoff.
Idempotent: re-running adds nothing new. Column layout matches Operation Log.xlsx exactly.
"""
import sys, io, re, openpyxl
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import db_config

# The new feed exports UTC; the existing ib_operations stores Baghdad display time (UTC+3, no DST)
# — same txn appears as feed 02:41 vs DB 05:41. Shift feed stamps +3h so new rows match the existing
# convention AND dedup lines up. (Matches the desk "report on the source's displayed day" rule.)
TZ_SHIFT = timedelta(hours=3)

FEED = r'C:\Broker-crm\IB setting\- 2026-07-17 (1) 1.xlsx'
SHEET = 'OperationLogs - 2026-07-17'
DEPOSIT = 'Wallet Deposit'

def pdate(s):
    if not s: return None
    s = str(s).strip()
    for f in ('%Y-%m-%dT%H:%M:%S.%f','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%d'):
        try: return datetime.strptime(s[:26], f)
        except: pass
    return None
def acc_id(s):
    m = re.match(r'\s*(\d+)', str(s or '')); return int(m.group(1)) if m else None
def famt(v):
    if v is None or v == '': return 0.0
    if isinstance(v,(int,float)): return float(v)
    m = re.search(r'-?[\d,]+\.?\d*', str(v).replace(',','')); return float(m.group()) if m else 0.0

def main(commit=False):
    wb = openpyxl.load_workbook(FEED, read_only=True, data_only=True)
    ws = wb[SHEET]; it = ws.iter_rows(values_only=True); hdr = list(next(it))
    idx = {h:i for i,h in enumerate(hdr)}
    def g(r,name): return r[idx[name]] if name in idx else None
    feed = [r for r in it if any(r)]
    wb.close()

    c = db_config.connect(); cur = c.cursor()
    cur.execute("SELECT id, ext_ib_id, LOWER(email) FROM ibs")
    by_ext={}; by_email={}
    for iid,ext,em in cur.fetchall():
        if ext is not None: by_ext.setdefault(ext,iid)
        if em: by_email.setdefault(em,iid)
    # existing dedup keys
    cur.execute("SELECT order_id FROM ib_operations WHERE order_id IS NOT NULL")
    have_oid = {str(r[0]) for r in cur.fetchall()}
    # dedup key for no-order rows: ext + amount + type + op_date(to the second, Baghdad). ext+amount+
    # type+second is effectively unique (two identical transfers in the same second never happen).
    cur.execute("""SELECT ext_ib_id, ROUND(amount::numeric,2), request_type,
                          to_char(op_date,'YYYY-MM-DD HH24:MI:SS') FROM ib_operations""")
    have_key = {(r[0], float(r[1]) if r[1] is not None else 0.0, r[2], (r[3] or '')) for r in cur.fetchall()}

    new_rows=[]; n_pay=0; n_dep=0; dep_items=[]
    for r in feed:
        req = str(g(r,'Request') or '').strip()
        status = str(g(r,'Status') or '').strip()
        acct = g(r,'Account')
        if not req or acc_id(acct) is None:            # skip Total/blank rows
            continue
        if status != 'Approved':
            continue
        ext = acc_id(acct); em = (str(g(r,'Email')).strip().lower() if g(r,'Email') else '')
        ib_id = by_ext.get(ext) or by_email.get(em)
        amount = famt(g(r,'Amount')); conv = famt(g(r,'Converted Amount'))
        to_acc = g(r,'To Account')
        op = pdate(g(r,'Date')); op = (op + TZ_SHIFT) if op else None          # UTC -> Baghdad
        act = pdate(g(r,'Action Date')); act = (act + TZ_SHIFT) if act else None
        oid = str(g(r,'OrderID')) if g(r,'OrderID') else None
        # dedup
        if oid and oid in have_oid:
            continue
        key = (ext, round(amount,2), req, (op.strftime('%Y-%m-%d %H:%M:%S') if op else ''))
        if not oid and key in have_key:
            continue
        have_key.add(key)                                                      # guard intra-feed dups too
        new_rows.append((ext, ib_id, str(acct) if acct else None, g(r,'Name'), g(r,'Email'), req,
                         amount, conv, g(r,'Payment Type'), status, str(to_acc) if to_acc else None,
                         str(g(r,'ReferralID')) if g(r,'ReferralID') else None, g(r,'Comment'),
                         op, act, oid, g(r,'Note')))
        if req == DEPOSIT:
            n_dep += 1; dep_items.append((ext, g(r,'Name'), amount, str(op)[:10]))
        else:
            n_pay += 1

    print(f"New approved ops to add: {len(new_rows)}  (payouts={n_pay}, TNFX->IB deposits={n_dep})")
    print(f"  new payout $ = {sum(x[6] for x in new_rows if x[5]!=DEPOSIT):,.2f}")
    print(f"  new deposit $ = {sum(x[6] for x in new_rows if x[5]==DEPOSIT):,.2f}")
    for d in dep_items: print("   deposit:", d)

    if not commit:
        print("\nDRY RUN — nothing written. Pass commit=True to apply.")
        c.close(); return

    execute_values(cur, """INSERT INTO ib_operations(ext_ib_id,ib_id,account,name,email,request_type,amount,
        converted_amount,payment_type,status,to_account,referral_id,comment,op_date,action_date,order_id,note)
        VALUES %s""", new_rows, page_size=1000)
    # payoff EXCLUDES deposits; add a tracked TNFX-support column
    cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS tnfx_support DOUBLE PRECISION DEFAULT 0")
    cur.execute("""UPDATE ibs SET total_payoff = COALESCE((SELECT SUM(o.amount) FROM ib_operations o
        WHERE o.ib_id=ibs.id AND o.status='Approved' AND o.request_type <> %s),0)""", (DEPOSIT,))
    cur.execute("""UPDATE ibs SET tnfx_support = COALESCE((SELECT SUM(o.amount) FROM ib_operations o
        WHERE o.ib_id=ibs.id AND o.status='Approved' AND o.request_type = %s),0)""", (DEPOSIT,))
    c.commit()
    cur.execute("SELECT ROUND(SUM(total_payoff)::numeric,0), ROUND(SUM(tnfx_support)::numeric,2), COUNT(*) FROM ib_operations")
    print("\nAFTER:", cur.fetchone())
    cur.execute("SELECT ROUND(SUM(total_payoff)::numeric,0) FROM ibs"); print("SUM total_payoff:", cur.fetchone()[0])
    cur.execute("SELECT ROUND(SUM(tnfx_support)::numeric,2), COUNT(*) FILTER (WHERE tnfx_support>0) FROM ibs"); print("SUM tnfx_support / IBs:", cur.fetchone())
    c.close()

if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
