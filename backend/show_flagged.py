import db_config
import psycopg2
conn=db_config.connect()
cur=conn.cursor()
cur.execute("""
  SELECT login, score, ROUND(hedged_ratio*100) as pct, total_positions, 
         hedged_positions, has_bonus, ROUND(credit) as credit, strong_link, reasons
  FROM hedge_flagged_traders ORDER BY score DESC LIMIT 20
""")
print(f"{'login':>8} {'score':>5} {'hedge%':>6} {'pos':>5} {'bonus':>6} {'link':>5}  reasons")
for r in cur.fetchall():
    print(f"{r[0]:>8} {r[1]:>5} {r[2]:>5}% {r[3]:>5} ${r[6]:>5} {str(r[7])[:1]:>5}  {r[8]}")
conn.close()
