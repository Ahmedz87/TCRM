p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()

# Extract the main SELECT ... FROM clients c block
start = s.find("SELECT\n            MIN(c.login)")
end = s.find("FROM clients c", start)
block = s[start:end]

# Count the columns (lines with 'as ')
import re
cols = []
for line in block.split("\n"):
    line = line.strip()
    m = re.search(r'\bas\s+(\w+)\s*,?\s*$', line)
    if m:
        cols.append(m.group(1))
print(f"Total columns in SELECT: {len(cols)}")
for idx, c in enumerate(cols):
    print(f"  r[{idx}] = {c}")
