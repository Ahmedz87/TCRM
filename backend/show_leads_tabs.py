p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
import re
# Find the sort tabs/buttons
print("=== Sort tabs ===")
for kw in ["Newest","Priority","Name","setSort","sortBy","sort ==="]:
    i = s.find(kw)
    if i>0:
        print(f"  '{kw}': ...{s[max(0,i-40):i+60].strip()}...")
