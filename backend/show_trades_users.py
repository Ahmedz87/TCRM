s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()

i = s.find("def get_open_trades")
j = s.find("\ndef ", i+10)
print("=== get_open_trades (full) ===")
print(s[i:j])

# Show how get_all_users reads ONE user (the loop body with login/balance/credit)
i = s.find("def get_all_users")
j = s.find("\ndef ", i+10)
body = s[i:j]
# print the part that builds the user dict
k = body.find("login")
print("\n=== get_all_users dict-building part ===")
print(body[:1400])
