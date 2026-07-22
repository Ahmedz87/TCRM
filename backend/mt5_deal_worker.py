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

import mt_managers as _M
SERVER = _M.MT5_SERVER
LOGIN, PW = _M.MT5["B"]
INTERVAL = 10                        # 10s cadence — MT5 deals near-real-time (was 90s; user Jul 2026)
INCR_WINDOW = 30 * 60                # fast per-cycle window (recent deals, light pull → true 10s freshness)
DEEP_WINDOW = 3 * 3600               # periodic deeper pull to catch any late fills
DEEP_EVERY = 30                      # one deep 3h pull every ~30 cycles (~5 min)
TX_EVERY = 6                         # tx_sync (deposits/withdrawals) every ~6 cycles (~60s), not every 10s


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
    print("MT5-B deal worker (1026) live - 10s cadence", flush=True)
    i = 0
    while True:
        try:
            now = int(time.time())
            # every cycle: recent window (light) so deals are fresh within ~10s;
            # periodically a 3h deep pull catches any late-reported fills.
            pull(m, now - (DEEP_WINDOW if i % DEEP_EVERY == 0 else INCR_WINDOW), now)
            if i % TX_EVERY == 0:
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
        i += 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        s = sys.argv[sys.argv.index("--backfill") + 1]
        backfill(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    else:
        loop()
