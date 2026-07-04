import os, re
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import inspect

backend = r"C:\broker-crm\backend"
# Gather all .py files (routers + bridges + main)
files = []
for root, dirs, fs in os.walk(backend):
    if "venv" in root: continue
    for f in fs:
        if f.endswith(".py"):
            files.append(os.path.join(root, f))

# For key tables, find alias.column references
# Common aliases: l=leads, c=clients, d=deals, t=transactions
alias_table = {"l": "leads", "c": "clients", "d": "deals", "t": "transactions", "ta": "trading_accounts"}
refs = {tbl: set() for tbl in alias_table.values()}

for fp in files:
    try:
        s = open(fp, encoding="utf-8", errors="ignore").read()
    except: continue
    for alias, tbl in alias_table.items():
        for m in re.findall(rf'\b{alias}\.(\w+)', s):
            refs[tbl].add(m)

insp = inspect(engine)
print("=== MISSING COLUMNS BY TABLE ===\n")
for tbl, cols in refs.items():
    try:
        existing = {c["name"] for c in insp.get_columns(tbl)}
    except:
        print(f"{tbl}: TABLE MISSING"); continue
    missing = sorted(c for c in cols if c not in existing and len(c) > 1 and not c.isupper())
    if missing:
        print(f"{tbl} missing ({len(missing)}):")
        print(f"  {missing}\n")
