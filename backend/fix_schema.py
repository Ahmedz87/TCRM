import db_config
import psycopg2
c = db_config.connect()
cur = c.cursor()
for t in ["clients","trading_accounts"]:
    cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS platform VARCHAR(10)")
    try:
        cur.execute(f"ALTER TABLE {t} ALTER COLUMN mqid TYPE TEXT USING mqid::TEXT")
    except Exception as e:
        print(t,"mqid:",str(e)[:50]); c.rollback()
c.commit(); print("schema fixes applied")
