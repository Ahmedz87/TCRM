"""Add Facebook tracking columns to leads table"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.rollback()
try:
    db.execute(text("""
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS fb_lead_id VARCHAR(50);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS fb_form_id VARCHAR(50);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_name VARCHAR(200);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_fb_lead_id
            ON leads(fb_lead_id) WHERE fb_lead_id IS NOT NULL;
    """))
    db.commit()
    print("Facebook columns added (fb_lead_id, fb_form_id, ad_name)!")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
