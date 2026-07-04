p = r"C:\broker-crm\backend\run_loyalty.py"
s = open(p, encoding="utf-8").read()
import re
# change start date to Jan 1 2026
s = re.sub(r"datetime\.date\(2026, ?5, ?1\)", "datetime.date(2026, 1, 1)", s)
open(p,"w",encoding="utf-8").write(s)
print("start date ->", "Jan 1 2026" if "2026, 1, 1" in s else "unchanged")
