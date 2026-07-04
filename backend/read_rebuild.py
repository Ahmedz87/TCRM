with open(r'C:\broker-crm\backend\rebuild_db.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find Transaction saving logic
idx = content.find('models.Transaction(')
print(content[idx-200:idx+500])
