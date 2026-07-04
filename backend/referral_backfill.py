"""Safe attribution: link ONLY unattributed clients (agent=0) whose utm_campaign matches a
referral link, to that IB. Never overwrites an existing agent."""
import psycopg2
import db_config
conn = db_config.connect()
cur = conn.cursor()
cur.execute("""
  UPDATE clients c SET agent = i.agent_id
  FROM ib_referral_links r JOIN ibs i ON i.id = r.ib_id
  WHERE r.campaign_code = c.utm_campaign
    AND COALESCE(c.agent,0) = 0
""")
print("clients attributed to their referral IB:", cur.rowcount)
conn.commit()
cur.close(); conn.close()
