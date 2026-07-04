import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free, TradeRecord
from ctypes import c_int, c_void_p, POINTER, byref, sizeof
import time

load_dll(); connect()
man = get_manager()

from_time = int(time.time()) - 30 * 86400
to_time   = int(time.time())
test_login = 432261

print("Probing TradesUserHistory slots 88-102...")
for slot in range(88, 103):
    try:
        total = c_int(0)
        ptr = vcall(man, slot, c_void_p,
                    [c_int, c_int, c_int, POINTER(c_int)],
                    test_login, from_time, to_time, byref(total))
        if ptr and total.value > 0:
            rec = TradeRecord.from_address(ptr)
            sym = rec.symbol.decode("utf-8", errors="ignore").strip()
            print(f"  Slot {slot}: {total.value} records | login={rec.login} sym={sym!r} cmd={rec.cmd} profit={rec.profit} *** CANDIDATE ***")
            mem_free(ptr)
        else:
            print(f"  Slot {slot}: total={total.value}")
    except Exception as e:
        print(f"  Slot {slot}: ERROR {type(e).__name__}")
