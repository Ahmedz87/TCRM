import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.rollback()
try:
    # Ensure leads has a score column
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0;"))
    db.commit()

    # +50 to recapture leads
    r1 = db.execute(text("""
        UPDATE leads SET score = COALESCE(score,0) + 50
        WHERE match_badge = 'recapture' AND (score IS NULL OR score < 50)
    """))
    # +50 to registered-no-deposit leads
    r2 = db.execute(text("""
        UPDATE leads SET score = COALESCE(score,0) + 50
        WHERE match_badge = 'registered_no_deposit' AND (score IS NULL OR score < 50)
    """))
    # +50 to recapture clients (on clients page)
    r3 = db.execute(text("""
        UPDATE clients SET score = COALESCE(score,0) + 50
        WHERE lead_badge = 'recapture'
    """))
    db.commit()
    print(f"Score boosted +50:")
    print(f"  Recapture leads:        {r1.rowcount}")
    print(f"  No-deposit leads:       {r2.rowcount}")
    print(f"  Recapture clients:      {r3.rowcount}")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
