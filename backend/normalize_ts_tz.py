"""One-time backfill: TradeSoft-sourced transactions (deal_id 8e9-9e9) were stamped in
BAGHDAD local time (UTC+3) while MT rows are UTC. Shift tx_date/tx_month/created_at by
-3h so the whole column is UTC. Idempotent-ish: guarded by a marker table so it can never
run twice (a second -3h shift would corrupt the data)."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import db_config
conn = db_config.connect(); cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS one_time_migrations (name TEXT PRIMARY KEY, run_at TIMESTAMPTZ DEFAULT NOW())""")
cur.execute("SELECT 1 FROM one_time_migrations WHERE name='ts_tx_tz_normalize_utc'")
if cur.fetchone():
    print("ALREADY RUN — aborting (a second shift would corrupt timestamps)."); sys.exit(0)

cur.execute("""SELECT COUNT(*) FROM transactions
  WHERE deal_id>=8000000000 AND deal_id<9000000000 AND tx_date ~ '^[0-9]{4}-'""")
n = cur.fetchone()[0]
print(f"shifting {n} TradeSoft rows by -3h ...")

cur.execute("""UPDATE transactions SET
    tx_date   = to_char(tx_date::timestamp - interval '3 hours','YYYY-MM-DD HH24:MI:SS'),
    tx_month  = to_char(tx_date::timestamp - interval '3 hours','YYYY-MM'),
    created_at = created_at - interval '3 hours',
    updated_at = NOW()
  WHERE deal_id>=8000000000 AND deal_id<9000000000 AND tx_date ~ '^[0-9]{4}-'""")
print(f"updated: {cur.rowcount}")
cur.execute("INSERT INTO one_time_migrations (name) VALUES ('ts_tx_tz_normalize_utc')")
conn.commit()

cur.execute("""SELECT tx_date, created_at AT TIME ZONE 'UTC' FROM transactions
  WHERE deal_id>=8000000000 AND deal_id<9000000000 ORDER BY deal_id DESC LIMIT 3""")
print("newest TS rows now:", [str(r[0]) for r in cur.fetchall()])
conn.close()
