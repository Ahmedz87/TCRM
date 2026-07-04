import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_trade_history, save_mt4_deals

load_dll()
connect()
print("Fetching ALL MT4 trade history...")
trades = get_trade_history(days=3650)
print(f"Found {len(trades)} trades")
if trades:
    save_mt4_deals(trades)
    print("Done - all MT4 trades saved to deals table")
else:
    print("No trades returned")
