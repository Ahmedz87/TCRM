import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
# Try the kind of query the leads endpoint runs - find which column is missing
try:
    r = db.execute(text("SELECT id, full_name, email, phone, country, city, status, source, platform, campaign_name, ad_name, adset_name, meta_lead_id, meta_quality, match_badge, matched_login, match_checked_at, score, created_at, assigned_agent_id FROM leads LIMIT 1")).fetchone()
    print("Basic columns OK")
except Exception as e:
    print(f"Missing column: {str(e)[:200]}")
db.close()
