"""
verify_mt4_vtable.py — READ-ONLY final confirmation that the build-1473 header vtable indices
match our live DLL, by calling count-returning reads that BRACKET TradeTransaction(105):
  [97]  UsersRequest(int* total)   -> total should ~= AdmUsersRequest count (~5307)
  [104] OnlineRequest(int* total)  -> total should be a small sane number of online connections
If both totals are sane, the count is exact through 104, so 105 = TradeTransaction is certain.
No money is moved.
"""
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from ctypes import c_int, c_void_p, byref, POINTER
import bridge_mt4 as B

def main():
    B.connect()
    adm = len(B.get_all_users())
    print(f"AdmUsersRequest[79] count = {adm}")
    man = B.get_manager()
    for idx, name in ((97, "UsersRequest"), (104, "OnlineRequest"), (106, "TradesRequest")):
        total = c_int(0)
        try:
            ptr = B.vcall(man, idx, c_void_p, [POINTER(c_int)], byref(total))
            print(f"  [{idx}] {name:14} total={total.value}  ptr={'null' if not ptr else 'ok'}")
        except Exception as e:
            print(f"  [{idx}] {name:14} EXCEPTION {e}")

if __name__ == "__main__":
    main()
