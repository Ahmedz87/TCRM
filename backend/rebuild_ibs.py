"""
rebuild_ibs.py — Rebuild IB stats from transactions and clients tables
Updates total_clients, active_clients, total_volume, total_commission etc.
Safe to run — only updates, never deletes.
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("=== Rebuilding IB stats ===\n")

print("Step 1: Update total_clients for each IB...")
db.execute(text("""
    UPDATE ibs ib
    SET total_clients = (
        SELECT COUNT(DISTINCT c.login)
        FROM clients c
        WHERE c.agent = ib.agent_id
    )
"""))
db.commit()
print("  ✅ total_clients updated")

print("Step 2: Update active_clients (clients with deposits)...")
db.execute(text("""
    UPDATE ibs ib
    SET active_clients = (
        SELECT COUNT(DISTINCT c.login)
        FROM clients c
        WHERE c.agent = ib.agent_id
        AND c.total_deposits > 0
    )
"""))
db.commit()
print("  ✅ active_clients updated")

print("Step 3: Update unique_ftds...")
db.execute(text("""
    UPDATE ibs ib
    SET unique_ftds = (
        SELECT COUNT(DISTINCT c.login)
        FROM clients c
        WHERE c.agent = ib.agent_id
        AND c.total_deposits > 0
    )
"""))
db.commit()
print("  ✅ unique_ftds updated")

print("Step 4: Update IB own account balance...")
db.execute(text("""
    UPDATE ibs ib
    SET balance = COALESCE((
        SELECT c.balance FROM clients c
        WHERE c.login = ib.agent_id
        LIMIT 1
    ), 0)
"""))
db.commit()
print("  ✅ balance updated")

print("Step 5: Set parent_ib_id (sub-IB detection)...")
# An IB is a sub-IB if their agent (introducer) is also an IB
db.execute(text("""
    UPDATE ibs ib
    SET parent_ib_id = parent.id
    FROM clients c
    JOIN ibs parent ON parent.agent_id = c.agent
    WHERE c.login = ib.agent_id
    AND c.agent IS NOT NULL
    AND c.agent != 0
    AND parent.id != ib.id
"""))
db.commit()
print("  ✅ parent_ib_id updated")

print("Step 6: Update IB level from group name...")
db.execute(text("""
    UPDATE ibs ib
    SET ib_level = CASE
        WHEN ib.group_name ILIKE '%IB-10%' THEN 10
        WHEN ib.group_name ILIKE '%IB-9%'  THEN 9
        WHEN ib.group_name ILIKE '%IB-8%'  THEN 8
        WHEN ib.group_name ILIKE '%IB-7%'  THEN 7
        WHEN ib.group_name ILIKE '%IB-6%'  THEN 6
        ELSE 5
    END
    WHERE ib.group_name IS NOT NULL
"""))
db.commit()
print("  ✅ ib_level updated from group name")

# Show results
print("\n=== Results ===")
result = db.execute(text("""
    SELECT 
        COUNT(*) as total_ibs,
        SUM(total_clients) as total_clients,
        SUM(active_clients) as active_clients,
        COUNT(*) FILTER (WHERE parent_ib_id IS NOT NULL) as sub_ibs,
        SUM(balance) as total_balance
    FROM ibs
""")).fetchone()
print(f"  Total IBs:      {result[0]:,}")
print(f"  Total clients:  {int(result[1] or 0):,}")
print(f"  Active clients: {int(result[2] or 0):,}")
print(f"  Sub-IBs:        {result[3]:,}")
print(f"  Total balance:  ${float(result[4] or 0):,.2f}")

# Top 5 IBs
print("\nTop 5 IBs by clients:")
top = db.execute(text("""
    SELECT name, ib_code, total_clients, active_clients, ib_level, balance
    FROM ibs ORDER BY total_clients DESC LIMIT 5
""")).fetchall()
for r in top:
    print(f"  {r[1]} {r[0][:30]}: {r[2]} clients ({r[3]} active), L{r[4]}, ${float(r[5] or 0):,.2f}")

db.close()
print("\n✅ IB rebuild complete!")
