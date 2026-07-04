import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Add missing columns
for col, typ, default in [
    ("passed_to_agent_id", "INTEGER", "NULL"),
    ("duration_seconds",   "INTEGER", "0"),
]:
    try:
        db.execute(text(f"ALTER TABLE call_actions ADD COLUMN IF NOT EXISTS {col} {typ} DEFAULT {default}"))
        db.commit()
        print(f"✅ Added call_actions.{col}")
    except Exception as e:
        db.rollback()
        print(f"⚠️  {col}: {e}")

db.close()
print("Done!")
