import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text
with engine.begin() as conn:
    # Compute deposit/withdrawal totals from transactions, update clients
    conn.execute(text("""
        UPDATE clients c SET
            total_deposits = COALESCE(sub.deposits, 0),
            total_withdrawals = COALESCE(sub.withdrawals, 0),
            net_deposit = COALESCE(sub.deposits,0) - COALESCE(sub.withdrawals,0)
        FROM (
            SELECT login,
                SUM(amount) FILTER (WHERE tx_type IN ('deposit','credit_in')) as deposits,
                SUM(amount) FILTER (WHERE tx_type IN ('withdrawal','credit_out') AND COALESCE(status,'')<>'rejected') as withdrawals
            FROM transactions GROUP BY login
        ) sub
        WHERE c.login = sub.login
    """))
    # Count with deposits now
    n = conn.execute(text("SELECT COUNT(*) FROM clients WHERE total_deposits > 0")).scalar()
    print(f"Clients with deposits now: {n}")
print("Client totals updated.")
