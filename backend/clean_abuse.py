import db_config
import psycopg2
conn = db_config.connect()
cur = conn.cursor()
cur.execute("DELETE FROM abuse_cases WHERE abuse_type IN ('device_cluster','cpa_fraud','round_trip')")
print(f"Removed {cur.rowcount} old non-relevant cases")
conn.commit()
conn.close()
