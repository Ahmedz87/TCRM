import psycopg2
import db_config
DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
conn = psycopg2.connect(**DB); cur = conn.cursor()

# direction on ENTRY deals (entry=0) - this is the true position direction
cur.execute("""SELECT direction, COUNT(*) FROM deals WHERE login=576497 AND platform='MT5'
   AND entry=0 GROUP BY direction""")
print("direction on ENTRY rows (entry=0):", cur.fetchall())

# action values on entry deals (0=buy,1=sell in MT5)
cur.execute("""SELECT action, COUNT(*) FROM deals WHERE login=576497 AND platform='MT5'
   AND entry=0 GROUP BY action""")
print("action on ENTRY rows:", cur.fetchall())

# action on exit deals
cur.execute("""SELECT action, COUNT(*) FROM deals WHERE login=576497 AND platform='MT5'
   AND entry=1 GROUP BY action""")
print("action on EXIT rows:", cur.fetchall())

# Can we join entry->exit by position_id to get a clean position?
cur.execute("""
  SELECT e.position_id, e.direction as entry_dir, e.action as entry_act,
         e.deal_time as open_t, x.deal_time as close_t, x.profit, x.volume, x.symbol
  FROM deals e JOIN deals x ON e.position_id=x.position_id
  WHERE e.login=576497 AND e.entry=0 AND x.entry=1 AND e.platform='MT5'
  LIMIT 8
""")
print("\nentry->exit joined positions:")
for r in cur.fetchall():
    print(f"  pid={r[0]} dir={r[1]} act={r[2]} open={r[3]} close={r[4]} held={r[4]-r[3]}s sym={r[7]} vol={float(r[6] or 0):.2f}")
conn.close()
