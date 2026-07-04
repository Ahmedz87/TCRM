p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
s = s.replace("'Country/City'", "'Country'")
open(p, "w", encoding="utf-8").write(s)
print("Header changed to 'Country' (city shows stacked below in cells)")
