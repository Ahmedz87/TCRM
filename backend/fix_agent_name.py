p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix agent_name lookup r[25] -> r[23]
old = 'agent_name_map.get(r[25] if len(r)>25 else None, "")'
new = 'agent_name_map.get(r[23] if len(r)>23 else None, "")'
if old in s:
    s = s.replace(old, new)
    print("Fixed agent_name -> r[23]")
else:
    # try without exact spacing
    import re
    s2 = re.sub(r'agent_name_map\.get\(r\[25\] if len\(r\)>25 else None', 'agent_name_map.get(r[23] if len(r)>23 else None', s)
    if s2 != s:
        s = s2
        print("Fixed agent_name (regex) -> r[23]")
    else:
        print("agent_name pattern not found")

# Also check assigned_agent_ids list builder around r[25]
import re
for m in re.finditer(r'r\[25\]', s):
    i = m.start()
    print("Remaining r[25]:", repr(s[max(0,i-45):i+15]))

open(p, "w", encoding="utf-8").write(s)
print("Saved.")
