"""
import_feed_promotions.py — Task 3 (CORRECT method): the XAUUSD rebate is a FIXED whole number per lot
(=$grade). So per gold trade, rate = rebate / lots is an integer 5..10, and a promotion/demotion is the
MOMENT the per-trade rate steps to a new integer. (A blended TotalComm/Volume average produces fractions
and hides the step — that was the earlier mistake.)

Method:
  1. gold 'Rebate' rows from the feed -> (ext_ib_id, client login, when, $).  login+symbol from the Comment.
  2. match each rebate to the client's XAU deal by nearest deal_time (feed is UTC; also try +3h) -> lots
     = deals.volume/10000  -> per-trade rate = round(rebate/lots), keep only clean gold rates (4.5..10.5).
  3. per IB: CURRENT grade = the dominant integer rate over the LAST few days; also the earlier grade, so
     the change + its date are captured. Apply where current != stored (log ib_promotions + set ib_level).
"""
import sys, io, re, openpyxl, datetime, bisect
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import defaultdict, Counter
import db_config

FEED = r'C:\Broker-crm\IB setting\- 2026-07-17 (1) 1.xlsx'
SHEET = 'Wallet-Transactions-2026-07-17'
P_FROM, P_TO = '2026-06-25', '2026-07-18'
RECENT_DAYS = 5           # window that defines the CURRENT grade
MIN_RECENT = 6            # need this many clean recent gold trades
DOM = 0.55                # dominant rate must be >= this share of the window
def amt(v):
    if v is None: return 0.0
    if isinstance(v,(int,float)): return float(v)
    m=re.search(r'-?[\d,]+\.?\d*',str(v).replace(',','')); return float(m.group()) if m else 0.0
def pdate(s):
    for f in ('%b %d %Y %I:%M%p','%b %d %Y %I:%M %p'):
        try: return datetime.datetime.strptime(str(s).strip(),f)
        except: pass
    return None
def acc(s):
    m=re.match(r'\s*(\d+)',str(s or '')); return int(m.group(1)) if m else None
def mode_share(vals):
    if not vals: return None,0
    c=Counter(vals); v,n=c.most_common(1)[0]; return v, n/len(vals)

def main(commit=False):
    wb=openpyxl.load_workbook(FEED,read_only=True,data_only=True)
    ws=wb[SHEET]; it=ws.iter_rows(values_only=True); hdr=list(next(it)); ix={h:i for i,h in enumerate(hdr)}
    reb=defaultdict(list)   # ext -> [(epoch, amount, login)]
    logins=set()
    for r in it:
        if str(r[ix['TransactionType']])!='Rebate': continue
        cm=str(r[ix['Comment']]);
        if 'XAU' not in cm.upper(): continue
        lg=re.search(r'MT[45]-(\d+)',cm); d=pdate(r[ix['CreationDate']]); a=amt(r[ix['Amount']]); ext=acc(r[ix['Wallet']])
        if lg and d and a>0 and ext is not None:
            reb[ext].append((int(d.timestamp()), a, int(lg.group(1)))); logins.add(int(lg.group(1)))
    wb.close()

    c=db_config.connect(); cur=c.cursor()
    cur.execute("""SELECT login, deal_time, volume FROM deals
        WHERE symbol ILIKE 'XAU%%' AND volume>0 AND action IN (0,1)
          AND deal_date BETWEEN %s AND %s AND login = ANY(%s)""",(P_FROM,P_TO,list(logins)))
    dl=defaultdict(list)
    for lg,t,v in cur.fetchall(): dl[lg].append((int(t),float(v)))
    for lg in dl: dl[lg].sort()
    dtimes={lg:[x[0] for x in v] for lg,v in dl.items()}

    # per-IB matched (epoch, rate_int)
    per=defaultdict(list)
    for ext, lst in reb.items():
        for ep,a,lg in lst:
            arr=dl.get(lg);
            if not arr: continue
            times=dtimes[lg]; best=None
            for tep in (ep, ep+10800):
                i=bisect.bisect_left(times,tep)
                for j in (i-1,i,i+1):
                    if 0<=j<len(arr):
                        g=abs(arr[j][0]-tep)
                        if best is None or g<best[1]: best=(arr[j][1],g)
            if best and best[0] and best[1]<7200:
                rate=a/(best[0]/10000.0)
                if 4.5<=rate<=10.5: per[ext].append((ep, round(rate)))

    # stored (original) levels
    cur.execute("SELECT ext_ib_id, id, name, COALESCE(ib_level,0) FROM ibs WHERE is_primary IS NOT FALSE AND ext_ib_id IS NOT NULL")
    stored={r[0]:(r[1],r[2],r[3]) for r in cur.fetchall()}

    cut_recent=int(datetime.datetime(2026,7,17).timestamp())-RECENT_DAYS*86400
    apply=[]
    for ext, tr in per.items():
        if ext not in stored: continue
        tr.sort()
        recent=[r for ep,r in tr if ep>=cut_recent]
        if len(recent)<MIN_RECENT: continue
        cur_lvl, share = mode_share(recent)
        if share < DOM: continue                      # rate not stable enough
        ibid,name,orig = stored[ext]
        if orig<5 or cur_lvl==orig: continue
        early,_=mode_share([r for ep,r in tr if ep<cut_recent] or [r for _,r in tr])
        # transition date = first recent-window trade at the new rate
        tdate=None
        for ep,r in tr:
            if ep>=cut_recent and r==cur_lvl: tdate=datetime.date.fromtimestamp(ep); break
        apply.append((ext,ibid,name,orig,cur_lvl,early,round(share*100),len(recent),str(tdate)))

    apply.sort(key=lambda x:(x[4]-x[3]))
    print(f"Grade changes from the per-trade gold rate: {len(apply)}")
    print(f"{'ext':>9} {'name':<24}{'from':>5}{'to':>4}{'early':>6}{'conf%':>6}{'n':>4}  changed_on")
    for x in apply:
        print(f"{x[0]:>9} {str(x[2])[:22]:<24}{x[3]:>5}{x[4]:>4}{str(x[5]):>6}{x[6]:>6}{x[7]:>4}  {x[8]}")

    if not commit:
        print("\nDRY RUN — nothing written."); c.close(); return
    for ext,ibid,name,orig,cur_lvl,early,share,n,tdate in apply:
        direction='promote' if cur_lvl>orig else 'demote'
        cur.execute("""INSERT INTO ib_promotions (ib_id, ext_ib_id, promo_date, from_level, to_level, direction, source)
            VALUES (%s,%s,%s,%s,%s,%s,'feed_pertrade_2026-07-17')""",(ibid,ext,tdate,orig,cur_lvl,direction))
        cur.execute("UPDATE ibs SET ib_level=%s WHERE ext_ib_id=%s",(cur_lvl,ext))
    c.commit()
    print(f"\nApplied {len(apply)} grade changes (per-trade rate; logged to ib_promotions + ibs.ib_level).")
    c.close()

if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
