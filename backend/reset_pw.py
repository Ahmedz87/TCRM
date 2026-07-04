import psycopg2
from passlib.context import CryptContext
import db_config
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
h = pwd.hash("Pass1234")
c = db_config.connect()
cur = c.cursor()
cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_valid_after TIMESTAMPTZ")
# changing the password also invalidates all existing JWT sessions for this account
cur.execute("UPDATE users SET hashed_password=%s, tokens_valid_after=NOW() WHERE email=%s",
            (h, "admin@brokercrm.com"))
c.commit()
print("rows updated (old sessions invalidated):", cur.rowcount)
# verify it works immediately
cur.execute("SELECT hashed_password FROM users WHERE email=%s", ("admin@brokercrm.com",))
stored = cur.fetchone()[0]
print("verify Pass1234:", pwd.verify("Pass1234", stored))
c.close()
