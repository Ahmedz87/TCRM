import sys, re
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, string_at
import time
from collections import Counter

load_dll(); connect()
man = get_manager()

SERVERLOG_SIZE = 796
OFFSET_MSG = 284
from_time = int(time.time()) - 7 * 86400
to_time   = int(time.time())

total = c_int(0)
ptr = vcall(man, 96, c_void_p,
            [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
            2, from_time, to_time, b"", byref(total))

print(f"Total trade journal records: {total.value}")

patterns = Counter()
close_samples = []
for i in range(total.value):
    off = ptr + i * SERVERLOG_SIZE
    msg = string_at(off + OFFSET_MSG, 512).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
    if "close order" in msg:
        patterns["close order"] += 1
        if len(close_samples) < 8:
            close_samples.append(msg)
    elif "changed balance" in msg:
        patterns["changed balance"] += 1
    elif "open order" in msg or "did order" in msg:
        patterns["open order"] += 1
    elif "deleted" in msg:
        patterns["deleted"] += 1
    else:
        patterns["other"] += 1

print(f"\nMessage type counts: {dict(patterns)}")
print(f"\nClose order samples:")
for s in close_samples:
    print(f"  {s}")
mem_free(ptr)
