import time
import bridge
mgr = bridge.get_manager()
now = int(time.time()); ft = now - 2*24*3600
test_login = 576497
deals = mgr.DealRequestByLogins([test_login], ft, now) or []
print(f"{len(deals)} deals for {test_login}")
print(f"{'Deal':>10} {'Pos':>10} {'Entry':>5} {'Act':>3} {'Sym':8} {'Vol':>6} {'Time':>12}")
for d in deals:
    act = getattr(d,"Action",-1)
    if act not in (0,1):
        continue
    print(f"{getattr(d,'Deal',0):>10} {getattr(d,'PositionID',0):>10} {getattr(d,'Entry',-1):>5} {act:>3} {getattr(d,'Symbol',''):8} {float(getattr(d,'Volume',0))/100:>6.2f} {getattr(d,'Time',0):>12}")
