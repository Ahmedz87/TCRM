"""
mt4_journal_worker.py — dedicated MT4-B (login 1026) journal worker.

Runs on its OWN MT4 manager connection (1026), separate from the live-sync mt4_loop (1025), so the
heavy journal pulls (balance ops + trades) and the historical backfill NEVER require stopping
mt4_loop again. Pulls balance ops (deposits/withdrawals/bonus) from the server journal; chunked to
stay under the ~288k-record server cap.

Loop mode (default): every ~2 min pull the last few hours of journal -> save balance ops (idempotent).
Backfill mode:  python mt4_journal_worker.py --backfill 2022-11-01
"""
import sys
import time
from ctypes import c_int, c_void_p, byref, POINTER, c_char_p, string_at
from datetime import datetime, timezone, timedelta
import bridge_mt4 as b
import mt_managers as M
from fetch_mt4_balance import save, SERVERLOG_SIZE, OFFSET_TIME, OFFSET_MSG, RE_BAL

# bind this process to the dedicated MT4-B login BEFORE connecting
b.MT4_LOGIN, b.MT4_PASSWORD = M.MT4["B"]      # dedicated MT4-B login 1026

INTERVAL = 120
INCR_WINDOW = 4 * 3600
BACKFILL_STEP = timedelta(days=2)             # small chunks vs the ~288k server cap


def fetch_window(man, frm, to):
    total = c_int(0)
    ptr = b.vcall(man, 96, c_void_p, [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  2, frm, to, b"", byref(total))
    if not ptr or total.value <= 0:
        return [], 0
    ops = []
    for i in range(total.value):
        msg = string_at(ptr + i * SERVERLOG_SIZE + OFFSET_MSG, 512).split(b"\x00")[0].decode("utf-8", "ignore")
        m = RE_BAL.search(msg)
        if not m:
            continue
        t = string_at(ptr + i * SERVERLOG_SIZE + OFFSET_TIME, 24).split(b"\x00")[0].decode("utf-8", "ignore").strip()
        try:
            dt = datetime.strptime(t[:19], "%Y.%m.%d %H:%M:%S")
        except Exception:
            dt = None
        ops.append((m.group(1), int(m.group(2)), float(m.group(3)), int(m.group(4)),
                    m.group(5).strip().strip("'"), dt))
    b.mem_free(ptr)
    return ops, total.value


def backfill(start):
    b.connect()
    man = b.get_manager()
    end = datetime.now(timezone.utc)
    cur = start
    allops = []
    print(f"MT4-B backfill {start:%Y-%m-%d} -> now (2-day chunks)", flush=True)
    while cur < end:
        nxt = min(cur + BACKFILL_STEP, end)
        ops, n = fetch_window(man, int(cur.timestamp()), int(nxt.timestamp()))
        allops.extend(ops)
        if n:
            print(f"{cur:%Y-%m-%d}: records={n} ops={len(ops)} running={len(allops):,}", flush=True)
        cur = nxt
    print(f"saving {len(allops):,} ops...", flush=True)
    save(allops)


def loop():
    b.connect()
    man = b.get_manager()
    print("MT4-B journal worker (1026) live", flush=True)
    while True:
        try:
            now = int(time.time())
            ops, _ = fetch_window(man, now - INCR_WINDOW, now)
            if ops:
                save(ops)
        except Exception as e:
            print("worker err:", e, flush=True)
            try:
                b._manager = None
                b.connect()
                man = b.get_manager()
            except Exception:
                pass
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        s = sys.argv[sys.argv.index("--backfill") + 1]
        backfill(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    else:
        loop()
