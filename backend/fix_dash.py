p = r"C:\broker-crm\backend\portal_router.py"
s = open(p, encoding="utf-8").read()

old = """    deposits = 0.0
    try:
        dep = db.execute(text(\"\"\"
            SELECT COALESCE(SUM(amount),0) FROM portal_money_requests
            WHERE client_id=:id AND kind='deposit'
        \"\"\"), {"id": client_id}).fetchone()
        deposits = float(dep[0] or 0)
    except Exception:
        deposits = 0.0"""

new = """    deposits = 0.0
    try:
        db.execute(text(\"\"\"
            CREATE TABLE IF NOT EXISTS portal_money_requests (
                id SERIAL PRIMARY KEY, client_id INT, login BIGINT, kind VARCHAR(12),
                amount NUMERIC, method VARCHAR(40), status VARCHAR(24) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
        \"\"\"))
        db.commit()
        dep = db.execute(text(\"\"\"
            SELECT COALESCE(SUM(amount),0) FROM portal_money_requests
            WHERE client_id=:id AND kind='deposit'
        \"\"\"), {"id": client_id}).fetchone()
        deposits = float(dep[0] or 0)
    except Exception:
        db.rollback()
        deposits = 0.0"""

if old in s:
    s = s.replace(old, new)
    open(p,"w",encoding="utf-8").write(s)
    print("patched: deposits query now creates table + rolls back on error")
else:
    print("PATTERN NOT FOUND - paste the deposits block from portal_router.py")
import py_compile; py_compile.compile(p, doraise=True); print("compiles OK")
