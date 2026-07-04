"""
inspect_mt4_schema.py — check clients and trading_accounts schema before MT4 import.
Run: python inspect_mt4_schema.py
"""
import psycopg2
import db_config
conn = db_config.connect()
cur = conn.cursor()

def show(title, sql):
    print(f"\n=== {title} ===")
    cur.execute(sql)
    for r in cur.fetchall():
        print(r)

show("clients columns", """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name='clients'
    ORDER BY ordinal_position
""")
show("trading_accounts columns", """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name='trading_accounts'
    ORDER BY ordinal_position
""")
show("clients primary key / unique constraints", """
    SELECT c.conname, c.contype, array_agg(a.attname)
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
    WHERE t.relname = 'clients'
    GROUP BY c.conname, c.contype
""")
show("sample MT5 client with phone", """
    SELECT login, name, phone, platform, group_name
    FROM clients
    WHERE phone IS NOT NULL AND phone != ''
    LIMIT 5
""")
show("phone duplicates (same phone, different logins)", """
    SELECT phone, COUNT(*), array_agg(login)
    FROM clients
    WHERE phone IS NOT NULL AND phone != ''
    GROUP BY phone HAVING COUNT(*) > 1
    LIMIT 5
""")
conn.close()
