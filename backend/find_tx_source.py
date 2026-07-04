import sys
sys.path.insert(0, r'C:\broker-crm\backend')

# Check all python files in backend for Transaction writes
import os
backend = r'C:\broker-crm\backend'
for fname in os.listdir(backend):
    if fname.endswith('.py'):
        try:
            with open(os.path.join(backend, fname), 'r', encoding='utf-8') as f:
                content = f.read()
            if 'Transaction(' in content or 'transactions' in content.lower() and 'INSERT' in content.upper():
                # Find the lines
                for i, line in enumerate(content.split('\n')):
                    if 'Transaction(' in line or ('transaction' in line.lower() and ('add' in line.lower() or 'insert' in line.lower())):
                        print(f"{fname}:{i+1}: {line.strip()}")
        except:
            pass
