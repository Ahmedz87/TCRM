p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()
# Find the all_logins mapping and show 400 chars after
i = s.find('"all_logins":')
print("=== Current mapping block ===")
print(s[i:i+400])
