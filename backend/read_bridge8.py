with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find where transactions table is written
for i, line in enumerate(lines):
    if 'Transaction' in line or 'transactions' in line.lower() or 'tx_type' in line:
        print(f"Line {i+1}: {line.rstrip()}")
