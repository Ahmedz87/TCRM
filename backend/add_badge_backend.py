p = r"C:\broker-crm\backend\leads_router.py"
s = open(p, encoding="utf-8").read()

# Add badge query param + WHERE clause
if 'badge:' not in s and 'badge ' not in s.split('def get_leads')[1][:500]:
    # Add to function signature after sort
    s = s.replace(
        'sort:      str   = Query("created_at"),',
        'sort:      str   = Query("created_at"),\n    badge:     str   = Query(""),',
        1
    )
    print("1. badge param added to signature")

# Add WHERE clause for badge (find where other filters add to where/params)
if "match_badge = :badge" not in s:
    # find a good anchor - where verified or another filter builds the where
    anchor = None
    for cand in ['if verified:', 'if platform:', 'if source:']:
        if cand in s:
            anchor = cand
            break
    if anchor:
        i = s.find(anchor)
        insert = '''    if badge:
        wc += " AND l.match_badge = :badge"
        params["badge"] = badge
'''
        s = s[:i] + insert + s[i:]
        print(f"2. badge WHERE clause added before '{anchor}'")
    else:
        print("2. Could not find filter anchor - showing where-building area")
        i = s.find("wc")
        print(repr(s[i:i+150]))

open(p, "w", encoding="utf-8").write(s)
print("Verify badge filter:", "match_badge = :badge" in s)
