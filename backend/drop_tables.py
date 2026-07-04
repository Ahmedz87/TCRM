import db_config
import psycopg2
conn=db_config.connect()
cur=conn.cursor()
cur.execute("DROP TABLE IF EXISTS hedge_flagged_traders")
cur.execute("DROP TABLE IF EXISTS hedge_trades")
conn.commit(); conn.close()
print("Old tables dropped, will be recreated with new schema")
