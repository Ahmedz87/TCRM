import re
s = open(r"C:\broker-crm\backend\meta_sync.py", encoding="utf-8", errors="ignore").read()
# Find the INSERT INTO leads statement
i = s.lower().find("insert into leads")
if i > 0:
    print("=== meta_sync INSERT INTO leads ===")
    print(s[i:i+700])
else:
    print("No 'insert into leads' found. Checking fetch_meta_leads.py...")
    s2 = open(r"C:\broker-crm\backend\fetch_meta_leads.py", encoding="utf-8", errors="ignore").read()
    j = s2.lower().find("insert into leads")
    print(s2[j:j+700] if j>0 else "Not found there either")
