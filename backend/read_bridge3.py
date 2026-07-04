with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Print sync_loop full function
idx = content.find('def sync_loop')
print(content[idx:idx+2000])
