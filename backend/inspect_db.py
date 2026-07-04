import db_config
import psycopg2
conn = db_config.connect()
cur = conn.cursor()

def show(title, sql):
    print("\n=== " + title + " ===")
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    print("COLUMNS:", cols)
    for row in cur.fetchall():
        print(row)

show("one deal row", "SELECT * FROM deals LIMIT 1")
show("distinct symbols", "SELECT DISTINCT symbol FROM deals LIMIT 100")
show("distinct account groups", 'SELECT DISTINCT "group" FROM trading_accounts LIMIT 50')
conn.close()
