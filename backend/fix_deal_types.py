"""
fix_deal_types.py
Reclassify existing deals with correct types and extract payment methods.
Business rules:
- Account types: STD, ZERO, Cent, VIP, FIX
- Islamic variant: any account with group ending in '-IS' (swap-free)
- Bonus & Credit ONLY for STD accounts (STD\2-STD, STD\2-STD-IS, etc.)
- ZERO, Cent, VIP, FIX get NO bonus and NO credit regardless of IS
- Internal transfers = action 2 with 'transfer' in comment
- Deposits = action 2, positive, not transfer, STD or any account
- Withdrawals = action 2, negative, not transfer
Run once after bridge has saved deals.
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("Fixing deal types...")
print("Rule: Bonus/Credit only for STD accounts\n")

# Step 1: Internal transfers (action=2, comment contains 'transfer')
r = db.execute(text("""
    UPDATE deals SET deal_type = 'internal_transfer'
    WHERE action = 2
    AND LOWER(comment) LIKE '%transfer%'
"""))
print(f"Internal transfers:     {r.rowcount:>8,}")

# Step 2: Real deposits (action=2, positive, not transfer)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'deposit'
    WHERE action = 2
    AND profit > 0
    AND LOWER(comment) NOT LIKE '%transfer%'
"""))
print(f"Deposits:               {r.rowcount:>8,}")

# Step 3: Real withdrawals (action=2, negative, not transfer)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'withdrawal'
    WHERE action = 2
    AND profit < 0
    AND LOWER(comment) NOT LIKE '%transfer%'
"""))
print(f"Withdrawals:            {r.rowcount:>8,}")

# Step 4: Bonus deposit — STD accounts ONLY (action=6, positive)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'bonus_deposit'
    WHERE action = 6
    AND profit >= 0
    AND login IN (
        SELECT login FROM trading_accounts 
        WHERE group_name ILIKE '%STD%'
    )
"""))
print(f"Bonus deposits (STD):   {r.rowcount:>8,}")

# Step 5: Bonus withdrawal — STD accounts ONLY (action=6, negative)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'bonus_withdrawal'
    WHERE action = 6
    AND profit < 0
    AND login IN (
        SELECT login FROM trading_accounts 
        WHERE group_name ILIKE '%STD%'
    )
"""))
print(f"Bonus withdrawals (STD):{r.rowcount:>8,}")

# Step 6: Non-STD action=6 → mark as 'other' (not a real bonus)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'other'
    WHERE action = 6
    AND login NOT IN (
        SELECT login FROM trading_accounts 
        WHERE group_name ILIKE '%STD%'
    )
"""))
print(f"Non-STD bonus (ignored):{r.rowcount:>8,}")

# Step 7: Credit in — STD accounts ONLY (action=3, positive)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'credit_in'
    WHERE action = 3
    AND profit >= 0
    AND login IN (
        SELECT login FROM trading_accounts 
        WHERE group_name ILIKE '%STD%'
    )
"""))
print(f"Credit in (STD):        {r.rowcount:>8,}")

# Step 8: Credit out — STD accounts ONLY (action=3, negative)
r = db.execute(text("""
    UPDATE deals SET deal_type = 'credit_out'
    WHERE action = 3
    AND profit < 0
    AND login IN (
        SELECT login FROM trading_accounts 
        WHERE group_name ILIKE '%STD%'
    )
"""))
print(f"Credit out (STD):       {r.rowcount:>8,}")

# Step 9: Non-STD action=3 → mark as 'other'
r = db.execute(text("""
    UPDATE deals SET deal_type = 'other'
    WHERE action = 3
    AND login NOT IN (
        SELECT login FROM trading_accounts 
        WHERE group_name ILIKE '%STD%'
    )
"""))
print(f"Non-STD credit (ignored):{r.rowcount:>7,}")

db.commit()

# Summary
print("\n" + "=" * 50)
print("DEAL TYPE SUMMARY")
print("=" * 50)
result = db.execute(text("""
    SELECT deal_type, COUNT(*) as cnt, 
           SUM(CASE WHEN profit > 0 THEN profit ELSE 0 END) as total_in,
           SUM(CASE WHEN profit < 0 THEN ABS(profit) ELSE 0 END) as total_out
    FROM deals
    WHERE action IN (2,3,6,14)
    GROUP BY deal_type
    ORDER BY cnt DESC
"""))
for row in result:
    print(f"  {row[0]:<25} {row[1]:>8,} records  in: ${row[2]:>12,.2f}  out: ${row[3]:>12,.2f}")

# Show account type distribution
print("\nAccount type distribution:")
result2 = db.execute(text("""
    SELECT 
        account_type,
        COUNT(*) as total,
        SUM(CASE WHEN is_islamic THEN 1 ELSE 0 END) as islamic,
        SUM(CASE WHEN NOT is_islamic THEN 1 ELSE 0 END) as swap
    FROM trading_accounts 
    GROUP BY account_type
    ORDER BY total DESC
"""))
for row in result2:
    print(f"  {row[0]:<12} total:{row[1]:>6,}  islamic:{row[2]:>6,}  swap:{row[3]:>6,}")

db.close()
print("\nDone! Now run: python rebuild_db.py")
