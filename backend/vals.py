import db_config
import psycopg2
c=db_config.connect().cursor()
def show(t,sql):
    print("\n=== "+t+" ===")
    c.execute(sql)
    for r in c.fetchall(): print(r)
show("account_type values", "SELECT account_type, COUNT(*) FROM trading_accounts GROUP BY account_type ORDER BY 2 DESC")
show("group_name values", "SELECT group_name, COUNT(*) FROM trading_accounts GROUP BY group_name ORDER BY 2 DESC LIMIT 40")
show("agent / is_ib sample", "SELECT login, name, is_ib, agent FROM trading_accounts WHERE is_ib = true LIMIT 10")
