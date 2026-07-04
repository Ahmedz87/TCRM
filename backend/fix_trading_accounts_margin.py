import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("Copying margin_level and equity from clients to trading_accounts...")
r = db.execute(text("""
    UPDATE trading_accounts ta
    SET 
        margin_level = c.margin_level,
        equity = CASE WHEN c.equity > 0 THEN c.equity ELSE c.balance END
    FROM clients c
    WHERE ta.login = c.login
    AND (c.margin_level > 0 OR c.equity > 0)
"""))
db.commit()
print(f"  Updated {r.rowcount} trading accounts")

# Verify
r2 = db.execute(text("SELECT COUNT(*) FROM trading_accounts WHERE margin_level > 0")).scalar()
r3 = db.execute(text("SELECT COUNT(*) FROM trading_accounts WHERE equity > 0")).scalar()
print(f"  Trading accounts with margin: {r2}")
print(f"  Trading accounts with equity: {r3}")

db.close()
print("Done!")
