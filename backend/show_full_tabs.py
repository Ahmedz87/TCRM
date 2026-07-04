p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
i = s.find("{key:'created_at',label:'Newest'}")
# show the full tab array
j = s.find("]", i)
print("=== Full tab array ===")
print(s[i-30:j+5])
