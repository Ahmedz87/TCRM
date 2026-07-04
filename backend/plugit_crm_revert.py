"""UNDO the CRM-side Plugit level work: restore levels, clear plugit fields, recompute commission."""
import psycopg2, build_ibs
import db_config
conn=db_config.connect();conn.autocommit=True;cur=conn.cursor()
cur.execute("UPDATE ibs SET ib_level = ib_level_before_plugit WHERE ib_level_before_plugit IS NOT NULL")
print("levels restored:", cur.rowcount)
cur.execute("UPDATE ibs SET markup_pips=NULL, plugit_status=NULL, ib_level_before_plugit=NULL WHERE markup_pips IS NOT NULL OR plugit_status IS NOT NULL OR ib_level_before_plugit IS NOT NULL")
print("plugit fields cleared:", cur.rowcount)
cur.execute("DROP TABLE IF EXISTS ib_plugit"); print("ib_plugit table dropped")
print("recomputing commission from restored levels..."); cur.execute(build_ibs.VOLUME_SQL); print("commission rows updated:", cur.rowcount)
cur.execute("SELECT ib_level, COUNT(*) FROM ibs GROUP BY ib_level ORDER BY ib_level")
print("level distribution now:", dict(cur.fetchall()))
cur.close();conn.close()
