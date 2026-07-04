p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()
orig = s
changes = []

# 1. Fix score sort to use call_score
if 'sort == "score":' in s and 'COALESCE(call_score,0) DESC' not in s:
    import re
    s = re.sub(r'(elif sort == "score":\s*sort_col = )"[^"]*"', r'\1"COALESCE(call_score,0) DESC, balance DESC"', s)
    changes.append("score sort -> call_score")

# 2. Pin recapture to top (after city sort line)
if "THEN 0 ELSE 1" not in s:
    import re
    m = re.search(r'(elif sort == "city":\s*sort_col = "city ASC")', s)
    if m:
        s = s.replace(m.group(1), m.group(1) + '\n    sort_col = "CASE WHEN lead_badge=\x27recapture\x27 THEN 0 ELSE 1 END ASC, " + sort_col')
        changes.append("pin recapture top")

# 3. Add lead_badge to SELECT before the ck CASE
if "MAX(c.lead_badge)" not in s:
    # find the 'END as ck' and insert before its CASE
    idx = s.find("END as ck")
    case_start = s.rfind("CASE", 0, idx)
    s = s[:case_start] + "MAX(c.lead_badge) as lead_badge,\n            MAX(c.matched_lead_id) as matched_lead_id,\n            " + s[case_start:]
    changes.append("lead_badge in SELECT")

open(p, "w", encoding="utf-8").write(s)
print("File:", p)
print("Changes applied:", changes if changes else "none (may already be patched)")
print("\nNow show the all_logins mapping area so we can fix indices:")
i = s.find('"all_logins"')
if i > 0:
    print(repr(s[i-10:i+200]))
else:
    print("all_logins mapping not found - searching for dict build...")
    i = s.find('"login":')
    print(repr(s[i-10:i+200]))
