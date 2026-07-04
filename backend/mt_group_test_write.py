"""ONE-ACCOUNT LIVE WRITE + verify. Changes login 335000009 IB\IB-7 -> IB\IB-5."""
import sys
import mt_managers as M
import MT5Manager as mt5m
LOGIN = 335000009
TARGET = "IB\IB-5"

login_c, pw_c = M.MT5["C"]
mgr = mt5m.ManagerAPI()
if not mgr.Connect(M.MT5_SERVER, login_c, pw_c):
    print("connect failed"); sys.exit(1)

def get(login):
    for meth in ("UserRequest","UserGet"):
        if hasattr(mgr, meth):
            try:
                u = getattr(mgr, meth)(int(login))
                if u: return u
            except Exception: pass
    return None

u = get(LOGIN)
if not u: print("user not found"); sys.exit(1)
before = u.Group
print("BEFORE:", before, flush=True)
u.Group = TARGET
res = mgr.UserUpdate(u)
print("UserUpdate ->", res, flush=True)
# re-read fresh
u2 = get(LOGIN)
print("AFTER :", getattr(u2,"Group",None), flush=True)
try: mgr.Disconnect()
except Exception: pass
