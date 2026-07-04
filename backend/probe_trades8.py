import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, mem_free, TradeRecord
import db_config
from ctypes import c_int, c_uint, c_void_p, POINTER, byref, sizeof
import time, psycopg2

load_dll(); connect()
man = get_manager()

# Get a login that definitely has recent MT4 trades
conn = db_config.connect()
cur = conn.cursor()
cur.execute("""
    SELECT ta.login FROM trading_accounts ta
    JOIN clients c ON c.id = ta.client_id
    WHERE ta.platform='MT4' AND ta.balance > 100
    ORDER BY ta.balance DESC LIMIT 5
""")
active_logins = [r[0] for r in cur.fetchall()]
conn.close()
print(f"Testing with active logins: {active_logins}")

vtable_ptr = ctypes.cast(man, ctypes.POINTER(ctypes.c_void_p))[0]
vtable     = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p))

for test_login in active_logins[:2]:
    login  = c_int(test_login)
    from_t = c_uint(0)           # from beginning of time
    to_t   = c_uint(int(time.time()))
    print(f"\n--- Login {test_login} ---")
    for slot in [106, 107, 108, 109, 110, 111, 112]:
        try:
            fn_ptr   = vtable[slot]
            FuncType = ctypes.WINFUNCTYPE(c_void_p, c_void_p, c_int, c_uint, c_uint, POINTER(c_int))
            fn       = FuncType(fn_ptr)
            total    = c_int(0)
            result   = fn(man, login, from_t, to_t, byref(total))
            if result and total.value > 0:
                rec = TradeRecord.from_address(result)
                sym = rec.symbol.decode("utf-8", errors="ignore").strip()
                print(f"  Slot {slot}: {total.value} records | sym={sym!r} cmd={rec.cmd} profit={rec.profit} *** HIT ***")
                mem_free(result)
            else:
                print(f"  Slot {slot}: total={total.value} result={result}")
        except Exception as e:
            print(f"  Slot {slot}: {type(e).__name__}")
