import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, mem_free, TradeRecord
from ctypes import c_int, c_uint, c_void_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

vtable_ptr = ctypes.cast(man, ctypes.POINTER(ctypes.c_void_p))[0]
vtable     = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p))

# Slot 108 = TradesUserHistory (login, from, to, total)
# Test with logins that have open trades = definitely active accounts
test_logins = [4881, 10032, 432261, 430378]

FuncType = ctypes.WINFUNCTYPE(c_void_p, c_void_p, c_int, c_uint, c_uint, POINTER(c_int))
fn = FuncType(vtable[108])

for tl in test_logins:
    login  = c_int(tl)
    from_t = c_uint(0)                      # from epoch start
    to_t   = c_uint(int(time.time()) + 86400)  # tomorrow
    total  = c_int(0)
    try:
        result = fn(man, login, from_t, to_t, byref(total))
        print(f"Login {tl}: total={total.value} result={result}")
        if result and total.value > 0:
            stride = sizeof(TradeRecord)
            for i in range(min(total.value, 3)):
                rec = TradeRecord.from_address(result + i * stride)
                sym = rec.symbol.decode("utf-8", errors="ignore").strip()
                print(f"    order={rec.order} sym={sym!r} cmd={rec.cmd} profit={rec.profit:.2f} close={rec.close_time}")
            mem_free(result)
    except Exception as e:
        print(f"Login {tl}: {type(e).__name__}: {str(e)[:50]}")
