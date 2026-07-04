p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Count columns in the MAIN select (starts at MIN(c.login))
main_start = s.find("MIN(c.login)")
end = s.find("FROM clients c", main_start)
block = s[main_start:end]

idx = 0
positions = {}
for line in block.split("\n"):
    ls = line.strip().rstrip(",")
    low = ls.lower()
    if " as " in low and "case" not in low and "when" not in low and "then" not in low and "else" not in low and "cast(" not in low:
        alias = low.rsplit(" as ", 1)[-1].strip()
        positions[alias] = idx
        idx += 1

lb = positions.get("lead_badge")
ml = positions.get("matched_lead_id")
print(f"lead_badge at r[{lb}], matched_lead_id at r[{ml}]")
print("Last few columns:")
for a,i in positions.items():
    if i >= idx-5:
        print(f"  r[{i}] = {a}")

# Now add/fix the dict mapping
if lb is not None:
    # remove any old broken lead_badge mapping first
    import re
    s = re.sub(r'\s*"lead_badge":\s*r\[\d+\] if len\(r\)>\d+ else None,', '', s)
    s = re.sub(r'\s*"matched_lead_id":\s*r\[\d+\] if len\(r\)>\d+ else None,', '', s)
    # add correct mapping after all_logins
    target = '"all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],'
    if target in s:
        addition = target + f'\n            "lead_badge":          r[{lb}] if len(r)>{lb} else None,\n            "matched_lead_id":     r[{ml}] if len(r)>{ml} else None,'
        s = s.replace(target, addition)
        print("Mapping added at correct index")
    else:
        print("all_logins target not found, showing area:")
        i = s.find('"all_logins"')
        print(repr(s[i-5:i+120]))
    # ensure +50 boost present
    if 'lead_badge") == "recapture"' not in s:
        s = s.replace(
            'mapped["call_score"] = calc_priority_score(mapped, settings)',
            'mapped["call_score"] = calc_priority_score(mapped, settings)\n        if mapped.get("lead_badge") == "recapture":\n            mapped["call_score"] += 50'
        )
    open(p, "w", encoding="utf-8").write(s)
    print("Saved. Verify:", '"lead_badge":' in s)
