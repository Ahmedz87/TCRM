import urllib.request, json
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
negs = [r[0] for r in db.execute(text("SELECT login FROM clients WHERE balance < 0 AND platform='MT5' LIMIT 40")).fetchall()]
db.close()

print("Looking for a Model 4 case (negative balance + open trades + negative PnL)...\n")
found = None
for login in negs:
    try:
        d = json.loads(urllib.request.urlopen(f"http://localhost:5000/neg-cover/inspect/{login}", timeout=10).read())
        if d.get("Balance",0) < 0 and d.get("positions",0) > 0:
            pnl = d.get("floating_pnl",0)
            tag = "NEGATIVE PnL (Model 4 case)" if pnl < 0 else "positive PnL (skip)"
            print(f"  #{login} bal={d['Balance']:.2f} positions={d['positions']} pnl={pnl:.2f} -> {tag}")
            if pnl < 0 and not found:
                found = login
    except: pass

if found:
    print(f"\n>>> Testing Model 4 cover on #{found}...")
    r = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://localhost:5000/neg-cover/cover/{found}", method="POST"), timeout=20).read())
    print("Result:", json.dumps(r))
    if r.get("status")=="covered":
        print("✓ MODEL 4 WORKS — covered open-trade account with negative PnL!")
else:
    print("\nNo Model 4 cases right now (no negative-balance accounts with open trades + negative PnL)")
