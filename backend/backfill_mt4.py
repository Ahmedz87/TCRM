"""
backfill_mt4.py — chunked MT4 balance-op (deposit/withdraw/bonus) backfill from the journal.

The MT4 journal IS retained back to ~2023, but a single large request hits a ~288k-record
SERVER CAP and silently truncates (that's why a 10-year request only returned the 2023 slice).
So we pull in SMALL windows (2-day) that stay under the cap, parse balance ops (RE_BAL), and
save (idempotent on deal_id = order + 4e9). 2019-2022 isn't on the journal -> legacy import.

Run with mt4_loop STOPPED (single MT4 connection).  python backfill_mt4.py [START YYYY-MM-DD]
"""
import sys, re
from ctypes import c_int, c_void_p, byref, POINTER, c_char_p, string_at
from datetime import datetime, timezone, timedelta
import bridge_mt4 as b
from fetch_mt4_balance import save, SERVERLOG_SIZE, OFFSET_TIME, OFFSET_MSG, RE_BAL

CAP_WARN = 280000   # near the ~288k server cap -> window likely truncated, shrink it
STEP = timedelta(days=2)


def fetch_window(man, frm, to):
    total = c_int(0)
    ptr = b.vcall(man, 96, c_void_p, [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  2, frm, to, b"", byref(total))
    n = total.value
    if not ptr or n <= 0:
        return [], 0
    ops = []
    for i in range(n):
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
    return ops, n


def main():
    start = datetime(2022, 11, 1, tzinfo=timezone.utc)
    if len(sys.argv) > 1:
        start = datetime.strptime(sys.argv[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    b.connect()
    man = b.get_manager()
    all_ops = []
    capped = []
    cur = start
    print(f"MT4 balance backfill {start:%Y-%m-%d} -> {end:%Y-%m-%d} (2-day chunks)", flush=True)
    while cur < end:
        nxt = min(cur + STEP, end)
        ops, n = fetch_window(man, int(cur.timestamp()), int(nxt.timestamp()))
        all_ops.extend(ops)
        if n >= CAP_WARN:
            capped.append(f"{cur:%Y-%m-%d}")
        if n:
            print(f"{cur:%Y-%m-%d}: records={n:>7} balance_ops={len(ops):>5} running={len(all_ops):,}"
                  + (" *CAPPED-shrink needed*" if n >= CAP_WARN else ""), flush=True)
        cur = nxt
    print(f"\ncollected {len(all_ops):,} balance ops. saving (idempotent)...", flush=True)
    if capped:
        print(f"WARNING capped windows (re-run smaller): {capped}", flush=True)
    save(all_ops)


if __name__ == "__main__":
    main()
