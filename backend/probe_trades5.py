import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free, TradeRecord
from ctypes import c_int, c_uint, c_void_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

# Use c_uint for time (MT4 uses __time32_t which is unsigned 32-bit)
from_time = ctypes.c_uint(int(time.time()) - 7 * 86400)
to_time   = ctypes.c_uint(int(time.time()))
test_login = 432261

print("Probing with c_uint times, slots 106-115...")
for slot in range(106, 116):
    try:
        total = c_int(0)
        ptr = vcall(man, slot, c_void_p,
                    [c_int, c_uint, c_uint, POINTER(c_int)],
                    test_login, from_time, to_time, byref(total))
        if ptr and total.value > 0:
            rec = TradeRecord.from_address(ptr)
            sym = rec.symbol.decode("utf-8", errors="ignore").strip()
            print(f"  Slot {slot}: {total.value} records | sym={sym!r} cmd={rec.cmd} *** HIT ***")
            mem_free(ptr)
        else:
            print(f"  Slot {slot}: total={total.value} ptr={ptr}")
    except Exception as e:
        print(f"  Slot {slot}: {type(e).__name__}")
