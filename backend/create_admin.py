import psycopg2
from passlib.context import CryptContext
import db_config

# ===== EDIT THESE =====
EMAIL = "admin@tnfx.co"
PASSWORD = "Admin@12345"
FULL_NAME = "Admin"
# ======================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash(PASSWORD)

c = db_config.connect()
cur = c.cursor()
# discover the users table columns so we insert correctly
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("users columns:", cols)

# insert with the common fields
cur.execute("""
    INSERT INTO users (full_name, email, hashed_password, role, is_active)
    VALUES (%s, %s, %s, 'admin', TRUE)
    ON CONFLICT (email) DO UPDATE SET hashed_password=EXCLUDED.hashed_password, role='admin', is_active=TRUE
""", (FULL_NAME, EMAIL, hashed))
c.commit()
cur.execute("SELECT id, email, role FROM users")
print("users now:", cur.fetchall())
c.close()
print(f"\nADMIN READY -> email: {EMAIL}  password: {PASSWORD}")
