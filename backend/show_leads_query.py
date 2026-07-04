import sys
sys.path.insert(0, r"C:\broker-crm\backend")
# Find the main SELECT in leads_router and run a piece of it
s = open(r"C:\broker-crm\backend\leads_router.py", encoding="utf-8", errors="ignore").read()
# Show the SELECT columns the router uses
i = s.find("SELECT")
j = s.find("FROM leads", i)
if i > 0 and j > 0:
    print("=== leads_router SELECT (first one) ===")
    print(s[i:j+60])
