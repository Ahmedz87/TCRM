import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    cols = db.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='notifications' ORDER BY ordinal_position")).fetchall()
    print("notifications columns:")
    for c in cols:
        print(f"  {c[0]} ({c[1]})")
finally:
    db.close()
