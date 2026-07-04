p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()
# Show the end of the SELECT where we inserted lead_badge
i = s.find("MAX(c.lead_badge)")
if i < 0:
    print("lead_badge NOT in SELECT!")
else:
    print("=== SELECT area around lead_badge ===")
    print(s[i-120:i+250])
