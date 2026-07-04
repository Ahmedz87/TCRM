"""Recompute stored total_commission/unpaid/volume from the (Excel-updated) ib_level.
Reuses build_ibs.VOLUME_SQL which reads i.ib_level and never writes it."""
import psycopg2, build_ibs
import db_config
conn = db_config.connect(); cur = conn.cursor()
print("Recomputing volume + commission from deals (scans trade history)...")
cur.execute(build_ibs.VOLUME_SQL); conn.commit()
print("rows updated:", cur.rowcount)
cur.execute("SELECT ib_level, COUNT(*), round(SUM(total_commission)::numeric,0) FROM ibs GROUP BY ib_level ORDER BY ib_level")
print("level | ibs | total_commission")
for lv,c,comm in cur.fetchall(): print(f"  IB-{lv}: {c} ibs, ${float(comm or 0):,.0f}")
cur.close(); conn.close()
