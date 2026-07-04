import sys
import os
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text
import bcrypt

db = SessionLocal()

# Check users table
users = db.execute(text("SELECT id, email, role, is_active FROM users")).fetchall()
print(f"Users in DB: {len(users)}")
for u in users:
    print(f"  id={u[0]} email={u[1]} role={u[2]} active={u[3]}")

# Reset admin password or create admin if missing
password = os.getenv("ADMIN_RESET_PW")
if not password:
    print("Set ADMIN_RESET_PW env var")
    sys.exit(1)
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

admin = db.execute(text("SELECT id FROM users WHERE email = 'admin@brokercrm.com'")).fetchone()
if admin:
    db.execute(text("UPDATE users SET hashed_password = :pw, is_active = TRUE WHERE email = 'admin@brokercrm.com'"), {"pw": hashed})
    print("\n✅ Admin password reset")
else:
    db.execute(text("""
        INSERT INTO users (full_name, email, hashed_password, role, is_active, created_at)
        VALUES ('Admin', 'admin@brokercrm.com', :pw, 'super_admin', TRUE, NOW())
    """), {"pw": hashed})
    print("\n✅ Admin user created: admin@brokercrm.com")

db.commit()
db.close()
