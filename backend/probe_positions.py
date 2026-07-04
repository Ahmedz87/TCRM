import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager
mgr = MT5Manager.ManagerAPI()
methods = [m for m in dir(mgr) if not m.startswith('__')]
print("=== Position methods (to check if account is flat) ===")
for m in methods:
    if 'position' in m.lower():
        print(f"  {m}")
print("\n=== PositionGet doc ===")
try:
    print(MT5Manager.ManagerAPI.PositionGet.__doc__)
except: pass
try:
    print(MT5Manager.ManagerAPI.PositionGetByLogin.__doc__)
except: pass
