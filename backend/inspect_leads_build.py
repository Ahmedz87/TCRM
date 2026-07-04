p = r"C:\broker-crm\backend\leads_router.py"
s = open(p, encoding="utf-8").read()

# Find where the lead dict is built and add a computed network_score + connections
# We compute from ip_count and cid_count that already exist
anchor = '"match_badge": r[31] or "", "matched_login": r[32], "score": r[33] or 0,'
if anchor in s and "network_score" not in s:
    addition = anchor + '''
            "network_score": min(100, (r[40] or 0)*35 + (r[39] or 0)*50) if (len(r)>40) else 0,'''
    # We'll compute properly below instead; placeholder
    print("Will add network via post-processing instead")

# Simpler + safe: add network_score computed in Python after row mapping.
# Find the append point
if "leads.append(" in s:
    print("Found leads.append")
elif "result.append(" in s:
    print("Found result.append")
else:
    # show how leads are collected
    import re
    for m in re.finditer(r'\.append\(', s):
        i=m.start(); print(repr(s[i-30:i+15]))
