"""
backfill_mt5.py — one-time historical backfill of MT5 deposits/withdrawals/bonus (Step A).

The live bridge only pulls the last ~120 days, so 2021->2025 balance ops were never fetched
even though the MT5 server still retains them (verified: data back to mid-2021). This drives the
bridge's /api/backfill endpoint in WEEKLY chunks (safe vs the MT 'Memory error (6)' on big
windows; a week returns up to ~240k deals fine), saving ONLY balance ops (action 2/3/6).

Idempotent: save_deals_to_db skips existing deal_id, so already-synced weeks are no-ops.
After the pull it converts the new balance deals to transactions.

Usage:  python backfill_mt5.py            # 2021-01-01 -> now (MT5 launch was 2021)
        python backfill_mt5.py 2024-01-01 # custom start
"""
import sys
import json
import urllib.request
from datetime import datetime, timezone, timedelta

START = datetime(2021, 1, 1, tzinfo=timezone.utc)
if len(sys.argv) > 1:
    START = datetime.strptime(sys.argv[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
END = datetime.now(timezone.utc)
STEP = timedelta(days=7)
BRIDGE = "http://localhost:5000/api/backfill"


def ep(d):
    return int(d.timestamp())


def main():
    cur = START
    total_saved = 0
    weeks = 0
    print(f"MT5 balance-op backfill {START:%Y-%m-%d} -> {END:%Y-%m-%d}", flush=True)
    while cur < END:
        nxt = min(cur + STEP, END)
        url = f"{BRIDGE}?from={ep(cur)}&to={ep(nxt)}&mode=balance"
        try:
            r = json.load(urllib.request.urlopen(url, timeout=900))
            if "error" in r:
                print(f"{cur:%Y-%m-%d}: bridge error {r['error']}", flush=True)
            else:
                s = r.get("saved_candidates", 0); f = r.get("fetched", 0)
                total_saved += s
                if f or s:
                    print(f"{cur:%Y-%m-%d}: fetched={f:>7} balance_saved={s:>5} total={total_saved:,}", flush=True)
        except Exception as e:
            print(f"{cur:%Y-%m-%d}: ERR {e}", flush=True)
        cur = nxt
        weeks += 1
    print(f"\nbackfill done ({weeks} weeks, {total_saved:,} balance deals saved). converting...", flush=True)
    import sync_transactions
    n = sync_transactions.sync()
    print(f"sync_transactions inserted {n} transaction(s).", flush=True)


if __name__ == "__main__":
    main()
