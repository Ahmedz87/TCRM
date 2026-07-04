with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
# Print lines 1-100
print("".join(lines[:100]))
