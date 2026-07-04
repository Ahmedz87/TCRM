import psycopg2
import db_config
DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
conn = psycopg2.connect(**DB); cur = conn.cursor()

# Is there an 'entry' column to distinguish open vs close deals?
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='deals' AND column_name IN ('entry','deal_type','action')")
print("distinguishing cols:", [r[0] for r in cur.fetchall()])

# Look at entry values for 576497
cur.execute("SELECT entry, COUNT(*) FROM deals WHERE login=576497 AND platform='MT5' AND open_time IS NOT NULL GROUP BY entry")
print("entry values:", cur.fetchall())

# The proper positions = rows where close > open (exit deals). Count them.
cur.execute("""SELECT COUNT(*) FROM deals WHERE login=576497 AND platform='MT5'
   AND open_time IS NOT NULL AND deal_time > open_time""")
print("proper position rows (close>open):", cur.fetchone()[0])

# Check direction is populated on those
cur.execute("""SELECT direction, COUNT(*) FROM deals WHERE login=576497 AND platform='MT5'
   AND open_time IS NOT NULL AND deal_time > open_time GROUP BY direction""")
print("direction on exit rows:", cur.fetchall())
conn.close()
