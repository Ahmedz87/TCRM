import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.rollback()
try:
    # Flag to exclude an account from auto/sweep cover
    db.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS no_auto_cover BOOLEAN DEFAULT FALSE;"))
    # Log table for cover history
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS neg_cover_log (
            id SERIAL PRIMARY KEY,
            login BIGINT,
            platform VARCHAR(10),
            deficit NUMERIC,
            cover_amount NUMERIC,
            balance_before NUMERIC,
            credit_before NUMERIC,
            balance_after NUMERIC,
            credit_after NUMERIC,
            status VARCHAR(40),
            mode VARCHAR(20),
            agent_id INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """))
    db.commit()
    print("Added no_auto_cover column + neg_cover_log table")
except Exception as e:
    db.rollback(); print(f"Error: {e}")
finally: db.close()
