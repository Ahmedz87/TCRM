import db_config
import psycopg2
conn = db_config.connect()
cur = conn.cursor()
# Clear old auto-generated cases (keep any human-reviewed/resolved ones)
cur.execute("DELETE FROM abuse_cases WHERE status NOT IN ('resolved','frozen')")
print(f"Cleared {cur.rowcount} old cases")
conn.commit()
conn.close()
