import os, re
backend = r"C:\broker-crm\backend"
# Search all py files for transaction-related logic
for f in os.listdir(backend):
    if not f.endswith(".py") or "venv" in f: continue
    fp = os.path.join(backend, f)
    try:
        s = open(fp, encoding="utf-8", errors="ignore").read()
    except: continue
    if "INSERT INTO transactions" in s or "transactions to process" in s or "new transactions" in s:
        print(f"=== {f} has transaction logic ===")
        i = s.find("INSERT INTO transactions")
        if i > 0:
            print(s[max(0,i-150):i+200])
        print()
