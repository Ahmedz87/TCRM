"""
schema_guard.py — tiny helper so "ensure column exists" calls never gridlock the DB.

`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` STILL takes an ACCESS EXCLUSIVE lock even when the
column already exists, so running it every loop/import on a big hot table (deals/clients/leads)
spikes locks and — if any session holds the table — hangs the whole app. This checks
information_schema first (a cheap read, no table lock) and only ALTERs when the column is
genuinely missing, with a short lock_timeout so even that fails fast instead of freezing.

Works with a SQLAlchemy Session (db.execute). For raw psycopg2 use ensure_column_pg(cur, ...).
"""
from sqlalchemy import text


def column_exists(db, table, column):
    return bool(db.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).scalar())


def ensure_column(db, table, column, coldef):
    """SQLAlchemy Session variant. coldef e.g. \"VARCHAR(10) DEFAULT 'MT5'\". Commits on change.
    Returns True if it added the column, False if it already existed / on lock timeout."""
    try:
        if column_exists(db, table, column):
            return False
        db.execute(text("SET lock_timeout = '4s'"))
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coldef}"))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def ensure_column_pg(cur, conn, table, column, coldef):
    """psycopg2 cursor variant (table/column/coldef are trusted literals from the caller)."""
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
            (table, column),
        )
        if cur.fetchone():
            return False
        cur.execute("SET lock_timeout = '4s'")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coldef}")
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
