"""
fix_db_schema.py
Safely adds any missing columns to existing tables.
NEVER drops or modifies existing columns.
Safe to run multiple times.
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

def add_col(table, col, col_type, default=None):
    """Add a column if it doesn't exist."""
    try:
        exists = db.execute(text(f"""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='{table}' AND column_name='{col}'
        """)).fetchone()
        if exists:
            return False
        default_sql = f"DEFAULT {default}" if default is not None else ""
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type} {default_sql}"))
        db.commit()
        print(f"  ✅ Added {table}.{col}")
        return True
    except Exception as e:
        db.rollback()
        print(f"  ❌ Failed {table}.{col}: {e}")
        return False

def create_table_if_not_exists(sql, name):
    try:
        db.execute(text(sql))
        db.commit()
        print(f"✅ Table {name} ready")
    except Exception as e:
        db.rollback()
        print(f"⚠️  Table {name}: {e}")

print("=== Fixing database schema ===\n")

# ─── clients ─────────────────────────────────────────────────────────────────
print("clients:")
add_col('clients', 'source',           "VARCHAR(50)",  "'none'")
add_col('clients', 'first_deposit_at', "TIMESTAMP",    None)
add_col('clients', 'last_deposit_at',  "TIMESTAMP",    None)
add_col('clients', 'last_trade_at',    "TIMESTAMP",    None)
add_col('clients', 'last_login_at',    "TIMESTAMP",    None)
add_col('clients', 'kyc_status',       "VARCHAR(20)",  "'pending'")
add_col('clients', 'risk_score',       "VARCHAR(20)",  "'low'")
add_col('clients', 'net_deposit',      "NUMERIC(15,2)","0")
add_col('clients', 'cid',              "VARCHAR(100)", "''")
add_col('clients', 'mqid',             "VARCHAR(100)", "''")
add_col('clients', 'free_margin',      "NUMERIC(15,2)","0")
add_col('clients', 'total_volume',     "NUMERIC(15,5)","0")
add_col('clients', 'total_trades',     "INTEGER",      "0")
add_col('clients', 'is_active',        "BOOLEAN",      "TRUE")
add_col('clients', 'is_ib',            "BOOLEAN",      "FALSE")
add_col('clients', 'is_islamic',       "BOOLEAN",      "FALSE")

# ─── trading_accounts ────────────────────────────────────────────────────────
print("\ntrading_accounts:")
add_col('trading_accounts', 'client_id',       "INTEGER",      None)
add_col('trading_accounts', 'source',          "VARCHAR(50)",  "'none'")
add_col('trading_accounts', 'kyc_status',      "VARCHAR(20)",  "'pending'")
add_col('trading_accounts', 'risk_score',      "VARCHAR(20)",  "'low'")
add_col('trading_accounts', 'net_deposit',     "NUMERIC(15,2)","0")
add_col('trading_accounts', 'cid',             "VARCHAR(100)", "''")
add_col('trading_accounts', 'total_volume',    "NUMERIC(15,5)","0")
add_col('trading_accounts', 'total_trades',    "INTEGER",      "0")

# ─── transactions ─────────────────────────────────────────────────────────────
print("\ntransactions:")
add_col('transactions', 'status',      "VARCHAR(20)",  "'approved'")
add_col('transactions', 'notes',       "TEXT",         None)
add_col('transactions', 'created_at',  "TIMESTAMP",    "NOW()")

# ─── ibs ─────────────────────────────────────────────────────────────────────
print("\nibs:")
add_col('ibs', 'parent_ib_id',       "INTEGER",      None)
add_col('ibs', 'ib_level',           "INTEGER",      "5")
add_col('ibs', 'unique_ftds',        "INTEGER",      "0")
add_col('ibs', 'total_clients',      "INTEGER",      "0")
add_col('ibs', 'active_clients',     "INTEGER",      "0")
add_col('ibs', 'total_volume',       "NUMERIC(15,5)","0")
add_col('ibs', 'total_commission',   "NUMERIC(15,2)","0")
add_col('ibs', 'unpaid_commission',  "NUMERIC(15,2)","0")
add_col('ibs', 'paid_commission',    "NUMERIC(15,2)","0")
add_col('ibs', 'referral_clicks',    "INTEGER",      "0")
add_col('ibs', 'balance',            "NUMERIC(15,2)","0")
add_col('ibs', 'email',              "VARCHAR(255)", None)
add_col('ibs', 'city',               "VARCHAR(100)", None)

