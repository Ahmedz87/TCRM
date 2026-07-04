import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text

adds = [
    ("leads", "is_verified", "BOOLEAN DEFAULT FALSE"),
    ("leads", "phone_verified", "BOOLEAN DEFAULT FALSE"),
    ("leads", "email_verified", "BOOLEAN DEFAULT FALSE"),
    ("leads", "ip_count", "INTEGER DEFAULT 0"),
    ("leads", "cid_count", "INTEGER DEFAULT 0"),
]
for tbl, col, typ in adds:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {typ}"))
        print(f"  OK: {tbl}.{col}")
    except Exception as e:
        print(f"  ERR {tbl}.{col}: {str(e)[:60]}")
print("Done.")
