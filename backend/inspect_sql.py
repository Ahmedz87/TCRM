p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Show the sort_col line with lead_badge
import re
print("=== Sort line with recapture ===")
i = s.find("THEN 0 ELSE 1")
print(repr(s[i-80:i+60]))

print("\n=== Count query ===")
i = s.find("count_sql")
print(s[i:i+350])

print("\n=== ORDER BY usage ===")
for m in re.finditer(r'ORDER BY', s):
    i = m.start()
    print(repr(s[i:i+60]))
