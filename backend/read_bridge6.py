with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Search for transaction-related saving
for kw in ['Transaction', 'transaction', 'deposit', 'withdrawal', 'Action == 2', 'action == 2', 'balance', 'tx_type', 'tx_date', 'upsert_transaction', 'save_transaction']:
    idx = content.find(kw)
    if idx >= 0:
        line = content[:idx].count('\n') + 1
        print(f"\n=== '{kw}' line {line} ===")
        print(content[idx:idx+200])
