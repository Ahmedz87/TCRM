p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix the dict mapping to correct indices from the real query:
# is_flagged=24, assigned_agent_id=25, all_logins=26, lead_badge=27, matched_lead_id=28
fixes = [
    ('"assigned_agent_id": r[23] if len(r)>23 else None,',
     '"assigned_agent_id": r[25] if len(r)>25 else None,'),
    ('"all_logins":          list(r[24]) if len(r)>24 and r[24] else [r[0]],',
     '"all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],'),
    ('"lead_badge":          r[25] if len(r)>25 else None,',
     '"lead_badge":          r[27] if len(r)>27 else None,'),
    ('"matched_lead_id":     r[26] if len(r)>26 else None,',
     '"matched_lead_id":     r[28] if len(r)>28 else None,'),
    ('agent_name_map.get(r[23] if len(r)>23 else None, "")',
     'agent_name_map.get(r[25] if len(r)>25 else None, "")'),
    ('assigned_agent_ids = list({r[23] for r in rows if len(r) > 23 and r[23]})',
     'assigned_agent_ids = list({r[25] for r in rows if len(r) > 25 and r[25]})'),
]
for old, new in fixes:
    if old in s:
        s = s.replace(old, new)
        print(f"Fixed: {new.strip()[:50]}")
    else:
        print(f"NOT FOUND: {old[:50]}")

open(p, "w", encoding="utf-8").write(s)
print("\nSaved.")
