p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
# Find the CID cell (last data cell before Actions)
i = s.find("cid_count")
print("=== Around CID cell ===")
print(repr(s[i-200:i+250]))
