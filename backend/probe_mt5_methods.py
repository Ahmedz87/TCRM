import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager

# List all methods on ManagerAPI related to balance/credit/deal/dealer
mgr = MT5Manager.ManagerAPI()
methods = [m for m in dir(mgr) if not m.startswith('__')]
print("=== Balance/Credit/Deal methods ===")
for m in methods:
    if any(k in m.lower() for k in ['balance','credit','deal','dealer','trade']):
        print(f"  {m}")

print("\n=== All methods containing 'User' ===")
for m in methods:
    if 'user' in m.lower():
        print(f"  {m}")
