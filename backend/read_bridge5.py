with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def deals_to_db')
print(content[idx:idx+3000])
