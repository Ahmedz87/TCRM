p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
s = open(p, encoding="utf-8").read()
import re
print("=== Top bar markers in Dashboard.tsx ===")
for kw in ["onLogout","userName","Logout","🔔","topBar","header","localStorage.getItem('userName')"]:
    i = s.find(kw)
    if i > 0:
        print(f"\n--- '{kw}' at {i} ---")
        print(s[max(0,i-100):i+150])
        break_after = kw
