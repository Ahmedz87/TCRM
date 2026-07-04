"""
Create the bonus-system tables (additive, IF NOT EXISTS) and seed the config row.
Idempotent — safe to run repeatedly. Run once after deploy:  python bonus_setup.py
"""
import json
from sqlalchemy import text
from database import SessionLocal
from bonus_engine import DEFAULTS

DDL = [
    # singleton config (JSONB blob so the desk + AI bot read one place)
    """
    CREATE TABLE IF NOT EXISTS bonus_config (
        id INT PRIMARY KEY,
        data JSONB NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """,
    # special/time-limited offers configured in Settings
    """
    CREATE TABLE IF NOT EXISTS bonus_offers (
        id SERIAL PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        percent NUMERIC NOT NULL DEFAULT 0,
        cap NUMERIC NOT NULL DEFAULT 0,          -- max bonus $ (0 = uncapped)
        min_deposit NUMERIC NOT NULL DEFAULT 0,
        countries JSONB DEFAULT '[]'::jsonb,     -- allow-list ([] = all, minus blocked)
        starts_at TIMESTAMP,
        ends_at TIMESTAMP,                        -- deadline
        active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    # every bonus credited (or reserved), with clawback tracking
    """
    CREATE TABLE IF NOT EXISTS bonus_grants (
        id SERIAL PRIMARY KEY,
        client_id INT,
        login BIGINT,
        kind VARCHAR(20) NOT NULL,                -- welcome|deposit_50|deposit_20|special|manual
        offer_id INT,
        deposit_request_id INT,
        deposit_amount NUMERIC DEFAULT 0,
        amount NUMERIC NOT NULL DEFAULT 0,
        clawed_back NUMERIC DEFAULT 0,
        status VARCHAR(16) DEFAULT 'credited',    -- credited|clawed_back|cancelled
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_bonus_grants_client ON bonus_grants(client_id)",
    "CREATE INDEX IF NOT EXISTS ix_bonus_grants_dep ON bonus_grants(deposit_request_id)",
    # one special-offer claim per client
    """
    CREATE TABLE IF NOT EXISTS bonus_offer_claims (
        id SERIAL PRIMARY KEY,
        offer_id INT NOT NULL,
        client_id INT NOT NULL,
        deposit_request_id INT,
        amount NUMERIC DEFAULT 0,
        claimed_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (offer_id, client_id)
    )
    """,
    # welcome-bonus per-client state
    """
    CREATE TABLE IF NOT EXISTS bonus_welcome (
        client_id INT PRIMARY KEY,
        login BIGINT,
        status VARCHAR(20) DEFAULT 'pending',     -- pending|claimed|not_eligible
        reason VARCHAR(200),
        amount NUMERIC DEFAULT 0,
        claimed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """,
]


def main():
    db = SessionLocal()
    try:
        for stmt in DDL:
            db.execute(text(stmt))
        db.commit()
        # seed config row if missing
        exists = db.execute(text("SELECT COUNT(*) FROM bonus_config WHERE id=1")).scalar()
        if not exists:
            db.execute(text("INSERT INTO bonus_config (id, data) VALUES (1, CAST(:d AS JSONB))"),
                       {"d": json.dumps(DEFAULTS)})
            db.commit()
            print("Seeded bonus_config with defaults.")
        else:
            print("bonus_config already present.")
        print("Bonus tables ready:", ", ".join(
            ["bonus_config", "bonus_offers", "bonus_grants", "bonus_offer_claims", "bonus_welcome"]))
    finally:
        db.close()


if __name__ == "__main__":
    main()
