import time, subprocess, os, sys
from datetime import datetime
# load the working token from meta_sync.py once
import re
tok = re.search(r'TOKEN\s*=\s*"(EAA[^"]+)"', open("meta_sync.py",encoding="utf-8").read()).group(1)
os.environ["META_ACCESS_TOKEN"] = tok
os.environ.pop("META_FORM_ID", None)
os.environ.pop("META_PAGE_ID", None)
INTERVAL = 60  # seconds (1 min)
print(f"Meta lead poller started — fetching every {INTERVAL} s. Ctrl+C to stop.")
_sweep_every = 5   # run the archive re-capture sweep every Nth cycle (~5 min)
_cycle = 0
while True:
    print(f"\n[{datetime.now():%H:%M:%S}] fetching new leads...")
    try:
        subprocess.run([sys.executable, "fetch_meta_leads.py"], check=False)
    except Exception as e:
        print("poll error:", e)
    # archive re-capture: bring back archived CLIENTS who deposited after being archived
    _cycle += 1
    if _cycle % _sweep_every == 0:
        try:
            subprocess.run([sys.executable, "reactivation.py"], check=False)
        except Exception as e:
            print("sweep error:", e)
    time.sleep(INTERVAL)
