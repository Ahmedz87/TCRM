p = r"C:\broker-crm\frontend\src\App.tsx"
s = open(p, encoding="utf-8").read()
# Show the structure - find header/topbar area, user info, logout etc
import re
print("=== Looking for top bar markers ===")
for kw in ["userName","logout","Logout","header","Header","topbar","user-info","localStorage.getItem('userName')","profile"]:
    i = s.find(kw)
    if i > 0:
        print(f"\n--- '{kw}' at {i} ---")
        print(s[max(0,i-80):i+120])
