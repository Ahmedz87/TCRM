"""
step_b_trades.py — Step B: backfill full DEAL history (trades, action 0/1) 2021-01 -> now on the
idle MT5-C login (3027), so it never touches the live worker on 1026. save_deals_to_db is idempotent
(balance ops already loaded are skipped; this fills the missing trades). 2-day chunks stay under the
~288k server cap. Runs for hours — launch in background. Resumable: re-run, already-saved deals skip.
"""
import sys, time
import MT5Manager
from datetime import datetime, timezone, timedelta
import bridge
from mt5_deal_worker import fmt

SERVER = "192.109.15.62:443"
LOGIN, PW = 3027, "Malakies@008"     # MT5-C, idle
STEP = timedelta(days=2)


def connect():
    m = MT5Manager.ManagerAPI()
    if not m.Connect(SERVER, LOGIN, PW):
        raise Exception("MT5-C (3027) connect failed")
    return m


def run(start):
    m = connect()
    end = datetime.now(timezone.utc)
    cur = start
    seen = trades = 0
    print(f"Step B trades backfill {start:%Y-%m-%d} -> now (2-day chunks) on MT5-C 3027", flush=True)
    while cur < end:
        nxt = min(cur + STEP, end)
        for attempt in range(3):
            try:
                raw = m.DealRequestByGroup("*", int(cur.timestamp()), int(nxt.timestamp())) or []
                rows = fmt(raw)
                bridge.save_deals_to_db(rows)
                seen += len(raw); trades += sum(1 for r in rows if r["action"] in (0, 1))
                if len(raw):
                    print(f"{cur:%Y-%m-%d}: deals={len(raw):,} run_trades={trades:,}", flush=True)
                break
            except Exception as e:
                print(f"{cur:%Y-%m-%d}: ERR {str(e)[:80]} (retry {attempt})", flush=True)
                time.sleep(5)
                try: m.Disconnect()
                except Exception: pass
                try: m = connect()
                except Exception: pass
        cur = nxt
    print(f"STEP B DONE: {seen:,} deals seen, {trades:,} trades in range", flush=True)


if __name__ == "__main__":
    s = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2021-01-01"
    run(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc))
