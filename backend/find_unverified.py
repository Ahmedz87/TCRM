import db_config
import psycopg2
c = db_config.connect().cursor()
c.execute("SELECT id, name, kyc_status FROM clients WHERE kyc_status='pending' OR kyc_status IS NULL LIMIT 5")
for r in c.fetchall():
    print(r)
