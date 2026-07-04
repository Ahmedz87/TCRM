import sys
import os
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db = SessionLocal()

DEFAULT_PASSWORD = os.getenv("ADMIN_RESET_PW")
if not DEFAULT_PASSWORD:
    print("Set ADMIN_RESET_PW env var")
    sys.exit(1)
hashed = pwd_context.hash(DEFAULT_PASSWORD)

result = db.execute(text("""
    UPDATE users 
    SET hashed_password = :pwd
    WHERE email != 'admin@brokercrm.com'
    AND hashed_password = '$2b$12$placeholder_hash_for_staff'
"""), {"pwd": hashed})
db.commit()

print(f"✅ Password set for {result.rowcount} staff members")
print(f"   Default password: {DEFAULT_PASSWORD}")
print(f"   All staff can now login with their email + {DEFAULT_PASSWORD}")
db.close()
