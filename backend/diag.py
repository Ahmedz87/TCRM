import psycopg2
import db_config
DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
conn = psycopg2.connect(**DB); cur = conn.cursor()

cur.execute("""
    SELECT direction, volume, open_time, deal_time,
           COALESCE(deal_time-open_time, -999) as held,
           COALESCE(position_id, 0) as pid
    FROM deals WHERE login=576497 AND platform='MT5' AND symbol LIKE 'XAUUSD%'
      AND open_time IS NOT NULL
    ORDER BY open_time LIMIT 20
""")
print(f"{'dir':5} {'vol':>5} {'open':>12} {'close':>12} {'held':>7} {'pid':>12}")
for r in cur.fetchall():
    d = r[0] or "?"; v = float(r[1] or 0); o = r[2] or 0; c = r[3] or 0; h = r[4]; p = r[5]
    print(f"{d:5} {v:>5.2f} {o:>12} {c:>12} {h:>7} {p:>12}")

cur.execute("""
    SELECT COUNT(*) FILTER (WHERE deal_time=open_time) as same,
           COUNT(*) FILTER (WHERE deal_time>open_time) as proper,
           COUNT(*) FILTER (WHERE deal_time<open_time) as backwards,
           COUNT(*) as total
    FROM deals WHERE login=576497 AND platform='MT5' AND open_time IS NOT NULL
""")
r=cur.fetchone()
print(f"\nopen==close: {r[0]}   close>open (good): {r[1]}   close<open (bug): {r[2]}   total: {r[3]}")
conn.close()
