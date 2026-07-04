with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def get_manager')
print(content[idx:idx+600])
