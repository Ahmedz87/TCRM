p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix the trailing dict indices to match real SELECT:
# assigned_agent_id -> r[23], all_logins -> r[24], lead_badge -> r[25], matched_lead_id -> r[26]
fixes = [
    ('"assigned_agent_id": r[25] if len(r)>25 else None,',
     '"assigned_agent_id": r[23] if len(r)>23 else None,'),
    ('"all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],',
     '"all_logins":          list(r[24]) if len(r)>24 and r[24] else [r[0]],'),
    ('"lead_badge":          r[25] if len(r)>25 else None,',
     '"lead_badge":          r[25] if len(r)>25 else None,'),
    ('"matched_lead_id":     r[26] if len(r)>26 else None,',
     '"matched_lead_id":     r[26] if len(r)>26 else None,'),
]
for old, new in fixes:
    if old in s:
        s = s.replace(old, new)
        print(f"Fixed: {new.strip()[:40]}")
    else:
        print(f"NOT FOUND: {old[:40]}")

# Also check agent_name which uses r[25]
import re
for m in re.finditer(r'r\[25\]', s):
    i = m.start()
    ctx = s[max(0,i-40):i+20]
    if "agent_name" in ctx:
        print("agent_name uses r[25], should be r[23]:", repr(ctx))

open(p, "w", encoding="utf-8").write(s)
print("\nSaved.")
