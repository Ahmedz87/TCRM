import urllib.request, json, time

# Get negative accounts from DB, check each LIVE for flat status, find a coverable one
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
negs = db.execute(text("SELECT login, balance FROM clients WHERE balance < 0 AND platform='MT5' ORDER BY balance DESC LIMIT 40")).fetchall()
db.close()

print(f"Checking {len(negs)} accounts live for a flat+coverable one...\n")
found = None
for login, bal in negs:
    try:
        d = json.loads(urllib.request.urlopen(f"http://localhost:5000/neg-cover/check/{login}", timeout=10).read())
        if d.get("flat") and d.get("balance",0) < 0:
            deficit = abs(d["balance"]); credit = d.get("credit",0)
            eligible = (d["balance"] >= -200) or (credit >= deficit*0.5) or (credit >= deficit)
            tag = "ELIGIBLE" if eligible else "manual-only"
            print(f"  #{login} bal={d['balance']:.2f} credit={credit:.2f} FLAT [{tag}]")
            if eligible and not found:
                found = login
    except: pass

if found:
    print(f"\n>>> Covering flat eligible account #{found}...")
    r = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://localhost:5000/neg-cover/cover/{found}", method="POST"), timeout=60).read())
    print("Result:", json.dumps(r))
    if r.get("status")=="covered":
        print(f"✓ WORKS! Balance now {r.get('balance_after')}")
else:
    print("\nNo flat eligible accounts found in this batch (most have open trades)")
