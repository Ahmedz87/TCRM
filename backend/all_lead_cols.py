s = open(r"C:\broker-crm\backend\leads_router.py", encoding="utf-8", errors="ignore").read()
import re
# Find all l.<column> references
cols = set(re.findall(r'\bl\.(\w+)', s))
print("Columns leads_router references on 'l' (leads):")
print(sorted(cols))
