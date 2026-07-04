import sys
from datetime import datetime, timezone
from bridge import get_manager, save_deals_to_db

def map_deal(d):
    action = getattr(d,"Action",-1)
    comment = getattr(d,"Comment","") or ""
    profit = float(getattr(d,"Profit",0) or 0)
    return {
        "dealId": getattr(d,"Deal",0), "login": getattr(d,"Login",0),
        "symbol": getattr(d,"Symbol",""), "action": action,
        "type": ("deposit" if action==2 and profit>0 else "withdrawal" if action==2 and profit<0
                 else "credit_in" if action==3 and profit>=0 else "credit_out" if action==3 and profit<0
                 else "trade"),
        "payment_method": "",
        "entry": getattr(d,"Entry",0), "volume": float(getattr(d,"Volume",0) or 0),
        "price": float(getattr(d,"Price",0) or 0), "profit": profit,
        "commission": float(getattr(d,"Commission",0) or 0),
        "swap": float(getattr(d,"Storage",0) or 0),
        "comment": comment, "time": getattr(d,"Time",0),
        "balance_after": float(getattr(d,"Balance",0) or 0),
    }

def backfill(start_date):
    mgr = get_manager()
    if not mgr:
        print("ERROR: no MT5 manager"); return
    start_ts = int(datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())
    now_ts = int(datetime.now(timezone.utc).timestamp())
    print(f"Backfill {start_date} -> now, weekly chunks")
    chunk = 86400*7
    total = 0
    cur = start_ts
    while cur < now_ts:
        end = min(cur+chunk, now_ts)
        df = datetime.fromtimestamp(cur,tz=timezone.utc).strftime("%Y-%m-%d")
        dt = datetime.fromtimestamp(end,tz=timezone.utc).strftime("%Y-%m-%d")
        try:
            raw = mgr.DealRequestByGroup("*", cur, end) or []
            total += len(raw)
            print(f"  {df}..{dt}: {len(raw):,} deals")
            if raw:
                save_deals_to_db([map_deal(d) for d in raw])
        except Exception as e:
            print(f"  {df}..{dt}: ERROR {e}")
        cur = end
    print(f"Done. Total fetched: {total:,}")

if __name__ == "__main__":
    s = datetime.strptime(sys.argv[1],"%Y-%m-%d").date() if len(sys.argv)>1 else datetime(2026,5,1).date()
    backfill(s)
