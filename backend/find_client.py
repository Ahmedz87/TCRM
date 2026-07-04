import db_config
import psycopg2
c = db_config.connect().cursor()
c.execute("SELECT id, name, email, phone FROM clients WHERE name ILIKE %s LIMIT 5", ("%Ahmed Zaman%",))
rows = c.fetchall()
if rows:
    for r in rows: print(r)
else:
    print("No 'Ahmed Zaman' yet - here are 5 sample clients:")
    c.execute("SELECT id, name FROM clients WHERE name IS NOT NULL AND name != '' LIMIT 5")
    for r in c.fetchall(): print(r)
