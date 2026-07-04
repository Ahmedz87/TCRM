import os
backend = r"C:\broker-crm\backend"
for f in os.listdir(backend):
    if not f.endswith(".py"): continue
    try:
        s = open(os.path.join(backend, f), encoding="utf-8", errors="ignore").read()
    except: continue
    for phrase in ["transactions saved", "deals to process", "Syncing deals after", "Transaction sync"]:
        if phrase in s:
            print(f"{f}: contains '{phrase}'")
