s = open(r"C:\broker-crm\backend\bridge.py", encoding="utf-8", errors="ignore").read()
# Find the transaction sync function
import re
for kw in ["after deal_id", "deals to process", "new transactions saved", "def sync_transactions", "INSERT INTO transactions", "tx_type"]:
    i = s.find(kw)
    if i > 0:
        print(f"=== '{kw}' at {i} ===")
        print(s[max(0,i-200):i+250])
        print("---\n")
