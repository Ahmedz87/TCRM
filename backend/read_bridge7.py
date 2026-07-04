with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 280-360 where action==2 logic is
print("".join(lines[270:380]))
