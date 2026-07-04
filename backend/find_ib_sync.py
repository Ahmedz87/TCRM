import os
backend = r"C:\broker-crm\backend"
for f in sorted(os.listdir(backend)):
    if not f.endswith(".py"): continue
    try:
        s = open(os.path.join(backend,f), encoding="utf-8", errors="ignore").read()
    except: continue
    if "INSERT INTO ibs" in s or "INTO ibs " in s or "ib_profiles" in s.lower():
        print(f"  {f} - handles IBs")
