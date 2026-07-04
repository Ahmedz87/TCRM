"""Run this once to create dialer tables"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS dialer_sessions (
            id          SERIAL PRIMARY KEY,
            agent_id    INTEGER,
            status      VARCHAR(20) DEFAULT 'active',
            source      VARCHAR(20) DEFAULT 'clients',
            filters     TEXT,
            total       INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT NOW(),
            ended_at    TIMESTAMP
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
            id          SERIAL PRIMARY KEY,
            session_id  INTEGER,
            login       INTEGER,
            queue_id    INTEGER,
            agent_id    INTEGER,
            outcome     VARCHAR(30),
            comment     TEXT,
            called_at   TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_dialer_queue_session ON dialer_queue(session_id, status, scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_dialer_logs_login ON dialer_call_logs(login);
    """))
    db.commit()
    print("Dialer tables created!")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
