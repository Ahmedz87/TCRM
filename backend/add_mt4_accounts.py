import db_config
import psycopg2
c = db_config.connect()
cur = c.cursor()

# how many MT4 clients are NOT yet in trading_accounts?
cur.execute("""
    SELECT COUNT(*) FROM clients c
    WHERE c.platform='MT4'
      AND NOT EXISTS (SELECT 1 FROM trading_accounts ta WHERE ta.login=c.login)
""")
missing = cur.fetchone()[0]
print(f"MT4 clients missing from trading_accounts: {missing}")

# insert them, mapping client columns -> trading_accounts columns
cur.execute("""
    INSERT INTO trading_accounts
        (login, name, email, phone, group_name, balance, credit, equity,
         leverage, country, city, last_ip, cid, mqid, agent, reg_date,
         is_active, platform, total_deposits, total_withdrawals, net_deposit,
         kyc_status, risk_score, account_type)
    SELECT
         c.login, c.name, c.email, c.phone, c.group_name, c.balance, c.credit, c.equity,
         c.leverage, c.country, c.city, c.last_ip, c.cid, c.mqid, c.agent, c.reg_date,
         c.is_active, 'MT4', c.total_deposits, c.total_withdrawals, c.net_deposit,
         c.kyc_status, c.risk_score, c.group_name
    FROM clients c
    WHERE c.platform='MT4'
      AND NOT EXISTS (SELECT 1 FROM trading_accounts ta WHERE ta.login=c.login)
""")
inserted = cur.rowcount
c.commit()

cur.execute("SELECT platform, COUNT(*) FROM trading_accounts GROUP BY platform")
print("Inserted:", inserted)
print("Now:", cur.fetchall())
c.close()
