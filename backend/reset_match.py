import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
# Reset match_checked_at to NULL so auto-match reprocesses all leads
db.execute(text("UPDATE leads SET match_checked_at = NULL"))
db.commit()
n = db.execute(text("SELECT COUNT(*) FROM leads WHERE match_checked_at IS NULL")).fetchone()[0]
print(f"Reset done. Leads now unchecked: {n:,}")
db.close()
