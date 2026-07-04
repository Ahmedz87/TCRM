import db_config
import psycopg2
c=db_config.connect().cursor()
c.execute("SELECT symbol_category, COUNT(*) FROM deals GROUP BY symbol_category ORDER BY 2 DESC LIMIT 30")
rows=c.fetchall()
print("symbol_category | count")
for r in rows: print(r)
print("\nTOTAL distinct categories:", len(rows))
print("All NULL?", all(r[0] is None for r in rows))
