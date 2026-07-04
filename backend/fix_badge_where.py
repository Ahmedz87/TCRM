p = r"C:\broker-crm\backend\leads_router.py"
s = open(p, encoding="utf-8").read()

old = '''    if badge:
        wc += " AND l.match_badge = :badge"
        params["badge"] = badge
'''
new = '''    if badge:
        where.append("l.match_badge = :badge")
        params["badge"] = badge
'''
if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Fixed: badge filter now uses where.append() like other filters")
else:
    print("Old pattern not found - showing current:")
    i = s.find("if badge:")
    print(repr(s[i:i+120]))
