p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()
c = []

# 1. action filter (in case still on direction)
if "d.direction IN" in s:
    import re
    s = re.sub(r"d\.direction IN \(\x27buy\x27,\s*\x27sell\x27\)", "d.action IN (0,1)", s); c.append("action")

# 2. add group_name to SELECT + CENT divide-by-10
if "COALESCE(ta.group_name" not in s:
    s = s.replace(
        "SELECT COALESCE(ta.client_id, c.id) AS client_id, d.login, d.symbol, d.volume, d.deal_time\n        FROM deals d",
        "SELECT COALESCE(ta.client_id, c.id) AS client_id, d.login, d.symbol, d.volume, d.deal_time,\n               COALESCE(ta.group_name, c.group_name, \x27\x27) AS group_name\n        FROM deals d")
    c.append("group-select")
if "for client_id, login, symbol, volume, deal_time in rows:" in s:
    s = s.replace(
        "    for client_id, login, symbol, volume, deal_time in rows:\n        # MT5 volume is stored in units where 1.00 standard lot = 10,000\n        # (the minimum 0.01 lot = volume 100). So lots = volume / 10,000.\n        lots = float(volume or 0) / 10000.0\n        eligible = is_eligible(symbol)",
        "    for client_id, login, symbol, volume, deal_time, group_name in rows:\n        lots = float(volume or 0) / 10000.0\n        if group_name and \x27cent\x27 in group_name.lower():\n            lots = lots / 10.0\n        eligible = is_eligible(symbol)")
    c.append("cent-divide")

open(p,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(p, doraise=True)
print("engine patched:", c)
print("has group_name select:", "COALESCE(ta.group_name" in s, "| has cent divide:", "/ 10.0" in s, "| action:", "d.action IN (0,1)" in s)
