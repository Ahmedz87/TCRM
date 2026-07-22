import time, subprocess, os, sys
from datetime import datetime
# token now lives in gitignored meta_config.py (secrets centralization, Jul 2026) — the old
# regex-grep of a hardcoded token in meta_sync.py crashed the poller after the hardening.
import meta_config
os.environ["META_ACCESS_TOKEN"] = meta_config.META_ACCESS_TOKEN
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
