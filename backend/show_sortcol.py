p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Show current sort_col definitions
import re
print("=== Current sort_col line (the recapture pin) ===")
i = s.find("CASE WHEN MAX(c.lead_badge)")
print(repr(s[i-60:i+130]))

print("\n=== score sort definition ===")
i = s.find('sort == "score"')
print(repr(s[i:i+90]))
