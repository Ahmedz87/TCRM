"""
fix_db_schema2.py — Fix remaining 5 issues
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

def run(sql, msg):
    try:
        db.execute(text(sql))
        db.commit()
        print(f"  ✅ {msg}")
    except Exception as e:
        db.rollback()
        print(f"  ⚠️  {msg}: {e}")

print("=== Fix 1: clients.account_type ===")
run("ALTER TABLE clients ADD COLUMN IF NOT EXISTS account_type VARCHAR(20) DEFAULT 'STD'", "clients.account_type")

print("\n=== Fix 2: ib_commissions missing columns ===")
for col, typ, default in [
    ("ib_login",          "INTEGER",       "NULL"),
    ("client_login",      "INTEGER",       "NULL"),
    ("pts_per_lot",       "NUMERIC(10,4)", "0"),
    ("quote_currency",    "VARCHAR(10)",   "'USD'"),
    ("commission_native", "NUMERIC(15,4)", "0"),
    ("fx_rate",           "NUMERIC(15,6)", "1"),
    ("commission_usd",    "NUMERIC(15,4)", "0"),
    ("commission_type",   "VARCHAR(20)",   "'direct'"),
    ("override_from_ib",  "INTEGER",       "NULL"),
    ("trade_date",        "TIMESTAMP",     "NULL"),
]:
    run(f"ALTER TABLE ib_commissions ADD COLUMN IF NOT EXISTS {col} {typ} DEFAULT {default}", f"ib_commissions.{col}")

print("\n=== Fix 3: client_assignments.created_at ===")
run("ALTER TABLE client_assignments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()", "client_assignments.created_at")

print("\n=== Fix 4: score_settings — drop and recreate correctly ===")
# The table exists but with wrong columns — check what's there
try:
    cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='score_settings'")).fetchall()
    print(f"  Current score_settings columns: {[c[0] for c in cols]}")
    # Drop and recreate
    run("DROP TABLE IF EXISTS score_settings", "drop score_settings")
    run("""
        CREATE TABLE score_settings (
            id         SERIAL PRIMARY KEY,
            trigger    VARCHAR(100) UNIQUE NOT NULL,
            points     INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """, "recreate score_settings")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== Fix 5: deals missing columns (deal, time, digits, asset) ===")
# These are old MT5 column names — check what exists
try:
    cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='deals' ORDER BY ordinal_position")).fetchall()
    print(f"  Deals columns: {[c[0] for c in cols]}")
    # These may be named differently — add aliases
    run("ALTER TABLE deals ADD COLUMN IF NOT EXISTS deal INTEGER DEFAULT 0", "deals.deal")
    run("ALTER TABLE deals ADD COLUMN IF NOT EXISTS time BIGINT DEFAULT 0", "deals.time")
    run("ALTER TABLE deals ADD COLUMN IF NOT EXISTS digits INTEGER DEFAULT 2", "deals.digits")
    run("ALTER TABLE deals ADD COLUMN IF NOT EXISTS asset VARCHAR(50) DEFAULT ''", "deals.asset")
except Exception as e:
    print(f"  Error: {e}")

db.close()
print("\n=== Done! Run check_db_schema.py to verify ===")
