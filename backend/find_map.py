p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()
# Find where all_logins is mapped in the dict (not the SELECT)
import re
for m in re.finditer(r'all_logins', s):
    i = m.start()
    snippet = s[i-30:i+120]
    if '"all_logins"' in s[i-30:i+5] or "all_logins\":" in s[i-30:i+15]:
        print("=== MAPPING LINE FOUND ===")
        print(repr(s[i-30:i+150]))
        print()
