import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, mem_free, TradeRecord
from ctypes import c_int, c_uint, c_void_p, POINTER, byref, sizeof, cast, CFUNCTYPE
import time

load_dll(); connect()
man = get_manager()

# Direct vtable call without vcall wrapper
# TradesUserHistory(login, from, to, total*) -> TradeRecord*
from_t = c_uint(int(time.time()) - 7 * 86400)
to_t   = c_uint(int(time.time()))
login  = c_int(432261)
total  = c_int(0)

# Get vtable pointer
vtable_ptr = ctypes.cast(man, ctypes.POINTER(ctypes.c_void_p))[0]
vtable     = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p))

print("Testing TradesUserHistory at slots 106-112 with direct vtable call...")
for slot in range(106, 113):
    try:
        fn_ptr  = vtable[slot]
        # Prototype: TradeRecord* __stdcall TradesUserHistory(this, int login, uint32 from, uint32 to, int* total)
        FuncType = ctypes.WINFUNCTYPE(c_void_p, c_void_p, c_int, c_uint, c_uint, POINTER(c_int))
        fn      = FuncType(fn_ptr)
        total   = c_int(0)
        result  = fn(man, login, from_t, to_t, byref(total))
        if result and total.value > 0:
            rec = TradeRecord.from_address(result)
            sym = rec.symbol.decode("utf-8", errors="ignore").strip()
            print(f"  Slot {slot}: {total.value} records | sym={sym!r} cmd={rec.cmd} *** HIT ***")
            mem_free(result)
        else:
            print(f"  Slot {slot}: total={total.value} result={result}")
    except Exception as e:
        print(f"  Slot {slot}: {type(e).__name__}: {str(e)[:60]}")
