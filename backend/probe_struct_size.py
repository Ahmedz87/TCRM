"""
probe_struct_size.py — find the real UserRecord struct size used by the MT4 DLL.
Run: python probe_struct_size.py
"""
import sys, ctypes
from ctypes import c_int, c_void_p, POINTER, WINFUNCTYPE, byref, cast
import os

DLL_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mtmanapi64.dll")
from mt_secrets import MT4_SERVER, MT4 as _MT4
MT4_LOGIN, MT4_PASSWORD = _MT4["A"]

V_MEM_FREE = 3
V_CONNECT  = 6
V_LOGIN    = 9

def vcall(obj, index, restype, argtypes, *args):
    vtable = cast(obj, POINTER(c_void_p))
    funcs  = cast(vtable[0], POINTER(c_void_p))
    proto  = WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(funcs[index])(obj, *args)

ws2 = ctypes.WinDLL("ws2_32.dll")
ws2.WSAStartup(0x0202, byref((ctypes.c_byte * 512)()))
dll = ctypes.WinDLL(DLL_PATH)
dll.MtManVersion.restype = c_int; dll.MtManVersion.argtypes = []
ver = dll.MtManVersion()
dll.MtManCreate.restype = c_int; dll.MtManCreate.argtypes = [c_int, POINTER(c_void_p)]
man = c_void_p()
dll.MtManCreate(ver, byref(man))
vcall(man, V_CONNECT, c_int, [ctypes.c_char_p], MT4_SERVER)
vcall(man, V_LOGIN,   c_int, [c_int, ctypes.c_char_p], MT4_LOGIN, MT4_PASSWORD)

# AdmUsersRequest = vtable slot 79
total = c_int(0)
ptr = vcall(man, 79, c_void_p, [ctypes.c_char_p, POINTER(c_int)], b"*", byref(total))
print(f"Total users: {total.value}")
print(f"Buffer pointer: {ptr}")

# Read the first 10 login integers spaced at different offsets
# Login is always the FIRST field (offset 0) in UserRecord
# We scan stride sizes 1100..1200 and find which one gives sequential non-zero logins
import struct as S
print("\nProbing stride (looking for consistent login values):")
for stride in range(1100, 1210, 4):
    logins = []
    valid = True
    for i in range(5):
        raw = (ctypes.c_byte * 4).from_address(ptr + i * stride)
        login = S.unpack_from("<i", raw)[0]
        logins.append(login)
        if login <= 0 or login > 10000000:
            valid = False
    if valid:
        print(f"  stride={stride}  logins={logins}  <-- CANDIDATE")
    else:
        print(f"  stride={stride}  logins={logins}")

vcall(man, V_MEM_FREE, None, [c_void_p], ptr)
print("\nDone.")
