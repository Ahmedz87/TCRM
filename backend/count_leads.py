import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
n = db.execute(text("SELECT COUNT(*) FROM leads")).fetchone()[0]
print(f"leads in database: {n:,}")
db.close()
