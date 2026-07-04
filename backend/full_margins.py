s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()

# Full get_margins
i = s.find("def get_margins")
j = s.find("\ndef ", i+10)
print("=== FULL get_margins ===")
print(s[i:j])
