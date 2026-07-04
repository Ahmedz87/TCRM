import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free
from ctypes import c_int, c_void_p, POINTER, byref, string_at
import struct

load_dll(); connect()
man = get_manager()

# SymbolsGetAll = slot 86
total = c_int(0)
ptr = vcall(man, 86, c_void_p, [POINTER(c_int)], byref(total))
print(f"Symbols: {total.value}")
if ptr and total.value > 0:
    # ConSymbol struct — find contract_size field
    # First symbol, dump first 200 bytes to find structure
    sym_size = 1936
    for i in range(min(total.value, 3)):
        base = ptr + i * sym_size
        symbol = string_at(base, 12).split(b"\x00")[0].decode("utf-8", errors="ignore")
        # contract_size is a double somewhere — common offset around 200-280
        print(f"\nSymbol: {symbol!r}")
        # Dump doubles at various offsets to find contract size (usually 100000 or 100)
        for off in range(176, 320, 8):
            try:
                val = struct.unpack_from("<d", (ctypes.c_byte*8).from_address(base+off))[0]
                if 1 <= val <= 1000000 and val == int(val):
                    print(f"  offset {off}: {val}")
            except: pass
    mem_free(ptr)
