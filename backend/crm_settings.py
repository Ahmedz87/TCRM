"""
crm_settings.py — tiny key/value settings store (the `settings`/`app_settings` tables don't exist).

Used for tunable business constants that the desk edits from the UI, e.g. the sales UNIT bonus
($ per NDA first-deposit). Values are stored as text; helpers cast on read.

    get_setting(db, 'sales_unit_usd', 10.0)   -> float
    set_setting(db, 'sales_unit_usd', 12)     -> persists

Table auto-creates on first import. Seeds sales_unit_usd=10.
"""
from sqlalchemy import text

DEFAULTS = {
    "sales_unit_usd": "10",   # $ per NDA first-time deposit (sales unit bonus)
}


def ensure(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS crm_settings (
            key VARCHAR(80) PRIMARY KEY,
            val TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    for k, v in DEFAULTS.items():
        db.execute(text("INSERT INTO crm_settings (key, val) VALUES (:k, :v) "
                        "ON CONFLICT (key) DO NOTHING"), {"k": k, "v": v})
    db.commit()


def get_setting(db, key, default=None):
    try:
        row = db.execute(text("SELECT val FROM crm_settings WHERE key=:k"), {"k": key}).fetchone()
    except Exception:
        db.rollback(); ensure(db)
        row = db.execute(text("SELECT val FROM crm_settings WHERE key=:k"), {"k": key}).fetchone()
    if not row or row[0] is None:
        return default
    return row[0]


def get_float(db, key, default=0.0):
    v = get_setting(db, key, None)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def set_setting(db, key, val):
    db.execute(text("""
        INSERT INTO crm_settings (key, val, updated_at) VALUES (:k, :v, NOW())
        ON CONFLICT (key) DO UPDATE SET val=EXCLUDED.val, updated_at=NOW()"""),
        {"k": key, "v": str(val)})
    db.commit()
    return val


if __name__ == "__main__":
    from database import SessionLocal
    db = SessionLocal()
    try:
        ensure(db)
        print("sales_unit_usd =", get_float(db, "sales_unit_usd", 10.0))
    finally:
        db.close()
