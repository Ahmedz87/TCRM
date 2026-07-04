import time
# Reuse the bridge's manager connection
import bridge

mgr = bridge.get_manager()
if not mgr:
    print("Could not get manager - is the MT5 bridge able to connect?")
    raise SystemExit

import datetime
now = int(time.time())
ft  = now - 3*24*3600   # last 3 days

deals = mgr.DealRequestByGroup("*", ft, now) or []
print(f"Got {len(deals)} deals in last 3 days")

# Find a few TRADE deals (Action 0 or 1 = buy/sell), not balance ops
shown = 0
for d in deals:
    action = getattr(d, "Action", -1)
    if action not in (0, 1):
        continue
    print("\n=== TRADE DEAL ===")
    # print every attribute that doesn't start with _
    for attr in dir(d):
        if attr.startswith("_"): 
            continue
        try:
            val = getattr(d, attr)
            if callable(val): 
                continue
            print(f"  {attr} = {val}")
        except Exception:
            pass
    shown += 1
    if shown >= 3:
        break

if shown == 0:
    print("No buy/sell trade deals found in this window - try widening the days.")
