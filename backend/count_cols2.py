p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()
start = s.find("MIN(c.login)")
end = s.find("FROM clients c", start)
block = s[start-20:end]
# Print each line with index of "as xxx" columns
lines = block.split("\n")
idx = 0
for line in lines:
    ls = line.strip().rstrip(",")
    if " as " in ls.lower():
        # take the alias after last ' as '
        alias = ls.lower().rsplit(" as ", 1)[-1].strip()
        print(f"r[{idx}] = {alias}")
        idx += 1
    elif ls and not ls.startswith("SELECT") and "CASE" not in ls and "WHEN" not in ls and "THEN" not in ls and "END" not in ls and "ELSE" not in ls:
        # column without alias (rare)
        pass
print(f"--- total aliased columns: {idx} ---")
