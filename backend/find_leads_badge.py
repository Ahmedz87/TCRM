p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
i = s.find("RECAPTURE")
if i < 0:
    print("RECAPTURE not found in file at all")
else:
    print("=== Context around RECAPTURE ===")
    print(repr(s[i-60:i+30]))
