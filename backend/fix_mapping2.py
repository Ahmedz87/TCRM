p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()

target = '"all_logins":          list(r[27]) if len(r)>27 and r[27] else [r[1]],'
if '"lead_badge":' in s:
    print("lead_badge already mapped, skipping")
elif target in s:
    addition = target + '\n            "lead_badge":          r[28] if len(r)>28 else None,\n            "matched_lead_id":     r[29] if len(r)>29 else None,'
    s = s.replace(target, addition)
    open(p, "w", encoding="utf-8").write(s)
    print("SUCCESS: lead_badge mapping added")
    print("Verify:", '"lead_badge":' in s)
else:
    print("Target still not matching. Raw area:")
    i = s.find('"all_logins"')
    print(repr(s[i:i+90]))
