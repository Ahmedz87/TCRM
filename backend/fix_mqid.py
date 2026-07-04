import db_config
import psycopg2
conn = db_config.connect()
c = conn.cursor()
# check current type of mqid on clients + trading_accounts
for tbl in ["clients", "trading_accounts"]:
    c.execute("""SELECT data_type FROM information_schema.columns
                 WHERE table_name=%s AND column_name='mqid'""", (tbl,))
    r = c.fetchone()
    print(f"{tbl}.mqid is currently:", r[0] if r else "MISSING")
# convert mqid to text on both (text is correct for an identifier)
for tbl in ["clients", "trading_accounts"]:
    try:
        c.execute(f"ALTER TABLE {tbl} ALTER COLUMN mqid TYPE TEXT USING mqid::TEXT")
        print(f"  {tbl}.mqid -> TEXT OK")
    except Exception as e:
        print(f"  {tbl}.mqid: {str(e)[:80]}")
        conn.rollback()
conn.commit()
# also check 'agent' and 'cid' which MT4 might send as empty - make them safe too
for tbl in ["clients", "trading_accounts"]:
    for col in ["cid"]:
        try:
            c.execute(f"ALTER TABLE {tbl} ALTER COLUMN {col} TYPE TEXT USING {col}::TEXT")
            print(f"  {tbl}.{col} -> TEXT OK")
        except Exception as e:
            print(f"  {tbl}.{col}: {str(e)[:60]}")
            conn.rollback()
conn.commit()
conn.close()
print("DONE")