# ─── users ───────────────────────────────────────────────────────────────────
print("\nusers:")
add_col('users', 'last_login', "TIMESTAMP", None)
add_col('users', 'full_name',  "VARCHAR(255)", "''")

# ─── New tables ──────────────────────────────────────────────────────────────
print("\nNew tables:")

create_table_if_not_exists("""
    CREATE TABLE IF NOT EXISTS score_settings (
        id         SERIAL PRIMARY KEY,
        trigger    VARCHAR(100) UNIQUE NOT NULL,
        points     INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
""", "score_settings")

create_table_if_not_exists("""
    CREATE TABLE IF NOT EXISTS referral_links (
        id         SERIAL PRIMARY KEY,
        ib_id      INTEGER NOT NULL,
        name       VARCHAR(255),
        url        TEXT,
        clicks     INTEGER DEFAULT 0,
        status     VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT NOW()
    )
""", "referral_links")

create_table_if_not_exists("""
    CREATE TABLE IF NOT EXISTS client_assignments (
        id         SERIAL PRIMARY KEY,
        login      INTEGER NOT NULL,
        agent_id   INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(login)
    )
""", "client_assignments")

create_table_if_not_exists("""
    CREATE TABLE IF NOT EXISTS call_actions (
        id                SERIAL PRIMARY KEY,
        login             INTEGER NOT NULL,
        agent_id          INTEGER,
        action            VARCHAR(50) NOT NULL,
        note              TEXT,
        call_later_at     TIMESTAMP,
        passed_to_manager BOOLEAN DEFAULT FALSE,
        created_at        TIMESTAMP DEFAULT NOW()
    )
""", "call_actions")

create_table_if_not_exists("""
    CREATE TABLE IF NOT EXISTS network_edges (
        id         SERIAL PRIMARY KEY,
        login_a    INTEGER NOT NULL,
        login_b    INTEGER NOT NULL,
        reason     VARCHAR(100),
        value      VARCHAR(255),
        weight     NUMERIC(5,2) DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT NOW()
    )
""", "network_edges")

create_table_if_not_exists("""
    CREATE TABLE IF NOT EXISTS ib_commissions (
        id                 SERIAL PRIMARY KEY,
        ib_id              INTEGER NOT NULL,
        ib_login           INTEGER,
        deal_id            INTEGER,
        client_login       INTEGER,
        symbol             VARCHAR(20),
        volume             NUMERIC(15,5) DEFAULT 0,
        pts_per_lot        NUMERIC(10,4) DEFAULT 0,
        quote_currency     VARCHAR(10) DEFAULT 'USD',
        commission_native  NUMERIC(15,4) DEFAULT 0,
        fx_rate            NUMERIC(15,6) DEFAULT 1,
        commission_usd     NUMERIC(15,4) DEFAULT 0,
        commission_type    VARCHAR(20) DEFAULT 'direct',
        override_from_ib   INTEGER,
        trade_date         TIMESTAMP,
        status             VARCHAR(20) DEFAULT 'unpaid',
        created_at         TIMESTAMP DEFAULT NOW()
    )
""", "ib_commissions")

# ─── Indexes ─────────────────────────────────────────────────────────────────
print("\nIndexes:")
indexes = [
    ("idx_clients_phone",        "CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)"),
    ("idx_clients_agent",        "CREATE INDEX IF NOT EXISTS idx_clients_agent ON clients(agent)"),
    ("idx_transactions_login",   "CREATE INDEX IF NOT EXISTS idx_transactions_login ON transactions(login)"),
    ("idx_transactions_type",    "CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(tx_type)"),
    ("idx_transactions_status",  "CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)"),
    ("idx_transactions_date",    "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(tx_date)"),
    ("idx_network_a",            "CREATE INDEX IF NOT EXISTS idx_network_a ON network_edges(login_a)"),
    ("idx_network_b",            "CREATE INDEX IF NOT EXISTS idx_network_b ON network_edges(login_b)"),
    ("idx_call_actions_login",   "CREATE INDEX IF NOT EXISTS idx_call_actions_login ON call_actions(login)"),
    ("idx_ib_comm_ib_id",        "CREATE INDEX IF NOT EXISTS idx_ib_comm_ib_id ON ib_commissions(ib_id)"),
]
for name, sql in indexes:
    try:
        db.execute(text(sql))
        db.commit()
        print(f"  ✅ {name}")
    except Exception as e:
        db.rollback()
        print(f"  ⚠️  {name}: {e}")

db.close()
print("\n=== Done! Run check_db_schema.py to verify ===")
