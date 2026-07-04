import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager

d = MT5Manager.MTDeal
print("=== EnDealAction values ===")
ea = d.EnDealAction
for a in dir(ea):
    if not a.startswith('__'):
        try:
            v = getattr(ea, a)
            print(f"  {a} = {v}")
        except Exception as e:
            print(f"  {a}: {e}")
