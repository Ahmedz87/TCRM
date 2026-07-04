import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Keep only first 13 leads (delete the duplicates added second time)
db.execute(text("DELETE FROM leads WHERE id > 13"))
db.commit()

count = db.execute(text("SELECT COUNT(*) FROM leads")).scalar()
print(f"✅ Cleaned up! Leads now: {count}")
db.close()
