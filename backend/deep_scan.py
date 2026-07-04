import os, re
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import inspect

backend = r"C:\broker-crm\backend"
insp = inspect(engine)

# Python methods / SQL keywords to ignore (false positives)
IGNORE = {"get","lower","upper","strip","split","append","execute","fetchall","fetchone",
    "keys","values","items","replace","join","format","encode","decode","isupper","islower",
    "start","close","commit","rollback","add","update","delete","query","filter","count",
    "conkey","conname","conrelid","contype","relname","oid","description","cursor",
    "includes","map","push","find","slice","length","total_pos","EnDealAction"}

# Real tables and their common aliases in the code
tables = ["leads","clients","deals","transactions","trading_accounts","notifications",
    "neg_cover_log","abuse_cases","network_edges","account_identifiers","users","ibs"]

# Build alias->table from "FROM <table> <alias>" and "JOIN <table> <alias>"
files = [os.path.join(backend,f) for f in os.listdir(backend) if f.endswith(".py") and "venv" not in f]
allcode = ""
for fp in files:
    try: allcode += open(fp,encoding="utf-8",errors="ignore").read() + "\n"
    except: pass

# Find alias mappings
alias_map = {}
for m in re.finditer(r'(?:FROM|JOIN)\s+(\w+)\s+(\w+)\b', allcode):
    tbl, alias = m.group(1), m.group(2)
    if tbl in tables and len(alias) <= 3:
        alias_map[alias] = tbl

print("Alias map found:", alias_map)
print()

# For each alias, collect referenced columns
refs = {t: set() for t in tables}
for alias, tbl in alias_map.items():
    for col in re.findall(rf'\b{alias}\.(\w+)', allcode):
        if col not in IGNORE and not col.isupper() and len(col) > 1:
            refs[tbl].add(col)

print("=== MISSING COLUMNS (real) ===")
for tbl in tables:
    try:
        existing = {c["name"] for c in insp.get_columns(tbl)}
    except:
        print(f"{tbl}: TABLE MISSING"); continue
    missing = sorted(c for c in refs[tbl] if c not in existing)
    if missing:
        print(f"\n{tbl} ({len(missing)}): {missing}")
