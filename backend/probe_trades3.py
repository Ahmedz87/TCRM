import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free, TradeRecord
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

# Try AdmTradesRequest with specific group instead of wildcard
# This may return closed trades for that group
groups = [b"STD", b"ZERO", b"CENT", b"VIP", b"2-STD-IS"]
for grp in groups:
    total = c_int(0)
    try:
        ptr = vcall(man, 80, c_void_p,
                    [c_char_p, c_int, POINTER(c_int)],
                    grp, 0, byref(total))
        print(f"Group {grp}: ptr={ptr} total={total.value}")
        if ptr:
            mem_free(ptr)
    except Exception as e:
        print(f"Group {grp}: {e}")

# Also test slot 80 with open_only=1 (just open trades - should be fast)
print("\nopen_only=1 test:")
total2 = c_int(0)
ptr2 = vcall(man, 80, c_void_p, [c_char_p, c_int, POINTER(c_int)], b"*", 1, byref(total2))
print(f"open trades: {total2.value}")
if ptr2:
    stride = sizeof(TradeRecord)
    from collections import Counter
    cmds = Counter()
    for i in range(total2.value):
        rec = TradeRecord.from_address(ptr2 + i * stride)
        cmds[rec.cmd] += 1
    print(f"CMD types: {dict(cmds)}")
    mem_free(ptr2)
