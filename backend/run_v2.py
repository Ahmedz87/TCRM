from database import SessionLocal
from abuse_detectors_v2 import run_v2_detectors
import db_config
db = SessionLocal()
print("Running detection with cross-account farm detection...")
print(run_v2_detectors(db))
import psycopg2
conn = db_config.connect()
cur = conn.cursor()
cur.execute("SELECT abuse_type, severity, COUNT(*) FROM abuse_cases GROUP BY abuse_type, severity ORDER BY abuse_type, severity")
print("\nCases by type/severity:")
for r in cur.fetchall(): print(f"  {r[0]:14s} {r[1]:9s} {r[2]}")
conn.close(); db.close()
