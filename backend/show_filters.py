p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
# Find the filter dropdowns area
i = s.find("filterVerified")
print("=== Filter area sample ===")
print(s[i-100:i+300] if i>0 else "not found")
