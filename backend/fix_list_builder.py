p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix the assigned_agent_ids list builder: r[25] -> r[23]
old = 'assigned_agent_ids = list({r[25] for r in rows if len(r) > 25 and r[25]})'
new = 'assigned_agent_ids = list({r[23] for r in rows if len(r) > 23 and r[23]})'
if old in s:
    s = s.replace(old, new)
    print("Fixed assigned_agent_ids list builder -> r[23]")
else:
    print("List builder pattern not found, showing:")
    i = s.find("assigned_agent_ids = list")
    print(repr(s[i:i+80]))

open(p, "w", encoding="utf-8").write(s)

# Final check: show all remaining r[25] and confirm only lead_badge uses it
import re
print("\n=== Remaining r[25] references ===")
for m in re.finditer(r'r\[25\]', s):
    i = m.start()
    print(" ", repr(s[max(0,i-35):i+12]))
print("\n(Only lead_badge should use r[25] now)")
