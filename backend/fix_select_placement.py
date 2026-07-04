p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# 1. Remove the wrongly-placed lead_badge from count_sql
bad = "SELECT COUNT(*) FROM (\n            SELECT MAX(c.lead_badge) as lead_badge,\n            MAX(c.matched_lead_id) as matched_lead_id,\n            CASE"
good = "SELECT COUNT(*) FROM (\n            SELECT CASE"
if bad in s:
    s = s.replace(bad, good)
    print("1. Removed lead_badge from count query")
else:
    print("1. Count query pattern not found (checking alternate)")

# 2. Find the MAIN data SELECT (the one with MIN(c.login) as login)
# and add lead_badge before ITS ck CASE
main_start = s.find("MIN(c.login)              as login")
if main_start < 0:
    main_start = s.find("MIN(c.login) as login")
if main_start < 0:
    main_start = s.find("MIN(c.login)")
print(f"2. Main SELECT starts at char {main_start}")

# Find the 'END as ck' AFTER main_start
ck_idx = s.find("END as ck", main_start)
print(f"   'END as ck' in main query at char {ck_idx}")

if "MAX(c.lead_badge)" not in s[main_start:ck_idx]:
    case_start = s.rfind("CASE", main_start, ck_idx)
    s = s[:case_start] + "MAX(c.lead_badge)         as lead_badge,\n            MAX(c.matched_lead_id)    as matched_lead_id,\n            " + s[case_start:]
    print("3. Added lead_badge to MAIN SELECT")
else:
    print("3. lead_badge already in main SELECT")

open(p, "w", encoding="utf-8").write(s)
