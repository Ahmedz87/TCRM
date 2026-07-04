import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, mem_free, TradeRecord
from ctypes import c_int, c_uint, c_void_p, POINTER, byref
import time

load_dll(); connect()
man = get_manager()

# Use login 432261 = Nael Dhiyaa Talib (real MT4 client with balance $17685)
# and login 334161225 = Ahmed Zaman Abdulsahib
test_logins = [432261, 334161225, 430378, 427027, 433718]

vtable_ptr = ctypes.cast(man, ctypes.POINTER(ctypes.c_void_p))[0]
vtable     = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p))

# Test slot 107 and 110 with from=0 (all history)
for test_login in test_logins:
    login  = c_int(test_login)
    from_t = c_uint(0)
    to_t   = c_uint(int(time.time()))
    for slot in [107, 110]:
        try:
            fn_ptr   = vtable[slot]
            FuncType = ctypes.WINFUNCTYPE(c_void_p, c_void_p, c_int, c_uint, c_uint, POINTER(c_int))
            fn       = FuncType(fn_ptr)
            total    = c_int(0)
            result   = fn(man, login, from_t, to_t, byref(total))
            if result and total.value > 0:
                rec = TradeRecord.from_address(result)
                sym = rec.symbol.decode("utf-8", errors="ignore").strip()
                print(f"LOGIN {test_login} Slot {slot}: {total.value} records | sym={sym!r} cmd={rec.cmd} *** HIT ***")
                mem_free(result)
            else:
                print(f"LOGIN {test_login} Slot {slot}: 0 records")
        except Exception as e:
            print(f"LOGIN {test_login} Slot {slot}: {type(e).__name__}")
