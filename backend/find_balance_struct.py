s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()
lines = s.split("\n")

# Look for any struct related to balance operations (TradeRecord, or a balance struct)
print("=== Structs defined in file ===")
for n, line in enumerate(lines):
    if "class" in line and "Structure" in line:
        print(f"  L{n}: {line.strip()}")

# Show the TradeRecord struct fully (AdmBalanceFix likely uses a TradeRecord with cmd=6 BALANCE)
i = s.find("class TradeRecord")
if i > 0:
    j = s.find("class ", i+10)
    print("\n=== TradeRecord struct ===")
    print(s[i:j][:1500])
