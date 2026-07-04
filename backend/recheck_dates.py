import db_config
import psycopg2, datetime
conn = db_config.connect()
cur = conn.cursor()

# Re-check the date range of TRADES (entry deals), not all deals
print("=== TRADE deals (entry IN 0,1, real buy/sell) by month ===")
cur.execute("""
  SELECT to_char(to_timestamp(deal_time),'YYYY-MM') as mon, COUNT(*)
  FROM deals
  WHERE direction IN ('buy','sell')
  GROUP BY mon ORDER BY mon
""")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]:,}")

print("\n=== ALL deals (incl balance ops) by month, 2026 only ===")
cur.execute("""
  SELECT to_char(to_timestamp(deal_time),'YYYY-MM') as mon, COUNT(*)
  FROM deals
  WHERE deal_time >= %s
  GROUP BY mon ORDER BY mon
""", (int(datetime.datetime(2026,1,1).timestamp()),))
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]:,}")

# total trade count now
cur.execute("SELECT COUNT(*) FROM deals WHERE direction IN ('buy','sell')")
print(f"\nTotal trade deals (buy/sell): {cur.fetchone()[0]:,}")
conn.close()
