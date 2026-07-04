import db_config
import psycopg2
c = db_config.connect()
cur = c.cursor()

# --- LEADS: every column the leads query selects ---
leads_cols = [
    ("language","VARCHAR(20)"), ("platform","VARCHAR(50)"), ("campaign_name","VARCHAR(255)"),
    ("ad_set_name","VARCHAR(255)"), ("ad_name","VARCHAR(255)"), ("assigned_agent_id","INTEGER"),
    ("kyc_status","VARCHAR(50)"), ("notes","TEXT"), ("call_attempts","INTEGER DEFAULT 0"),
    ("last_call_at","TIMESTAMP"), ("converted_login","BIGINT"), ("converted_at","TIMESTAMP"),
    ("utm_source","VARCHAR(255)"), ("utm_medium","VARCHAR(255)"), ("utm_campaign","VARCHAR(255)"),
    ("updated_at","TIMESTAMP DEFAULT NOW()"), ("google_lead_id","VARCHAR(100)"),
    ("meta_stage","VARCHAR(50)"), ("meta_platform","VARCHAR(50)"), ("meta_quality","VARCHAR(50)"),
    ("match_badge","VARCHAR(50)"), ("matched_login","BIGINT"), ("score","INTEGER"),
    ("phone_verified","BOOLEAN DEFAULT FALSE"), ("email_verified","BOOLEAN DEFAULT FALSE"),
    ("is_verified","BOOLEAN DEFAULT FALSE"), ("ip_address","VARCHAR(64)"), ("ip_count","INTEGER DEFAULT 0"),
    ("cid","VARCHAR(128)"), ("cid_count","INTEGER DEFAULT 0"),
    ("bonus_eligible","BOOLEAN DEFAULT FALSE"), ("bonus_claimed","BOOLEAN DEFAULT FALSE"),
    ("bonus_blocked_reason","TEXT"), ("kyc_id_uploaded","BOOLEAN DEFAULT FALSE"),
    ("kyc_id_verified","BOOLEAN DEFAULT FALSE"), ("kyc_address_uploaded","BOOLEAN DEFAULT FALSE"),
    ("kyc_address_verified","BOOLEAN DEFAULT FALSE"), ("kyc_notes","TEXT"),
]
for name,typ in leads_cols:
    cur.execute(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {name} {typ}")

# --- CLIENTS: missing columns the clients query selects ---
clients_cols = [
    ("lead_badge","VARCHAR(50)"), ("matched_lead_id","INTEGER"),
    ("total_withdrawals","NUMERIC DEFAULT 0"),
]
for name,typ in clients_cols:
    cur.execute(f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS {name} {typ}")

c.commit()
print("All missing columns added.")
c.close()
