import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free
from ctypes import c_int, c_char_p, c_void_p, POINTER, byref, create_string_buffer
import struct

load_dll(); connect()
man = get_manager()

# SymbolGet(symbol, ConSymbol*) = slot 87, returns int
# ConSymbol is ~1936 bytes — allocate buffer
buf = create_string_buffer(2048)

test_symbols = [b"EURUSD", b"XAUUSD", b"BTCUSD", b"Tesla", b"USOIL", b"GBPUSD."]
for sym in test_symbols:
    try:
        rc = vcall(man, 87, c_int, [c_char_p, c_void_p], sym, buf)
        if rc == 0:
            # Find contract size — scan for known values (100000, 100, 1, 1000)
            base = ctypes.addressof(buf)
            name = ctypes.string_at(base, 12).split(b"\x00")[0].decode("utf-8", errors="ignore")
            print(f"\n{sym.decode()}: rc={rc} name={name!r}")
            # Scan doubles for contract size
            for off in range(80, 400, 8):
                try:
                    val = struct.unpack_from("<d", buf, off)[0]
                    if val in (1.0, 10.0, 100.0, 1000.0, 5000.0, 10000.0, 100000.0):
                        print(f"    offset {off}: {val}")
                except: pass
        else:
            print(f"{sym.decode()}: rc={rc} (not found or error)")
    except Exception as e:
        print(f"{sym.decode()}: {type(e).__name__}")
