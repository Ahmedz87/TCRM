p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()
old = """    rows = db.execute(text(f\"\"\"
        SELECT ta.client_id AS client_id, d.login, d.symbol, d.volume, d.deal_time
        FROM deals d
        JOIN trading_accounts ta ON ta.login = d.login
        WHERE d.entry=1 AND d.direction IN ('buy','sell')
          AND d.deal_time >= :s AND d.deal_time < :e
          AND ta.client_id IS NOT NULL
        ORDER BY ta.client_id, d.deal_time
    \"\"\"), {"s": start_ts, "e": end_ts}).fetchall()"""
new = """    rows = db.execute(text(f\"\"\"
        SELECT COALESCE(ta.client_id, c.id) AS client_id, d.login, d.symbol, d.volume, d.deal_time
        FROM deals d
        LEFT JOIN trading_accounts ta ON ta.login = d.login
        LEFT JOIN clients c ON c.login = d.login
        WHERE d.entry=1 AND d.direction IN ('buy','sell')
          AND d.deal_time >= :s AND d.deal_time < :e
          AND COALESCE(ta.client_id, c.id) IS NOT NULL
        ORDER BY COALESCE(ta.client_id, c.id), d.deal_time
    \"\"\"), {"s": start_ts, "e": end_ts}).fetchall()"""
if old in s:
    s = s.replace(old, new); open(p,"w",encoding="utf-8").write(s)
    print("ENGINE join -> COALESCE fallback applied (recovers 88 orphans)")
else:
    print("pattern not found")
import py_compile
py_compile.compile(p, doraise=True); print("compiles OK")
