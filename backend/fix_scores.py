import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.rollback()
try:
    # Set recapture + no-deposit leads to score 50 (clean, no double-counting)
    r1 = db.execute(text("""
        UPDATE leads SET score = 50
        WHERE match_badge = 'recapture' AND (score IS NULL OR score < 50)
    """))
    r2 = db.execute(text("""
        UPDATE leads SET score = 50
        WHERE match_badge = 'registered_no_deposit' AND (score IS NULL OR score < 50)
    """))
    db.commit()
    print(f"Fixed scores: {r1.rowcount} recapture, {r2.rowcount} no-deposit set to 50")

    # Verify
    chk = db.execute(text("""
        SELECT match_badge, COUNT(*), COUNT(*) FILTER (WHERE score >= 50) as ok
        FROM leads WHERE match_badge IS NOT NULL
        GROUP BY match_badge
    """)).fetchall()
    print("\nAfter fix:")
    for r in chk:
        print(f"  {r[0]}: {r[1]} total, {r[2]} with score 50")
finally:
    db.close()
