import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text

adds = [
    ("leads", "ad_set_name", "VARCHAR"),
    ("leads", "bonus_blocked_reason", "VARCHAR"),
    ("leads", "bonus_claimed", "BOOLEAN DEFAULT FALSE"),
    ("leads", "bonus_eligible", "BOOLEAN DEFAULT FALSE"),
    ("leads", "call_attempts", "INTEGER DEFAULT 0"),
    ("leads", "converted_at", "TIMESTAMP"),
    ("leads", "google_lead_id", "VARCHAR"),
    ("leads", "kyc_address_uploaded", "BOOLEAN DEFAULT FALSE"),
    ("leads", "kyc_address_verified", "BOOLEAN DEFAULT FALSE"),
    ("leads", "kyc_id_uploaded", "BOOLEAN DEFAULT FALSE"),
    ("leads", "kyc_id_verified", "BOOLEAN DEFAULT FALSE"),
    ("leads", "kyc_notes", "TEXT"),
    ("leads", "kyc_status", "VARCHAR"),
    ("leads", "last_call_at", "TIMESTAMP"),
    ("leads", "meta_stage", "VARCHAR"),
    ("leads", "utm_source", "VARCHAR"),
]
for tbl, col, typ in adds:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {typ}"))
        print(f"  OK: {tbl}.{col}")
    except Exception as e:
        print(f"  ERR {tbl}.{col}: {str(e)[:60]}")

# Verify ALL columns the router needs now exist
from sqlalchemy import inspect
existing = {c["name"] for c in inspect(engine).get_columns("leads")}
needed = ['ad_name','ad_set_name','assigned_agent_id','bonus_blocked_reason','bonus_claimed','bonus_eligible','call_attempts','campaign_name','cid','cid_count','city','converted_at','converted_login','country','created_at','email','email_verified','full_name','google_lead_id','id','ip_address','ip_count','is_verified','kyc_address_uploaded','kyc_address_verified','kyc_id_uploaded','kyc_id_verified','kyc_notes','kyc_status','language','last_call_at','match_badge','matched_login','meta_lead_id','meta_platform','meta_quality','meta_stage','notes','phone','phone_verified','platform','score','source','status','updated_at','utm_campaign','utm_medium','utm_source']
missing = [c for c in needed if c not in existing]
print(f"\nStill missing: {missing if missing else 'NONE - all columns present!'}")
