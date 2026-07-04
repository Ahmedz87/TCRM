s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()
lines = s.split("\n")

# Find AdmBalanceFix line numbers
print("=== Lines mentioning balance ops 81-84 ===")
for n, line in enumerate(lines):
    if "AdmBalance" in line or "BalanceFix" in line or "=82" in line or "=81" in line:
        print(f"  L{n}: {line.strip()[:90]}")

# Find MarginLevel struct (class or Structure)
print("\n=== MarginLevel struct location ===")
for n, line in enumerate(lines):
    if "MarginLevel" in line and ("class" in line or "Structure" in line or "_fields_" in line):
        print(f"  L{n}: {line.strip()[:90]}")
        # print next 20 lines (the fields)
        for k in range(n, min(n+22, len(lines))):
            print(f"     {lines[k]}")
        break

# Is there a 'credit' field anywhere in a struct?
print("\n=== 'credit' in structs ===")
for n, line in enumerate(lines):
    if '"credit"' in line or "('credit'" in line or '("credit"' in line:
        print(f"  L{n}: {line.strip()[:90]}")
