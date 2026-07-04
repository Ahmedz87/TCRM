import os
backend = r"C:\broker-crm\backend"
print("=== Matching & scoring scripts ===")
for f in sorted(os.listdir(backend)):
    if not f.endswith(".py"): continue
    low = f.lower()
    if any(k in low for k in ["match","auto","recapture","fix_score","badge"]):
        print("  " + f)
