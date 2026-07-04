import db_config
import psycopg2
c=db_config.connect().cursor()
def show(t,sql):
    print("\n=== "+t+" ===")
    c.execute(sql)
    for r in c.fetchall(): print(r)
show("symbol_category values", "SELECT DISTINCT symbol_category, COUNT(*) FROM deals GROUP BY symbol_category ORDER BY 2 DESC LIMIT 40")
show("symbol + its category", "SELECT DISTINCT symbol, symbol_category FROM deals WHERE symbol_category IS NOT NULL LIMIT 40")
show("account groups", "SELECT DISTINCT group_name, COUNT(*) FROM trading_accounts GROUP BY group_name ORDER BY 2 DESC LIMIT 60")
