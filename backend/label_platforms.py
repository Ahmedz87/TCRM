import db_config
import psycopg2
c = db_config.connect()
cur = c.cursor()
# label existing trading_accounts: MT4 if the client is MT4, else MT5
cur.execute("UPDATE trading_accounts ta SET platform='MT4' FROM clients c WHERE c.login=ta.login AND c.platform='MT4'")
cur.execute("UPDATE trading_accounts SET platform='MT5' WHERE platform IS NULL OR platform=''")
c.commit()
cur.execute("SELECT platform, COUNT(*) FROM trading_accounts GROUP BY platform")
print(cur.fetchall())
c.close()
