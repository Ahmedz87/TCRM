import urllib.request, json
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
negs = [r[0] for r in db.execute(text("SELECT login FROM clients WHERE balance < 0 AND platform='MT5'")).fetchall()]
db.close()

cover = []
for login in negs:
    try:
        d = json.loads(urllib.request.urlopen(f"http://localhost:5000/neg-cover/inspect/{login}", timeout=8).read())
        if d.get("Balance",0) < 0 and d.get("positions",0) > 0 and d.get("floating_pnl",0) < 10:
            cover.append((login, d['Balance'], d['positions'], d['floating_pnl']))
    except: pass

print(f"=== PnL < 10 open-trade accounts (Model 4 coverable): {len(cover)} ===")
for login,bal,pos,pnl in cover:
    print(f"  #{login} bal={bal:.2f} pos={pos} pnl={pnl:.2f}")

# Test cover the first one to prove Model 4 + $10 threshold works
if cover:
    test = cover[0][0]
    print(f"\n>>> Covering #{test} (Model 4, PnL<10)...")
    r = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://localhost:5000/neg-cover/cover/{test}", method="POST"), timeout=20).read())
    print("Result:", json.dumps(r))
    if r.get("status")=="covered":
        print(f"✓ MODEL 4 + $10 THRESHOLD WORKS — balance now {r.get('balance_after')}")
