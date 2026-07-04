import urllib.request, json
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
# ALL negative MT5 accounts, not just 40
negs = [r[0] for r in db.execute(text("SELECT login FROM clients WHERE balance < 0 AND platform='MT5'")).fetchall()]
db.close()
print(f"Checking all {len(negs)} negative MT5 accounts for open trades...\n")

open_trade = []
for login in negs:
    try:
        d = json.loads(urllib.request.urlopen(f"http://localhost:5000/neg-cover/inspect/{login}", timeout=8).read())
        if d.get("Balance",0) < 0 and d.get("positions",0) > 0:
            pnl = d.get("floating_pnl",0)
            open_trade.append((login, d['Balance'], d['positions'], pnl))
    except: pass

print(f"Found {len(open_trade)} negative accounts WITH open trades:\n")
cover = [x for x in open_trade if x[3] < 10]
skip = [x for x in open_trade if x[3] >= 10]
print(f"  PnL < 10 (COVERABLE): {len(cover)}")
for login,bal,pos,pnl in cover[:15]:
    print(f"    #{login} bal={bal:.2f} pos={pos} pnl={pnl:.2f}")
print(f"\n  PnL >= 10 (Positive PnL, skip): {len(skip)}")
for login,bal,pos,pnl in skip[:10]:
    print(f"    #{login} bal={bal:.2f} pos={pos} pnl={pnl:.2f}")
