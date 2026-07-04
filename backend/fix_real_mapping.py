p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Count columns in the main SELECT to find lead_badge index
start = s.find("MIN(c.login)")
end = s.find("FROM clients c", start)
block = s[start-20:end]
idx = 0
positions = {}
for line in block.split("\n"):
    ls = line.strip().rstrip(",")
    if " as " in ls.lower():
        alias = ls.lower().rsplit(" as ", 1)[-1].strip()
        positions[alias] = idx
        idx += 1
print("Column indices:")
for a, i in positions.items():
    if a in ("all_logins","lead_badge","matched_lead_id","ck") or i >= idx-5:
        print(f"  r[{i}] = {a}")

lb_idx = positions.get("lead_badge")
ml_idx = positions.get("matched_lead_id")
print(f"\nlead_badge at r[{lb_idx}], matched_lead_id at r[{ml_idx}]")

# Add the mapping using correct indices
if '"lead_badge":' not in s and lb_idx is not None:
    target = '"all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],'
    addition = target + f'\n            "lead_badge":          r[{lb_idx}] if len(r)>{lb_idx} else None,\n            "matched_lead_id":     r[{ml_idx}] if len(r)>{ml_idx} else None,'
    s = s.replace(target, addition)
    # add +50 boost
    s = s.replace(
        'mapped["call_score"] = calc_priority_score(mapped, settings)',
        'mapped["call_score"] = calc_priority_score(mapped, settings)\n        if mapped.get("lead_badge") == "recapture":\n            mapped["call_score"] += 50'
    )
    open(p, "w", encoding="utf-8").write(s)
    print("\nMapping + boost added!")
    print("Verify lead_badge mapped:", '"lead_badge":' in s)
else:
    print("\nAlready mapped or index missing")
