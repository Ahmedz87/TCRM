import urllib.request, json, time

# Time a single bridge cover to see where the 12s goes
# Find a flat eligible account first
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
negs = db.execute(text("SELECT login FROM clients WHERE balance < 0 AND balance > -200 AND platform='MT5' LIMIT 10")).fetchall()
db.close()

print("Timing individual bridge covers...")
for (login,) in negs[:3]:
    t0 = time.time()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://localhost:5000/neg-cover/cover/{login}", method="POST"), timeout=30).read())
        print(f"  #{login}: {time.time()-t0:.1f}s -> {r.get('status')}")
    except Exception as e:
        print(f"  #{login}: {time.time()-t0:.1f}s ERROR {e}")
