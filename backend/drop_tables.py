"""
drop_tables.py — one-off: drop the legacy hedge_* tables so they can be recreated with a new
schema. DESTRUCTIVE. Guarded so an accidental `python drop_tables.py` cannot drop live tables.
Run with:  python drop_tables.py --yes
"""
import sys
import db_config
import psycopg2

TABLES = ["hedge_flagged_traders", "hedge_trades"]

if "--yes" not in sys.argv:
    print("Refusing to run without confirmation.")
    print(f"This will DROP the following tables on the LIVE DB: {', '.join(TABLES)}")
    print("Re-run with:  python drop_tables.py --yes")
    sys.exit(1)

conn = db_config.connect()
cur = conn.cursor()
for t in TABLES:
    cur.execute(f"DROP TABLE IF EXISTS {t}")
conn.commit()
conn.close()
print("Old tables dropped, will be recreated with new schema")
