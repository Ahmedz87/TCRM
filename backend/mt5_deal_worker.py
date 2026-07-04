"""
mt5_deal_worker.py — dedicated MT5-B (login 1026) deal/transaction worker.

Runs on its OWN MT5 manager connection (1026), separate from the live-sync bridge (1025), so the
heavy DealRequestByGroup never blocks session/equity/account sync. This is why new accounts now
show in ~2 min (the bridge does accounts-only) and deposits/withdrawals stay fresh within ~90s.

Loop mode (default): every ~90s pull the last few hours of deals -> save_deals_to_db (idempotent)
-> sync_transactions.  Backfill mode: python mt5_deal_worker.py --backfill 2021-01-01
"""
import sys
import time
import MT5Manager
from datetime import datetime, timezone, timedelta
import bridge                         # reuse save_deals_to_db (DB-only)
from sync_transactions import sync as tx_sync

SERVER = "192.109.15.62:443"
LOGIN = 1026
PW = "Malakies@008"
INTERVAL = 90
INCR_WINDOW = 3 * 3600               # re-pull last 3h each cycle (idempotent; catches late fills)


def connect():
    m = MT5Manager.ManagerAPI()
    if not m.Connect(SERVER, LOGIN, PW):
        raise Exception("MT5-B (1026) connect failed")
    return m


def fmt(raw):
    out = []
    for d in raw:
        action = int(getattr(d, "Action", -1))
        prof = float(getattr(d, "Profit", 0) or 0)
        out.append({
            "dealId": getattr(d, "Deal", 0), "login": getattr(d, "Login", 0),
            "symbol": getattr(d, "Symbol", ""), "action": action,
            "type": ("deposit" if action == 2 and prof > 0 else "withdrawal" if action == 2 else
                     "bonus_deposit" if action == 6 and prof >= 0 else "bonus_withdrawal" if action == 6 else
                     "credit_in" if action == 3 and prof >= 0 else "credit_out" if action == 3 else "trade"),
            "entry": getattr(d, "Entry", 0), "volume": float(getattr(d, "Volume", 0) or 0),
            "price": float(getattr(d, "Price", 0) or 0), "profit": prof,
            "commission": float(getattr(d, "Commission", 0) or 0),
            "swap": float(getattr(d, "Storage", 0) or 0),
            "comment": getattr(d, "Comment", ""), "time": getattr(d, "Time", 0), "balance_after": 0,
        })
    return out


def pull(m, frm, to):
    raw = m.DealRequestByGroup("*", frm, to) or []
    bridge.save_deals_to_db(fmt(raw))
    return len(raw)


def backfill(start):
    m = connect()
    end = datetime.now(timezone.utc)
    cur = start
    step = timedelta(days=7)
    tot = 0
    print(f"MT5-B backfill {start:%Y-%m-%d} -> now (weekly)", flush=True)
    while cur < end:
        nxt = min(cur + step, end)
        try:
            n = pull(m, int(cur.timestamp()), int(nxt.timestamp()))
            tot += n
            if n:
                print(f"{cur:%Y-%m-%d}: {n}", flush=True)
        except Exception as e:
            print(f"{cur:%Y-%m-%d}: ERR {e}", flush=True)
        cur = nxt
    tx_sync()
    print(f"backfill done, {tot:,} deals seen", flush=True)


def loop():
    m = connect()
    print("MT5-B deal worker (1026) live", flush=True)
    while True:
        try:
            now = int(time.time())
            pull(m, now - INCR_WINDOW, now)
            tx_sync()
        except Exception as e:
            print("worker err:", e, flush=True)
            try:
                m.Disconnect()
            except Exception:
                pass
            time.sleep(5)
            try:
                m = connect()
            except Exception:
                pass
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        s = sys.argv[sys.argv.index("--backfill") + 1]
        backfill(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    else:
        loop()
