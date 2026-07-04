"""Add columns for lead-client matching badges"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.rollback()
try:
    db.execute(text("""
        -- On leads: badge + matched client login
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS match_badge VARCHAR(40);
        -- values: 'recapture', 'registered_no_deposit', NULL
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS matched_login BIGINT;
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS match_checked_at TIMESTAMP;

        -- On clients: badge showing they came from a lead / recaptured
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS lead_badge VARCHAR(40);
        -- values: 'recapture', 'from_lead', NULL
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS matched_lead_id BIGINT;
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS recapture_at TIMESTAMP;

        CREATE INDEX IF NOT EXISTS idx_leads_match_badge ON leads(match_badge) WHERE match_badge IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_clients_lead_badge ON clients(lead_badge) WHERE lead_badge IS NOT NULL;
    """))
    db.commit()
    print("Match columns added!")
    print("  leads: match_badge, matched_login, match_checked_at")
    print("  clients: lead_badge, matched_lead_id, recapture_at")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
