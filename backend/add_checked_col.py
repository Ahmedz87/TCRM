import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.rollback()
try:
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS match_checked_at TIMESTAMP;"))
    # Mark all currently-matched leads as already checked
    db.execute(text("UPDATE leads SET match_checked_at = NOW() WHERE match_badge IS NOT NULL"))
    db.commit()
    print("Added match_checked_at and marked existing matches as checked")
except Exception as e:
    db.rollback(); print(f"Error: {e}")
finally: db.close()
