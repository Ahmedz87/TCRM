"""Add all Meta Ads tracking columns to leads table"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.rollback()
try:
    db.execute(text("""
        -- Meta lead identity
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_lead_id VARCHAR(50);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS fb_form_id VARCHAR(50);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_name VARCHAR(200);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS adset_name VARCHAR(200);

        -- Source detail: instagram / facebook / messenger / audience_network
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_platform VARCHAR(40);
        -- For audience network: which app/website it came from
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_publisher_platform VARCHAR(60);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_platform_position VARCHAR(60);

        -- All custom qualifying questions (JSON: [{"q":"...","a":"..."}])
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS custom_questions JSONB;

        -- Meta CAPI feedback: stage sent back to Meta + when
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_stage VARCHAR(40);
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_stage_sent_at TIMESTAMP;

        -- Attribution
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS fbclid VARCHAR(255);

        -- Unique index on meta_lead_id (rename from fb_lead_id if exists)
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='leads' AND column_name='fb_lead_id') THEN
                -- Copy old fb_lead_id values into meta_lead_id
                UPDATE leads SET meta_lead_id = fb_lead_id
                    WHERE meta_lead_id IS NULL AND fb_lead_id IS NOT NULL;
            END IF;
        END $$;

        CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_meta_lead_id
            ON leads(meta_lead_id) WHERE meta_lead_id IS NOT NULL;
    """))
    db.commit()
    print("All Meta columns added to leads table!")
    print("  meta_lead_id, fb_form_id, ad_name, adset_name")
    print("  meta_platform, meta_publisher_platform, meta_platform_position")
    print("  custom_questions (JSONB), meta_stage, meta_stage_sent_at, fbclid")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
