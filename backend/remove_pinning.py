p = r"C:\broker-crm\backend\leads_router.py"
s = open(p, encoding="utf-8").read()

# Remove the recapture pinning prefix from the ORDER BY
old = '''    order = sort_map.get(sort, 'l.created_at DESC')
    # Only RECAPTURE pinned to top; everything else follows the chosen sort.
    # On 'score' (Priority) sort, also lift no-deposit leads up via their score.
    order = """
        CASE WHEN l.match_badge = 'recapture' THEN 0 ELSE 1 END ASC,
    """ + order'''

new = '''    order = sort_map.get(sort, 'l.created_at DESC')
    # No pinning - pure sort. Recaptures rise on Priority via their +50 score.'''

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Removed pinning - pure sort now")
else:
    print("Pinning block not matched - showing current ORDER area:")
    i = s.find("sort_map.get(sort")
    print(repr(s[i:i+300]))
