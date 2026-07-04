import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, mem_free, TradeRecord
from ctypes import c_int, c_uint, c_void_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

vtable_ptr = ctypes.cast(man, ctypes.POINTER(ctypes.c_void_p))[0]
vtable     = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p))

login  = c_int(4881)
from_t = c_uint(0)
to_t   = c_uint(int(time.time()) + 86400)

print("Sweeping slots 104-120 with (login, from, to, total) history signature...")
for slot in range(104, 121):
    try:
        FuncType = ctypes.WINFUNCTYPE(c_void_p, c_void_p, c_int, c_uint, c_uint, POINTER(c_int))
        fn = FuncType(vtable[slot])
        total = c_int(0)
        result = fn(man, login, from_t, to_t, byref(total))
        if result and total.value > 0:
            rec = TradeRecord.from_address(result)
            sym = rec.symbol.decode("utf-8", errors="ignore").strip()
            print(f"  Slot {slot}: {total.value} records | sym={sym!r} cmd={rec.cmd} *** HIT! ***")
            mem_free(result)
        else:
            print(f"  Slot {slot}: total={total.value}")
    except Exception as e:
        print(f"  Slot {slot}: {type(e).__name__}")
