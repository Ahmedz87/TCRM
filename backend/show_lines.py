p = r"C:\broker-crm\backend\leads_router.py"
s = open(p, encoding="utf-8").read()
lines = s.split("\n")
# Show lines 48-58 with their indentation visible
for i in range(47, 58):
    if i < len(lines):
        print(f"{i+1}: {repr(lines[i])}")
