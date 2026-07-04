"""
probe_mt4_hist.py — replicate the WORKING backfill method (small 2-day windows) to test MT4
journal retention. Runs on login 1026 (journal worker stopped). A 2026 window is the control:
if it shows balance_ops the method works; then compare old years.
"""
from ctypes import c_int, c_void_p, byref, POINTER, c_char_p, string_at
from datetime import datetime, timezone, timedelta
import bridge_mt4 as b
import mt_managers as M
from fetch_mt4_balance import SERVERLOG_SIZE, OFFSET_TIME, OFFSET_MSG, RE_BAL

b.MT4_LOGIN, b.MT4_PASSWORD = M.MT4["B"]   # 1026 journal-capable


def window(man, frm, to):
    total = c_int(0)
    ptr = b.vcall(man, 96, c_void_p, [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  2, frm, to, b"", byref(total))
    n = total.value; bal = 0; ft = lt = None
    if ptr and n > 0:
        for i in range(n):
            t = string_at(ptr + i*SERVERLOG_SIZE + OFFSET_TIME, 24).split(b"\x00")[0].decode("utf-8","ignore").strip()
            if ft is None: ft = t
            lt = t
            msg = string_at(ptr + i*SERVERLOG_SIZE + OFFSET_MSG, 512).split(b"\x00")[0].decode("utf-8","ignore")
            if RE_BAL.search(msg): bal += 1
        b.mem_free(ptr)
    return n, bal, ft, lt


def scan(man, label, start, days=10):
    """sum balance ops over `days` of 2-day chunks from start"""
    tot_rec = tot_bal = 0; ft = lt = None
    cur = start
    end = start + timedelta(days=days)
    while cur < end:
        nx = cur + timedelta(days=2)
        n, bal, a, z = window(man, int(cur.timestamp()), int(nx.timestamp()))
        tot_rec += n; tot_bal += bal
        if a and ft is None: ft = a
        if z: lt = z
        cur = nx
    print(f"  {label:28} over {days}d: records={tot_rec:>7,}  balance_ops={tot_bal:>6,}  [{ft} .. {lt}]")


def D(y,m,d): return datetime(y,m,d,tzinfo=timezone.utc)

if __name__ == "__main__":
    b.connect(); man = b.get_manager()
    print("connected 1026. 2-day-chunk scans:\n")
    scan(man, "2026 recent (CONTROL)", D(2026,6,1), 10)
    scan(man, "2023 mid (known-good)",  D(2023,6,1), 10)
    scan(man, "2022 mid",               D(2022,6,1), 10)
    scan(man, "2021 mid",               D(2021,6,1), 10)
    scan(man, "2020 mid",               D(2020,6,1), 10)
    scan(man, "2019 mid",               D(2019,6,1), 10)
    print("\nIf CONTROL shows balance_ops but old years show 0 => old data is purged from MT.")
