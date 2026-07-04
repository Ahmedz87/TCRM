import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free, TradeRecord
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

# First test AdmTradesRequest with open_only=0 (all trades including closed)
print("=== Testing AdmTradesRequest (slot 80) with open_only=0 ===")
total = c_int(0)
ptr = vcall(man, 80, c_void_p,
            [c_char_p, c_int, POINTER(c_int)],
            b"*", 0, byref(total))
print(f"open_only=0: ptr={ptr} total={total.value}")
if ptr and total.value > 0:
    # Count by cmd type
    from collections import Counter
    cmds = Counter()
    stride = sizeof(TradeRecord)
    for i in range(min(total.value, 10000)):
        rec = TradeRecord.from_address(ptr + i * stride)
        cmds[rec.cmd] += 1
    print(f"CMD distribution (first 10k): {dict(cmds)}")
    mem_free(ptr)

# Test with open_only=1
print("\n=== Testing AdmTradesRequest (slot 80) with open_only=1 ===")
total2 = c_int(0)
ptr2 = vcall(man, 80, c_void_p,
             [c_char_p, c_int, POINTER(c_int)],
             b"*", 1, byref(total2))
print(f"open_only=1: ptr={ptr2} total={total2.value}")
if ptr2:
    mem_free(ptr2)

# Try slots 103-115 with login+from+to signature
from_time = int(time.time()) - 365 * 86400
to_time   = int(time.time())
test_login = 432261
print(f"\n=== Probing slots 103-120 with (login, from, to, total) ===")
for slot in range(103, 121):
    try:
        total3 = c_int(0)
        ptr3 = vcall(man, slot, c_void_p,
                     [c_int, c_int, c_int, POINTER(c_int)],
                     test_login, from_time, to_time, byref(total3))
        if ptr3 and total3.value > 0:
            rec = TradeRecord.from_address(ptr3)
            sym = rec.symbol.decode("utf-8", errors="ignore").strip()
            print(f"  Slot {slot}: {total3.value} records | sym={sym!r} cmd={rec.cmd} *** HIT ***")
            mem_free(ptr3)
        else:
            print(f"  Slot {slot}: total={total3.value}")
    except Exception as e:
        print(f"  Slot {slot}: {type(e).__name__}")
