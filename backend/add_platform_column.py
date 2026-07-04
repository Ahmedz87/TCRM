"""Add platform column to clients and transactions tables"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.rollback()
try:
    db.execute(text("""
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS platform VARCHAR(10) DEFAULT 'MT5';
        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS platform VARCHAR(10) DEFAULT 'MT5';
        ALTER TABLE trading_accounts ADD COLUMN IF NOT EXISTS platform VARCHAR(10) DEFAULT 'MT5';
    """))
    db.commit()
    print("✓ Platform columns added!")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
