import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE transactions ADD CONSTRAINT transactions_deal_id_key UNIQUE (deal_id)"))
        print("Added UNIQUE constraint on transactions.deal_id")
    except Exception as e:
        print(f"Note: {str(e)[:80]}")
print("Done.")
