import db_config
import psycopg2
c = db_config.connect()
cur = c.cursor()
# add the columns the meta import needs (IF NOT EXISTS = safe to re-run)
cols = [
    ("status", "VARCHAR(50) DEFAULT 'new'"),
    ("source", "VARCHAR(100)"),
    ("full_name", "VARCHAR(255)"),
    ("email", "VARCHAR(255)"),
    ("phone", "VARCHAR(50)"),
    ("meta_lead_id", "TEXT"),
    ("created_at", "TIMESTAMP DEFAULT NOW()"),
    ("raw_data", "JSONB"),
]
for name, typ in cols:
    try:
        cur.execute(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {name} {typ}")
        print(f"ok: {name}")
    except Exception as e:
        print(f"{name}: {str(e)[:60]}"); c.rollback()
c.commit()
# show final columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='leads' ORDER BY ordinal_position")
print("leads columns:", [r[0] for r in cur.fetchall()])
c.close()
