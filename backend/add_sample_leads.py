import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Check current leads
count = db.execute(text("SELECT COUNT(*) FROM leads")).scalar()
print(f"Current leads: {count}")

# Add sample leads with varied verification states
samples = [
    {
        "full_name": "Ahmed Hassan Ali", "phone": "+9647801234567",
        "email": "ahmed.hassan@gmail.com", "country": "Iraq", "city": "Baghdad",
        "language": "ar", "source": "Facebook", "campaign_name": "Gold Trading Campaign",
        "status": "new", "phone_verified": False, "email_verified": False,
        "is_verified": False, "kyc_id_uploaded": False, "kyc_id_verified": False,
        "kyc_address_uploaded": False, "kyc_address_verified": False,
    },
    {
        "full_name": "Sara Mohammed", "phone": "+9647709876543",
        "email": "sara.m@hotmail.com", "country": "Iraq", "city": "Basrah",
        "language": "ar", "source": "Google", "campaign_name": "Forex Keywords Iraq",
        "status": "contacted", "phone_verified": True, "email_verified": False,
        "is_verified": False, "kyc_id_uploaded": False, "kyc_id_verified": False,
        "kyc_address_uploaded": False, "kyc_address_verified": False,
    },
    {
        "full_name": "Khalid Ibrahim", "phone": "+971501234567",
        "email": "khalid.i@yahoo.com", "country": "UAE", "city": "Dubai",
        "language": "ar", "source": "Instagram", "campaign_name": "UAE Traders Campaign",
        "status": "callback", "phone_verified": True, "email_verified": True,
        "is_verified": False, "kyc_id_uploaded": True, "kyc_id_verified": False,
        "kyc_address_uploaded": False, "kyc_address_verified": False,
    },
    {
        "full_name": "Fatima Al-Zahra", "phone": "+9647751234567",
        "email": "fatima.z@gmail.com", "country": "Iraq", "city": "Karbala",
        "language": "ar", "source": "WhatsApp", "campaign_name": "",
        "status": "interested", "phone_verified": True, "email_verified": True,
        "is_verified": True, "kyc_id_uploaded": True, "kyc_id_verified": True,
        "kyc_address_uploaded": True, "kyc_address_verified": True,
    },
    {
        "full_name": "Omar Nasser", "phone": "+963991234567",
        "email": "omar.n@gmail.com", "country": "Syria", "city": "Damascus",
        "language": "ar", "source": "Facebook", "campaign_name": "Syria Trading",
        "status": "new", "phone_verified": False, "email_verified": True,
        "is_verified": False, "kyc_id_uploaded": True, "kyc_id_verified": False,
        "kyc_address_uploaded": False, "kyc_address_verified": False,
    },
    {
        "full_name": "Layla Mahmoud", "phone": "+9647801112233",
        "email": "layla.m@gmail.com", "country": "Iraq", "city": "Baghdad",
        "language": "ar", "source": "Google", "campaign_name": "Baghdad Forex",
        "status": "no_answer", "phone_verified": False, "email_verified": False,
        "is_verified": False, "kyc_id_uploaded": False, "kyc_id_verified": False,
        "kyc_address_uploaded": False, "kyc_address_verified": False,
    },
    {
        "full_name": "Hassan Karimi", "phone": "+971507654321",
        "email": "hassan.k@outlook.com", "country": "UAE", "city": "Sharjah",
        "language": "ar", "source": "Facebook", "campaign_name": "UAE Gold",
        "status": "contacted", "phone_verified": True, "email_verified": True,
        "is_verified": False, "kyc_id_uploaded": True, "kyc_id_verified": True,
        "kyc_address_uploaded": True, "kyc_address_verified": False,
    },
    {
        "full_name": "Noor Al-Ahmad", "phone": "+963944556677",
        "email": "", "country": "Syria", "city": "Aleppo",
        "language": "ar", "source": "TikTok", "campaign_name": "Syria Social",
        "status": "new", "phone_verified": False, "email_verified": False,
        "is_verified": False, "kyc_id_uploaded": False, "kyc_id_verified": False,
        "kyc_address_uploaded": False, "kyc_address_verified": False,
    },
]

for s in samples:
    db.execute(text("""
        INSERT INTO leads (
            full_name, phone, email, country, city, language,
            source, campaign_name, status,
            phone_verified, email_verified, is_verified,
            kyc_id_uploaded, kyc_id_verified,
            kyc_address_uploaded, kyc_address_verified,
            created_at, updated_at
        ) VALUES (
            :full_name, :phone, :email, :country, :city, :language,
            :source, :campaign_name, :status,
            :phone_verified, :email_verified, :is_verified,
            :kyc_id_uploaded, :kyc_id_verified,
            :kyc_address_uploaded, :kyc_address_verified,
            NOW(), NOW()
        )
    """), s)

db.commit()
new_count = db.execute(text("SELECT COUNT(*) FROM leads")).scalar()
print(f"✅ Added {new_count - count} sample leads!")
print(f"Total leads now: {new_count}")
print("\nSample states:")
print("  #1 Ahmed:   Nothing verified")
print("  #2 Sara:    Phone only ✓")
print("  #3 Khalid:  Phone + Email ✓, ID uploaded")
print("  #4 Fatima:  FULLY VERIFIED ✅")
print("  #5 Omar:    Email only ✓, ID uploaded")
print("  #6 Layla:   No answer — nothing verified")
print("  #7 Hassan:  Phone+Email+ID verified, address uploaded")
print("  #8 Noor:    New lead — nothing")
db.close()
