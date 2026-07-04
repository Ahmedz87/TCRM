import db_config
import psycopg2
conn = db_config.connect()
c = conn.cursor()
for tbl in ["clients", "trading_accounts"]:
    try:
        c.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS platform VARCHAR(10)")
        print(f"  {tbl}.platform added (or already existed)")
    except Exception as e:
        print(f"  {tbl}: {e}")
        conn.rollback()
conn.commit()
# verify
for tbl in ["clients", "trading_accounts"]:
    c.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{tbl}' AND column_name='platform'")
    print(f"  {tbl} has platform:", bool(c.fetchone()))
conn.close()
print("DONE")
