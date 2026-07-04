"""run_loyalty.py — build loyalty data from May-Jun 2026 trades for testing."""
import datetime
from database import SessionLocal
import loyalty_engine as LE

if __name__ == "__main__":
    db = SessionLocal()
    print("Ensuring schema + rewards catalog...")
    LE.ensure_schema(db)
    start = datetime.date(2025, 1, 1)
    end   = datetime.date(2026, 7, 1)   # exclusive -> May+June
    print(f"Building loyalty from trades {start} .. {end} (exclusive)")
    LE.rebuild_from_trades(db, start, end)

    # summary
    from sqlalchemy import text
    r = db.execute(text("""
        SELECT COUNT(*),
          COUNT(*) FILTER (WHERE tier='bronze'), COUNT(*) FILTER (WHERE tier='silver'),
          COUNT(*) FILTER (WHERE tier='gold'), COUNT(*) FILTER (WHERE tier='platinum'),
          ROUND(SUM(points_balance)::numeric,0)
        FROM loyalty_accounts
    """)).fetchone()
    print(f"\nMembers: {r[0]}  Bronze:{r[1]} Silver:{r[2]} Gold:{r[3]} Platinum:{r[4]}")
    print(f"Total points outstanding: {r[5]:,}")
    print("\nTop 10 members by lifetime points:")
    for row in db.execute(text("""
        SELECT la.client_id, c.name, la.tier, ROUND(la.lifetime_points::numeric,0), la.current_streak, la.best_streak
        FROM loyalty_accounts la LEFT JOIN clients c ON c.id=la.client_id
        ORDER BY la.lifetime_points DESC LIMIT 10
    """)).fetchall():
        print(f"  #{row[0]} {row[1]}: {row[2]} | {row[3]:,} pts | streak {row[4]} (best {row[5]})")
    db.close()
