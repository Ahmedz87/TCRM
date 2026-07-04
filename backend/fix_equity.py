"""
fix_equity.py
For accounts with no open positions, equity = balance and margin_level = 0
This updates equity to equal balance where equity is 0 but balance > 0
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("Fixing equity = balance where equity is 0...")
r = db.execute(text("""
    UPDATE trading_accounts 
    SET equity = balance
    WHERE equity = 0 AND balance > 0
"""))
db.commit()
print(f"  Updated {r.rowcount} trading accounts")

r2 = db.execute(text("""
    UPDATE clients 
    SET equity = balance
    WHERE equity = 0 AND balance > 0
"""))
db.commit()
print(f"  Updated {r2.rowcount} clients")

# Verify
row = db.execute(text("""
    SELECT COUNT(*) FILTER (WHERE equity > 0), COUNT(*)
    FROM trading_accounts WHERE balance > 0
""")).fetchone()
print(f"\nTrading accounts with balance>0: {row[1]}, now has equity: {row[0]}")

db.close()
print("Done!")
