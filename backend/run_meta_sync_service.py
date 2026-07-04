"""
Meta Leads Auto-Sync Service
Runs forever, syncing new leads every 3 minutes so nothing is ever lost.
Keep this running in its own terminal (like the bridge).

Run:  python run_meta_sync_service.py
"""
import sys, time, subprocess
import auto_match
from datetime import datetime

sys.path.insert(0, r'C:\broker-crm\backend')

SYNC_INTERVAL = 180  # 3 minutes

def main():
    print("=" * 50)
    print("META LEADS AUTO-SYNC SERVICE")
    print(f"Syncing every {SYNC_INTERVAL//60} minutes")
    print("Keep this window open. Ctrl+C to stop.")
    print("=" * 50)

    while True:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{ts}] Running sync...")
        try:
            # Import and run the sync directly
            import importlib
            import meta_sync
            importlib.reload(meta_sync)
            meta_sync.run_sync()
            try:
                auto_match.run_match_and_notify(verbose=False)
            except Exception as e:
                print(f'  auto-match error: {e}')
        except Exception as e:
            print(f"  Sync error: {e}")
        print(f"  Sleeping {SYNC_INTERVAL//60} min until next sync...")
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    main()
