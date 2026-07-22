"""
Bulk fetch EMAILS (EMail field) + registration date from MT5 → clients
Now using the correct field name 'EMail' (capital M)
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from datetime import datetime

from mt_secrets import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD

import MT5Manager
from database import SessionLocal
from sqlalchemy import text

mgr = MT5Manager.ManagerAPI()
ok = mgr.Connect(MT5_SERVER, MT5_LOGIN, MT5_PASSWORD)
print(f"MT5 Connect: {ok}")
if not ok:
    sys.exit()

users = mgr.UserGetByGroup("*") or []
print(f"Got {len(users)} users")

# Make sure clients has a reg_date column
db = SessionLocal()
db.rollback()
try:
    db.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS mt_registration TIMESTAMP;"))
    db.commit()
except Exception as e:
    db.rollback()
    print(f"Column note: {e}")

updated_email = 0
updated_reg = 0
saved_ident = 0
try:
    for u in users:
        login = getattr(u, 'Login', 0)
        email = (getattr(u, 'EMail', '') or '').strip()
        reg   = getattr(u, 'Registration', 0)
        if not login:
            continue

        if email and '@' in email:
            r = db.execute(text("""
                UPDATE clients SET email = :email
                WHERE login = :login AND (email IS NULL OR email = '' OR email LIKE '%@email.com')
            """), {"email": email, "login": login})
            if r.rowcount > 0:
                updated_email += 1

            # save identifier
            try:
                ex = db.execute(text("""
                    SELECT 1 FROM account_identifiers
                    WHERE login=:l AND identifier_type='email' AND identifier_value=:e
                """), {"l": login, "e": email}).fetchone()
                if not ex:
                    db.execute(text("""
                        INSERT INTO account_identifiers (login, identifier_type, identifier_value)
                        VALUES (:l, 'email', :e)
                    """), {"l": login, "e": email})
                    saved_ident += 1
            except Exception:
                pass

        if reg and reg > 0:
            reg_dt = datetime.fromtimestamp(reg)
            db.execute(text("""
                UPDATE clients SET mt_registration = :reg WHERE login = :login
            """), {"reg": reg_dt, "login": login})
            updated_reg += 1

        if (updated_email + updated_reg) % 1000 == 0 and (updated_email+updated_reg) > 0:
            db.commit()
            print(f"  Progress: {updated_email} emails, {updated_reg} reg dates...")

    db.commit()
    print(f"\nDone!")
    print(f"  Emails added:        {updated_email}")
    print(f"  Reg dates added:     {updated_reg}")
    print(f"  Email identifiers:   {saved_ident}")

    cov = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE email IS NOT NULL AND email != '' AND email NOT LIKE '%@email.com') as real_email,
               COUNT(*) FILTER (WHERE mt_registration IS NOT NULL) as has_reg,
               COUNT(*) as total FROM clients
    """)).fetchone()
    print(f"  Real email coverage: {cov[0]:,} / {cov[2]:,}")
    print(f"  Reg date coverage:   {cov[1]:,} / {cov[2]:,}")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
    mgr.Disconnect()
