import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager

# Try different ways to find the deal type constants
print("=== MTDeal attributes (all) ===")
d = MT5Manager.MTDeal
attrs = [a for a in dir(d) if not a.startswith('__')]
print(attrs)

print("\n=== Looking for ENUM_DEAL_ACTION ===")
for name in dir(MT5Manager):
    if 'ENUM' in name.upper() or 'ACTION' in name.upper():
        print(f"  {name}")
        obj = getattr(MT5Manager, name)
        for a in dir(obj):
            if not a.startswith('__'):
                try:
                    v = getattr(obj, a)
                    if isinstance(v, int):
                        print(f"     {a} = {v}")
                except: pass
