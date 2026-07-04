p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()
c = []

# The loop must unpack 6 columns now (group_name added) and apply cent /10
old_loop = "    for client_id, login, symbol, volume, deal_time in rows:"
new_loop = "    for client_id, login, symbol, volume, deal_time, group_name in rows:"
if old_loop in s:
    s = s.replace(old_loop, new_loop); c.append("unpack-6col")

# Ensure cent divide exists right after lots is computed
if "/ 10.0" not in s and "lots = float(volume or 0) / 10000.0" in s:
    s = s.replace(
        "        lots = float(volume or 0) / 10000.0\n",
        "        lots = float(volume or 0) / 10000.0\n        if group_name and \x27cent\x27 in group_name.lower():\n            lots = lots / 10.0\n",
        1)
    c.append("cent-divide")

open(p,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(p, doraise=True)
print("patched:", c)
print("unpacks 6col:", new_loop in s, "| cent divide:", "/ 10.0" in s)
