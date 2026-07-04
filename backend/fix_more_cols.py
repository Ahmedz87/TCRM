import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text

adds = [
    ("leads", "agent_id", "INTEGER"),
    ("leads", "called_at", "TIMESTAMP"),
    ("leads", "family_count", "INTEGER DEFAULT 0"),
    ("leads", "ib_name", "VARCHAR"),
    ("leads", "network_score", "INTEGER DEFAULT 0"),
    ("leads", "outcome", "VARCHAR"),
    ("clients", "ib_name", "VARCHAR"),
    ("clients", "is_islamic", "BOOLEAN DEFAULT FALSE"),
    ("clients", "mt_registration", "VARCHAR"),
    ("clients", "score", "INTEGER DEFAULT 0"),
]
for tbl, col, typ in adds:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {typ}"))
        print(f"  OK: {tbl}.{col}")
    except Exception as e:
        print(f"  ERR {tbl}.{col}: {str(e)[:60]}")
print("Done.")
