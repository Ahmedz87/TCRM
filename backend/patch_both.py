p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()
orig = s
c = []
if "d.direction IN (\x27buy\x27,\x27sell\x27)" in s:
    s = s.replace("d.direction IN (\x27buy\x27,\x27sell\x27)", "d.action IN (0,1)"); c.append("dir->action")
if "d.direction IN (\x27buy\x27, \x27sell\x27)" in s:
    s = s.replace("d.direction IN (\x27buy\x27, \x27sell\x27)", "d.action IN (0,1)"); c.append("dir->action2")
if "JOIN trading_accounts ta ON ta.login = d.login\n        WHERE" in s and "LEFT JOIN clients c" not in s:
    s = s.replace(
        "SELECT ta.client_id AS client_id, d.login, d.symbol, d.volume, d.deal_time\n        FROM deals d\n        JOIN trading_accounts ta ON ta.login = d.login",
        "SELECT COALESCE(ta.client_id, c.id) AS client_id, d.login, d.symbol, d.volume, d.deal_time\n        FROM deals d\n        LEFT JOIN trading_accounts ta ON ta.login = d.login\n        LEFT JOIN clients c ON c.login = d.login")
    s = s.replace("AND ta.client_id IS NOT NULL", "AND COALESCE(ta.client_id, c.id) IS NOT NULL")
    s = s.replace("ORDER BY ta.client_id, d.deal_time", "ORDER BY COALESCE(ta.client_id, c.id), d.deal_time")
    c.append("coalesce")
if s != orig: open(p,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(p, doraise=True)
print("Applied:", c if c else "nothing")
print("action filter:", "d.action IN (0,1)" in s, "| COALESCE:", "LEFT JOIN clients c" in s, "| compiles OK")
