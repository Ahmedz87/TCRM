import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("Adding verification columns to leads...")
alterations = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS ip_address VARCHAR(50)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS ip_count INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS cid VARCHAR(100)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS cid_count INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS verification_notes TEXT",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS bonus_eligible BOOLEAN DEFAULT NULL",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS bonus_claimed BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS bonus_blocked_reason VARCHAR(200)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS welcome_bonus_amount FLOAT DEFAULT 0",
]
for a in alterations:
    try:
        db.execute(text(a))
        db.commit()
        print(f"  ✅ {a.split('ADD COLUMN IF NOT EXISTS ')[1].split(' ')[0]}")
    except Exception as e:
        db.rollback()
        print(f"  ⚠️ {e}")

print("\nCreating client_dashboard table...")
db.execute(text("""
CREATE TABLE IF NOT EXISTS client_dashboard_sessions (
    id              SERIAL PRIMARY KEY,
    login           INTEGER NOT NULL,
    cid             VARCHAR(100),
    ip_address      VARCHAR(50),
    session_time    TIMESTAMP DEFAULT NOW(),
    bonus_shown     BOOLEAN DEFAULT FALSE,
    bonus_action    VARCHAR(50)
)
"""))
db.commit()
print("✅ client_dashboard_sessions created!")

print("\nCreating welcome_bonus_rules table...")
db.execute(text("""
CREATE TABLE IF NOT EXISTS welcome_bonus_rules (
    id              SERIAL PRIMARY KEY,
    rule_name       VARCHAR(100),
    bonus_amount    FLOAT DEFAULT 50,
    min_deposit     FLOAT DEFAULT 0,
    max_per_cid     INTEGER DEFAULT 1,
    max_per_ip      INTEGER DEFAULT 3,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
)
"""))
# Insert default rule
db.execute(text("""
INSERT INTO welcome_bonus_rules (rule_name, bonus_amount, min_deposit, max_per_cid, max_per_ip)
VALUES ('Default Welcome Bonus', 50, 0, 1, 3)
ON CONFLICT DO NOTHING
"""))
db.commit()
print("✅ welcome_bonus_rules created!")

db.close()
print("\n✅ All setup complete!")
