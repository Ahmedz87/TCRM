"""PHASE A.2 — stats + commission for all IBs after the feed. NULL IBs -> 0 commission."""
import psycopg2, build_ibs
import db_config
conn=db_config.connect();conn.autocommit=True;cur=conn.cursor()
# 1) total_clients for every IB (incl. the new ones)
cur.execute("UPDATE ibs SET total_clients = (SELECT COUNT(*) FROM clients c WHERE c.agent = ibs.agent_id)")
print("total_clients refreshed")
# 2) volume + commission from deals (reads ib_level, never writes it)
print("recomputing volume+commission (scans deals)..."); cur.execute(build_ibs.VOLUME_SQL); print("  rows:",cur.rowcount)
# 3) NULL IBs (not eligible) -> hard 0 commission
cur.execute("UPDATE ibs SET total_commission=0, unpaid_commission=0 WHERE plugit_status='null'"); print("null IBs zeroed:",cur.rowcount)
# report
cur.execute("SELECT plugit_status, COUNT(*), COUNT(*) FILTER (WHERE COALESCE(total_clients,0)>0) AS with_clients, ROUND(SUM(total_commission)::numeric,0) FROM ibs GROUP BY plugit_status ORDER BY 2 DESC")
print("status | count | with_clients | total_commission")
for r in cur.fetchall(): print("  ",r)
cur.close();conn.close()
