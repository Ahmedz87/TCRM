import db_config
import psycopg2
c = db_config.connect().cursor()
for t in ["clients","trading_accounts","deals"]:
    c.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"{t}: {c.fetchone()[0]:,}")
# split by platform once it populates
c.execute("SELECT platform, COUNT(*) FROM clients GROUP BY platform")
print("clients by platform:", c.fetchall())
c.execute("SELECT platform, COUNT(*) FROM trading_accounts GROUP BY platform")
print("accounts by platform:", c.fetchall())
