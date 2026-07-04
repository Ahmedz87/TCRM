p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Remove the entire live flat-check block (from its comment to just before the Sort comment)
start = s.find("    # Live flat-check via bridge ONLY for credit-eligible accounts")
end = s.find("    # Sort: eligible first", start)
if start > 0 and end > start:
    s = s[:start] + s[end:]
    open(p, "w", encoding="utf-8").write(s)
    print("Removed live flat-check block — scan is now pure DB (fast)")
else:
    print(f"Block boundaries not found (start={start}, end={end})")

# Verify it's gone
print("Live flat-check still present:", "Live flat-check via bridge" in s)

import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
