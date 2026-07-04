import psycopg2
from passlib.context import CryptContext
import db_config
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
EMAIL="admin@brokercrm.com"; PASSWORD="Admin@12345"
h = pwd.hash(PASSWORD)
c = db_config.connect()
cur=c.cursor()
cur.execute("""INSERT INTO users (full_name,email,hashed_password,role,is_active)
VALUES ('Admin',%s,%s,'admin',TRUE)
ON CONFLICT (email) DO UPDATE SET hashed_password=EXCLUDED.hashed_password, role='admin', is_active=TRUE""",(EMAIL,h))
c.commit()
cur.execute("SELECT id,email,role FROM users"); print(cur.fetchall())
print(f"READY: {EMAIL} / {PASSWORD}")
