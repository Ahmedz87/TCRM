p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
s = open(p, encoding="utf-8").read()
import re
# Find how pages are imported and rendered
print("=== Page imports ===")
for m in re.finditer(r"import \w+ from './\w+'", s):
    print("  " + m.group(0))
print("\n=== active === checks (page routing) ===")
for m in re.finditer(r"active === '(\w+)'", s):
    print("  active === '" + m.group(1) + "'")
print("\n=== Sidebar menu items (look for label/key) ===")
i = s.find("Trading accounts")
if i > 0:
    print(s[i-200:i+300])
