"""Run this to: 1) create tables, 2) register router in main.py"""
import sys, os
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

# Step 1: Create tables
print("=== Creating dialer tables ===")
db = SessionLocal()
db.rollback()
try:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS dialer_sessions (
            id         SERIAL PRIMARY KEY,
            agent_id   INTEGER,
            status     VARCHAR(20) DEFAULT 'active',
            source     VARCHAR(20) DEFAULT 'clients',
            filters    TEXT,
            total      INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            ended_at   TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS dialer_queue (
            id           SERIAL PRIMARY KEY,
            session_id   INTEGER REFERENCES dialer_sessions(id),
            login        INTEGER,
            lead_id      INTEGER,
            position     INTEGER DEFAULT 0,
            status       VARCHAR(20) DEFAULT 'pending',
            attempt      INTEGER DEFAULT 0,
            scheduled_at TIMESTAMP,
            created_at   TIMESTAMP DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dialer_queue_login
            ON dialer_queue(session_id, login) WHERE login IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dialer_queue_lead
            ON dialer_queue(session_id, lead_id) WHERE lead_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS dialer_call_logs (
            id         SERIAL PRIMARY KEY,
            session_id INTEGER,
            login      INTEGER,
            lead_id    INTEGER,
            queue_id   INTEGER,
            agent_id   INTEGER,
            outcome    VARCHAR(30),
            comment    TEXT,
            called_at  TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_dialer_queue_session
            ON dialer_queue(session_id, status, scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_dialer_logs_login
            ON dialer_call_logs(login);
    """))
    db.commit()
    print("  ✓ Tables created!")
except Exception as e:
    db.rollback()
    print(f"  ✗ Error: {e}")
finally:
    db.close()

# Step 2: Register router in main.py
print("\n=== Registering dialer router in main.py ===")
main_path = r'C:\broker-crm\backend\main.py'
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'power_dialer_router' in content:
    print("  ✓ Already registered")
else:
    # Find last router import and add after it
    import_lines = [l for l in content.split('\n') if 'import router as' in l]
    if import_lines:
        last_import = import_lines[-1]
        content = content.replace(
            last_import,
            last_import + '\nfrom power_dialer_router import router as dialer_router'
        )
    # Find last include_router and add after it
    include_lines = [l for l in content.split('\n') if 'include_router' in l]
    if include_lines:
        last_include = include_lines[-1]
        content = content.replace(
            last_include,
            last_include + '\napp.include_router(dialer_router)'
        )
    with open(main_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓ Registered!")

print("\nDone! Now restart the backend (Terminal 2: Ctrl+C then uvicorn main:app --reload)")
