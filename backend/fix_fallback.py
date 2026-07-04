p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
s = open(p, encoding="utf-8").read()
old = "active !== 'abuse' && active !== 'leads' && ("
new = "active !== 'abuse' && active !== 'leads' && active !== 'loyalty' && active !== 'neg_balance' && ("
if old in s:
    s = s.replace(old, new)
    open(p,"w",encoding="utf-8").write(s)
    print("FIXED: loyalty + neg_balance added to fallback exclusion")
else:
    print("pattern not found - paste the exact line 702")
