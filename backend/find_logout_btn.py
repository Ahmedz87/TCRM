p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
s = open(p, encoding="utf-8").read()
import re
# Find where onLogout is USED in JSX (the button), not the prop definition
matches = [m.start() for m in re.finditer(r'onLogout', s)]
print(f"onLogout appears {len(matches)} times")
for i in matches:
    ctx = s[max(0,i-60):i+120]
    if "onClick" in ctx or "button" in ctx.lower() or "=>" in ctx:
        print(f"\n--- USAGE at {i} ---")
        print(ctx)
