s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()

# Find the function that reads a single/all user records (the one with rec.credit at ~L296)
import re
print("=== Functions that read user records (credit) ===")
for m in re.finditer(r'def (\w+)', s):
    fn = m.group(1)
    body = s[m.start():m.start()+1500]
    if "rec.credit" in body or "UserRecordGet" in body or "AdmUsersRequest" in body:
        print(f"  {fn}")

# TradeRecord struct - does it have profit field?
i = s.find("class TradeRecord")
print("\n=== TradeRecord struct (looking for profit) ===")
block = s[i:i+800]
for line in block.split("\n"):
    if "profit" in line.lower() or "_fields_" in line or "login" in line.lower() or "cmd" in line.lower():
        print("  " + line.strip()[:70])

# Show top imports - is Flask imported? what's the V_ index for AdmUsersRequest and balance?
print("\n=== vtable index constants defined (V_*) ===")
for m in re.finditer(r'(V_\w+)\s*=\s*(\d+)', s):
    print(f"  {m.group(1)} = {m.group(2)}")
