p = r"C:\broker-crm\backend\leads_router.py"
lines = open(p, encoding="utf-8").read().split("\n")

lines[50] = "    if badge:"
lines[51] = "        where.append(" + chr(34) + "l.match_badge = :badge" + chr(34) + ")"
lines[52] = "        params[" + chr(34) + "badge" + chr(34) + "] = badge"
lines[53] = "    if platform:"
lines[54] = "        where.append(" + chr(34) + "l.platform = :platform" + chr(34) + ")"
lines[55] = "        params[" + chr(34) + "platform" + chr(34) + "] = platform"

open(p, "w", encoding="utf-8").write("\n".join(lines))
print("Fixed. Verifying...")

import py_compile
try:
    py_compile.compile(p, doraise=True)
    print("leads_router.py compiles OK now")
except py_compile.PyCompileError as e:
    print("STILL BROKEN:", e)
