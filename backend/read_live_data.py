with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def update_live_data')
print(content[idx:idx+1500])
