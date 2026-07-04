import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager

# The 'type' param uses MTDeal enum. Find balance/credit deal type constants
print("=== MTDeal constants ===")
d = MT5Manager.MTDeal
for name in dir(d):
    if not name.startswith('__'):
        try:
            val = getattr(d, name)
            if isinstance(val, int):
                print(f"  MTDeal.{name} = {val}")
        except: pass
