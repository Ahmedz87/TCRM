p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
lines = open(p, encoding="utf-8").read().split("\n")
for i, ln in enumerate(lines, 1):
    if "being built" in ln or ("active !== " in ln and "leads" in ln):
        print(f"LINE {i}: {repr(ln)}")
