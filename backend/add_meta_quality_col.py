"""Add separate meta_quality column (qualified/converted/not_qualified/lost)"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.rollback()
try:
    db.execute(text("""
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_quality VARCHAR(30);
    """))
    db.commit()
    print("meta_quality column added!")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
