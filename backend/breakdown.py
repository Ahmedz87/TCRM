import psycopg2
import db_config
DB=dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
conn=psycopg2.connect(**DB); cur=conn.cursor()

# Of flagged accounts, how many have bonus credit?
cur.execute("""
  SELECT COUNT(*) FROM hedge_flagged_traders f
  JOIN trading_accounts ta ON ta.login=f.login
  WHERE ta.credit > 0
""")
print("Flagged accounts WITH bonus credit:", cur.fetchone()[0], "of 3196")

# How many have a STRONG link (ip/cid/mqid) to another account?
cur.execute("""
  SELECT COUNT(DISTINCT f.login) FROM hedge_flagged_traders f
  JOIN network_edges ne ON (ne.login_a=f.login OR ne.login_b=f.login)
  WHERE ne.reason IN ('ip','cid','mqid')
""")
print("Flagged accounts with STRONG link (ip/cid/mqid):", cur.fetchone()[0])

# distribution of hedge ratio
cur.execute("""
  SELECT 
    COUNT(*) FILTER (WHERE hedged_ratio>=0.8) as r80,
    COUNT(*) FILTER (WHERE hedged_ratio>=0.6 AND hedged_ratio<0.8) as r60,
    COUNT(*) FILTER (WHERE hedged_ratio>=0.4 AND hedged_ratio<0.6) as r40,
    COUNT(*) FILTER (WHERE hedged_ratio<0.4) as rlow
  FROM hedge_flagged_traders
""")
r=cur.fetchone()
print(f"\nHedge ratio: >=80%: {r[0]}   60-80%: {r[1]}   40-60%: {r[2]}   <40%: {r[3]}")

# how many have BOTH high ratio AND bonus
cur.execute("""
  SELECT COUNT(*) FROM hedge_flagged_traders f
  JOIN trading_accounts ta ON ta.login=f.login
  WHERE ta.credit>0 AND f.hedged_ratio>=0.6
""")
print("High ratio (>=60%) AND bonus credit:", cur.fetchone()[0])
conn.close()
