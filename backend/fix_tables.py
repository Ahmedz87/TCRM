import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text

with engine.begin() as conn:
    # Real missing columns
    for sql in [
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS comment TEXT",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS login BIGINT",
        "ALTER TABLE ibs ADD COLUMN IF NOT EXISTS login BIGINT",
        "ALTER TABLE ibs ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(text(sql))
            print(f"OK: {sql[:55]}")
        except Exception as e:
            print(f"ERR: {str(e)[:60]}")

    # Create neg_cover_log table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS neg_cover_log (
            id SERIAL PRIMARY KEY,
            login BIGINT,
            platform VARCHAR DEFAULT 'MT5',
            deficit DOUBLE PRECISION,
            cover_amount DOUBLE PRECISION,
            balance_before DOUBLE PRECISION,
            balance_after DOUBLE PRECISION,
            credit_before DOUBLE PRECISION,
            credit_after DOUBLE PRECISION,
            status VARCHAR,
            mode VARCHAR,
            agent_id INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    print("OK: neg_cover_log table")

    # Create abuse_cases table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS abuse_cases (
            id SERIAL PRIMARY KEY,
            login_a BIGINT,
            login_b BIGINT,
            all_logins VARCHAR,
            abuse_type VARCHAR,
            severity VARCHAR,
            risk_score INTEGER,
            evidence TEXT,
            status VARCHAR DEFAULT 'open',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    print("OK: abuse_cases table")

print("Done.")
