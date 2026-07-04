p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# Find a param line to anchor the insertion (page is always set)
import re
# Show the param building block
i = s.find("const p = new URLSearchParams")
if i < 0:
    i = s.find("p.set('page'")
    i = s.rfind("\n", 0, i)
j = s.find("apiGet(`/leads", i)
print("=== Param building block ===")
print(s[i:j])
