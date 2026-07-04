import db_config
import psycopg2
c=db_config.connect().cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='trading_accounts' ORDER BY 1")
print([r[0] for r in c.fetchall()])
