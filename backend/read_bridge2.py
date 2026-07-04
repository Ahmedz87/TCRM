with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find deals sync section
for keyword in ['sync_deals', 'deals_to_db', 'DealsGet', 'RequestDeals', 'from_time', 'last_sync', 'SYNC_INTERVAL', 'def sync', 'def run', 'scheduler', 'while True']:
    idx = content.find(keyword)
    if idx >= 0:
        print(f"\n=== '{keyword}' at line ~{content[:idx].count(chr(10))+1} ===")
        print(content[idx:idx+300])
        print("...")
