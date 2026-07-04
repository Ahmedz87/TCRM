p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix the mapping indices to match the real SELECT order
s = s.replace(
    '"all_logins":          list(r[27]) if len(r)>27 and r[27] else [r[1]],',
    '"all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],'
)
s = s.replace(
    '"lead_badge":          r[28] if len(r)>28 else None,',
    '"lead_badge":          r[27] if len(r)>27 else None,'
)
s = s.replace(
    '"matched_lead_id":     r[29] if len(r)>29 else None,',
    '"matched_lead_id":     r[28] if len(r)>28 else None,'
)

open(p, "w", encoding="utf-8").write(s)

# Verify
print("all_logins r[26]:", '"all_logins":          list(r[26])' in s)
print("lead_badge r[27]:", '"lead_badge":          r[27]' in s)
print("matched_lead_id r[28]:", '"matched_lead_id":     r[28]' in s)
