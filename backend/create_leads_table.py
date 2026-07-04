import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Drop and recreate cleanly
db.execute(text("DROP TABLE IF EXISTS leads CASCADE"))
db.commit()

db.execute(text("""
CREATE TABLE leads (
    id                  SERIAL PRIMARY KEY,
    full_name           VARCHAR(200),
    phone               VARCHAR(50),
    email               VARCHAR(200),
    country             VARCHAR(100),
    city                VARCHAR(100),
    language            VARCHAR(20),
    source              VARCHAR(50) DEFAULT 'manual',
    campaign_name       VARCHAR(200),
    ad_set_name         VARCHAR(200),
    ad_name             VARCHAR(200),
    form_id             VARCHAR(100),
    platform            VARCHAR(20) DEFAULT 'manual',
    status              VARCHAR(30) DEFAULT 'new',
    assigned_agent_id   INTEGER,
    kyc_status          VARCHAR(20) DEFAULT 'pending',
    notes               TEXT,
    call_attempts       INTEGER DEFAULT 0,
    last_call_at        TIMESTAMP,
    last_call_by        INTEGER,
    converted_login     INTEGER,
    converted_at        TIMESTAMP,
    meta_lead_id        VARCHAR(100),
    google_lead_id      VARCHAR(100),
    utm_source          VARCHAR(100),
    utm_medium          VARCHAR(100),
    utm_campaign        VARCHAR(100),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
)
"""))
db.commit()
print("✅ leads table created!")

# Indexes
for idx in [
    "CREATE INDEX idx_leads_status ON leads(status)",
    "CREATE INDEX idx_leads_source ON leads(source)",
    "CREATE INDEX idx_leads_agent ON leads(assigned_agent_id)",
    "CREATE INDEX idx_leads_created ON leads(created_at DESC)",
    "CREATE INDEX idx_leads_phone ON leads(phone)",
]:
    db.execute(text(idx))
db.commit()
print("✅ indexes created!")

# Sample leads
samples = [
    ('Ahmed Hassan Ali',  '+9647801234567', 'ahmed.hassan@gmail.com', 'Iraq', 'Baghdad',  'ar', 'Facebook', 'Gold Trading Campaign', 'new'),
    ('Sara Mohammed',     '+9647709876543', 'sara.m@hotmail.com',     'Iraq', 'Basrah',   'ar', 'Google',   'Forex Keywords Iraq',   'contacted'),
    ('Khalid Ibrahim',    '+971501234567',  'khalid.i@yahoo.com',     'UAE',  'Dubai',    'ar', 'Instagram','UAE Traders Campaign',  'new'),
    ('Fatima Al-Zahra',   '+9647751234567', '',                       'Iraq', 'Karbala',  'ar', 'WhatsApp', '',                      'callback'),
    ('Omar Nasser',       '+963991234567',  'omar.n@gmail.com',       'Syria','Damascus', 'ar', 'Facebook', 'Syria Trading',         'new'),
]
for s in samples:
    db.execute(text("""
        INSERT INTO leads (full_name,phone,email,country,city,language,source,campaign_name,status)
        VALUES (:n,:p,:e,:c,:ci,:l,:s,:camp,:st)
    """), {"n":s[0],"p":s[1],"e":s[2],"c":s[3],"ci":s[4],"l":s[5],"s":s[6],"camp":s[7],"st":s[8]})
db.commit()
print("✅ 5 sample leads added!")
print("\n✅ All done!")
db.close()
