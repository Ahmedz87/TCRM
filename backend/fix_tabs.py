p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

old = "{key:'created_at',label:'Newest'},{key:'status',label:'Status'},{key:'name',label:'Name'}"
new = "{key:'created_at',label:'Newest'},{key:'score',label:'Priority'},{key:'status',label:'Status'}"

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Tabs updated: removed Name, added Priority")
    print("Verify:", "label:'Priority'" in s and "label:'Name'" not in s.split("map")[0][-200:])
else:
    print("Tab array not matched exactly, showing current:")
    i = s.find("label:'Newest'")
    print(repr(s[i-30:i+150]))
