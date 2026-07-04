import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.rollback()
try:
    r = db.execute(text("""
        UPDATE clients SET call_score = COALESCE(call_score,0) + 50
        WHERE lead_badge = 'recapture'
    """))
    db.commit()
    print(f"Recapture clients boosted +50 call_score: {r.rowcount}")
except Exception as e:
    db.rollback(); print(f"Error: {e}")
finally: db.close()
