"""
setup_ib_profiles.py — commission PROFILE builder (replaces the earlier level x layer grid).

Run once:  python setup_ib_profiles.py

A profile is one commission rule:
  name            free text, e.g. "IB-5 / Gold"
  ib_level        which IB level it applies to (parsed from IB account group_name, e.g. 'IB-5')
  account_types   which client layers it covers: {'standard','vip',...}; empty = ANY layer
  asset_class     'forex'|'metal'|'crypto'|'equity'|'index'|'energy'; used when match_symbols is empty
  match_symbols   explicit BASE symbols, e.g. {'XAUUSD'} or {'BTCUSD'}; empty = match by asset_class
  match_suffixes  e.g. {'', '.c', '.v', '.x'}; empty = ANY suffix
  points          per 1.0 lot, paid in the symbol's quote currency
  min_hold_minutes hold-time floor (captured now; enforced once deals get a position_id)
  priority        lower wins when two profiles match the same trade (explicit symbols default lower)

Draft vs live: editing sets published=FALSE on that profile. Publish flips active profiles to TRUE.
The commission calc reads ONLY (published=TRUE AND active=TRUE) profiles.

NOTE: the old grid tables (ib_levels, ib_layers, ib_rate_card, ib_flat_rate) are superseded.
You can drop them once this is in use:  DROP TABLE ib_rate_card, ib_flat_rate, ib_levels, ib_layers;
"""
import os
import db_config
import psycopg2

DB = dict(
    host=os.getenv("PGHOST", db_config.DB_HOST), port=os.getenv("PGPORT", db_config.DB_PORT),
    dbname=os.getenv("PGDATABASE", db_config.DB_NAME), user=os.getenv("PGUSER", db_config.DB_USER),
    password=os.getenv("PGPASSWORD", db_config.DB_PASSWORD),
)

DDL = """
CREATE TABLE IF NOT EXISTS ib_profiles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    ib_level TEXT NOT NULL,
    account_types TEXT[] NOT NULL DEFAULT '{}',
    asset_class TEXT,
    match_symbols TEXT[] NOT NULL DEFAULT '{}',
    match_suffixes TEXT[] NOT NULL DEFAULT '{}',
    points NUMERIC(12,4) NOT NULL DEFAULT 0,
    min_hold_minutes INT NOT NULL DEFAULT 0,
    priority INT NOT NULL DEFAULT 100,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ib_profile_meta (
    id INT PRIMARY KEY DEFAULT 1,
    last_published_at TIMESTAMPTZ,
    CONSTRAINT one_row CHECK (id = 1)
);
"""

# Real levels found in your group_name data
LEVELS = ["IB-3", "IB-5", "IB-6", "IB-7", "IB-8", "IB-9"]

# A starter template (for IB-5) — the "standard" you can edit and duplicate to other levels.
# asset_class drives matching; suffixes empty = all account variants; points 0 = fill in.
# priority: explicit-symbol rules (Gold/Silver) beat broad asset_class rules.
STARTER = [
    # name,            asset_class, match_symbols,  suffixes, points, priority
    ("FX",             "forex",     [],             [],       0,      100),
    ("Gold",           "metal",     ["XAUUSD"],     [],       0,       50),
    ("Silver",         "metal",     ["XAGUSD"],     [],       0,       50),
    ("Crypto",         "crypto",    [],             [],       0,      100),
    ("Equities / US shares", "equity", [],          [],       0,      100),
    ("Indices",        "index",     [],             [],       0,      100),
    ("Energy / Oil",   "energy",    [],             [],       0,      100),
]


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("INSERT INTO ib_profile_meta (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM ib_profiles")
    if cur.fetchone()[0] == 0:
        lvl = "IB-5"
        for name, ac, syms, sufs, pts, prio in STARTER:
            cur.execute("""INSERT INTO ib_profiles
                (name, ib_level, asset_class, match_symbols, match_suffixes, points, priority)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (f"{lvl} / {name}", lvl, ac, syms, sufs, pts, prio))
        print(f"Seeded {len(STARTER)} starter profiles for {lvl}. "
              f"Edit them, set points, then Duplicate to other levels in the UI.")
    else:
        print("ib_profiles already has rows — left untouched.")

    conn.commit()
    print("Levels available:", ", ".join(LEVELS))
    conn.close()
    print("Done. Nothing is published yet.")


if __name__ == "__main__":
    main()
