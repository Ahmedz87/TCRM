import db_config
import psycopg2
conn = db_config.connect()
cur = conn.cursor()
print("=== Top MT5 symbols (for base/quote grouping) ===")
cur.execute("""
    SELECT symbol, COUNT(*) FROM deals
    WHERE platform='MT5' AND direction IN ('buy','sell') AND open_time IS NOT NULL
    GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 40
""")
for r in cur.fetchall(): print(f"  {r[0]:14s} {r[1]:,}")
conn.close()
