s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()

# Show the UserRecord struct (has credit at L120) - find the class
lines = s.split("\n")
# Find which struct contains the credit field at L120
for n in range(120, 80, -1):
    if "class" in lines[n] and "Structure" in lines[n]:
        print(f"=== Credit's struct: {lines[n].strip()} (at L{n}) ===")
        break

# Show get_all_users fully (how it reads a user record incl credit)
i = s.find("def get_all_users")
j = s.find("\ndef ", i+10)
print("\n=== get_all_users ===")
print(s[i:j][:1200])

# Show get_open_trades
i = s.find("def get_open_trades")
j = s.find("\ndef ", i+10)
print("\n=== get_open_trades ===")
print(s[i:j][:900])
