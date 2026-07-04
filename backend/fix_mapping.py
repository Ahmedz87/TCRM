p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()

# Find the all_logins mapping line and add lead_badge after it
target = '"all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],'
if target in s and '"lead_badge":' not in s:
    addition = target + '\n            "lead_badge":          r[27] if len(r)>27 else None,\n            "matched_lead_id":     r[28] if len(r)>28 else None,'
    s = s.replace(target, addition)
    print("Added lead_badge mapping")
else:
    print("Target not found or already present. Searching alternatives...")
    # show the area around all_logins
    i = s.find("all_logins")
    print(s[i-100:i+200])

# Also ensure the +50 boost is in calc
boost_anchor = 'mapped["call_score"] = calc_priority_score(mapped, settings)'
if boost_anchor in s and 'lead_badge") == "recapture"' not in s:
    s = s.replace(
        boost_anchor,
        boost_anchor + '\n        if mapped.get("lead_badge") == "recapture":\n            mapped["call_score"] += 50'
    )
    print("Added +50 recapture boost")

open(p, "w", encoding="utf-8").write(s)
print("Done. lead_badge mapped:", '"lead_badge":' in s)
