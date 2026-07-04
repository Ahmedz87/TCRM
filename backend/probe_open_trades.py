import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free, TradeRecord
from ctypes import c_int, c_char_p, c_void_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

# Get open trades only
total = c_int(0)
ptr = vcall(man, 80, c_void_p,
            [c_char_p, c_int, POINTER(c_int)],
            b"*", 1, byref(total))
print(f"Open trades: {total.value}")
if ptr and total.value > 0:
    stride = sizeof(TradeRecord)
    from collections import Counter
    cmds = Counter()
    samples = []
    for i in range(total.value):
        rec = TradeRecord.from_address(ptr + i * stride)
        cmds[rec.cmd] += 1
        if len(samples) < 5 and rec.cmd in (0,1):
            sym = rec.symbol.decode("utf-8", errors="ignore").strip()
            samples.append(f"  login={rec.login} sym={sym!r} cmd={rec.cmd} vol={rec.volume} profit={rec.profit:.2f}")
    print(f"CMD types: {dict(cmds)}")
    print("Sample open trades:")
    for s in samples: print(s)
    mem_free(ptr)
else:
    print("No open trades returned")
