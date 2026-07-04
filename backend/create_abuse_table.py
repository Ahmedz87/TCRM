import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

db.execute(text("""
CREATE TABLE IF NOT EXISTS abuse_cases (
    id                  SERIAL PRIMARY KEY,
    abuse_type          VARCHAR(50) NOT NULL,
    severity            VARCHAR(20) NOT NULL DEFAULT 'medium',
    login_a             INTEGER NOT NULL,
    login_b             INTEGER,
    all_logins          TEXT,
    symbol              VARCHAR(30),
    risk_score          INTEGER DEFAULT 0,
    confidence          INTEGER DEFAULT 0,
    network_score       INTEGER DEFAULT 0,
    evidence            TEXT,
    total_deposits      FLOAT DEFAULT 0,
    exposure            FLOAT DEFAULT 0,
    status              VARCHAR(20) DEFAULT 'open',
    auto_action         VARCHAR(20),
    auto_action_taken   BOOLEAN DEFAULT FALSE,
    reviewed_by         INTEGER,
    review_note         TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);
"""))

# Indexes for fast queries
for idx in [
    "CREATE INDEX IF NOT EXISTS idx_abuse_severity ON abuse_cases(severity)",
    "CREATE INDEX IF NOT EXISTS idx_abuse_type ON abuse_cases(abuse_type)",
    "CREATE INDEX IF NOT EXISTS idx_abuse_status ON abuse_cases(status)",
    "CREATE INDEX IF NOT EXISTS idx_abuse_login_a ON abuse_cases(login_a)",
    "CREATE INDEX IF NOT EXISTS idx_abuse_created ON abuse_cases(created_at DESC)",
]:
    db.execute(text(idx))

db.commit()
print("✅ abuse_cases table created with indexes")
db.close()
