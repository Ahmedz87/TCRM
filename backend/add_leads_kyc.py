import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("Adding KYC columns to leads...")
cols = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS kyc_id_uploaded BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS kyc_id_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS kyc_address_uploaded BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS kyc_address_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS kyc_notes TEXT",
]
for c in cols:
    try:
        db.execute(text(c))
        db.commit()
        col = c.split('ADD COLUMN IF NOT EXISTS ')[1].split(' ')[0]
        print(f"  ✅ {col}")
    except Exception as e:
        db.rollback()
        print(f"  ⚠️  {e}")

# Update sample leads with varied verification states
print("\nUpdating sample leads with varied verification states...")
db.execute(text("""
    UPDATE leads SET 
        phone_verified=TRUE, email_verified=FALSE, is_verified=FALSE,
        kyc_id_uploaded=FALSE, kyc_id_verified=FALSE,
        kyc_address_uploaded=FALSE, kyc_address_verified=FALSE
    WHERE id=1
"""))
db.execute(text("""
    UPDATE leads SET 
        phone_verified=TRUE, email_verified=TRUE, is_verified=FALSE,
        kyc_id_uploaded=TRUE, kyc_id_verified=FALSE,
        kyc_address_uploaded=FALSE, kyc_address_verified=FALSE
    WHERE id=2
"""))
db.execute(text("""
    UPDATE leads SET 
        phone_verified=FALSE, email_verified=FALSE, is_verified=FALSE,
        kyc_id_uploaded=FALSE, kyc_id_verified=FALSE,
        kyc_address_uploaded=FALSE, kyc_address_verified=FALSE
    WHERE id=3
"""))
db.execute(text("""
    UPDATE leads SET 
        phone_verified=TRUE, email_verified=TRUE, is_verified=TRUE,
        kyc_id_uploaded=TRUE, kyc_id_verified=TRUE,
        kyc_address_uploaded=TRUE, kyc_address_verified=TRUE
    WHERE id=4
"""))
db.execute(text("""
    UPDATE leads SET 
        phone_verified=FALSE, email_verified=TRUE, is_verified=FALSE,
        kyc_id_uploaded=TRUE, kyc_id_verified=FALSE,
        kyc_address_uploaded=FALSE, kyc_address_verified=FALSE
    WHERE id=5
"""))
db.commit()
print("✅ Sample leads updated with varied verification states!")
db.close()
