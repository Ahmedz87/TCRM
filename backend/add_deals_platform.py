import db_config
import psycopg2
conn = db_config.connect()
cur = conn.cursor()
cur.execute("ALTER TABLE deals ADD COLUMN IF NOT EXISTS platform VARCHAR(10) DEFAULT 'MT5'")
cur.execute("UPDATE deals SET platform='MT5' WHERE platform IS NULL")
conn.commit()
print("deals.platform column added")
cur.execute("SELECT COUNT(*) FROM deals WHERE platform='MT5'")
print(f"MT5 deals: {cur.fetchone()[0]}")
conn.close()
