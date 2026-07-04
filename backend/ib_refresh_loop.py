"""
ib_refresh_loop.py — keep IB trades / commission / credit-trade flags current.

Periodically rebuilds the ib_trades table (atomic swap) so the IB Admin 'Trades',
'Short <5min' and 'Credit trades' views + per-IB commission reflect newly-synced deals
(and their captured balance_after). Run as a background process, like the bridges.
"""
import time
import traceback
import ib_trades

INTERVAL = 1800   # 30 minutes (throttled from 10min — rebuilding ib_trades from 11.6M deals
                  # every 10min was a steady CPU drain; IB stats don't need that freshness)

if __name__ == "__main__":
    print("ib_refresh_loop started; rebuilding every", INTERVAL, "s", flush=True)
    while True:
        t0 = time.time()
        try:
            ib_trades.main()
        except Exception:
            traceback.print_exc()
        # sleep the remainder of the interval (rebuild itself takes ~1 min)
        time.sleep(max(30, INTERVAL - (time.time() - t0)))
