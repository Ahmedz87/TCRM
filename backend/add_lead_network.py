p = r"C:\broker-crm\backend\leads_router.py"
s = open(p, encoding="utf-8").read()

# Add network_score from ip_count(r38)*35 + cid_count(r40)*50, capped at 100
anchor = '"match_badge": r[31] or "", "matched_login": r[32], "score": r[33] or 0,'
if anchor in s and '"network_score"' not in s:
    s = s.replace(anchor, anchor + '\n            "network_score": min(100, (r[38] or 0)*35 + (r[40] or 0)*50),')
    open(p, "w", encoding="utf-8").write(s)
    print("network_score added. Verify:", '"network_score"' in s)
else:
    print("already present or anchor missing")
