"""REVERT the Jul 14 -3h TradeSoft shift: MT's clock turned out to be GMT+3 (same as
TradeSoft, verified against old CRM + MT terminals + per-deposit stamp comparison), so
tx_date was ALREADY uniformly Baghdad local and the shift broke consistency. +3h back.
Guarded exactly-once via one_time_migrations."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import db_config
conn = db_config.connect(); cur = conn.cursor()
cur.execute("SELECT 1 FROM one_time_migrations WHERE name='ts_tx_tz_normalize_utc'")
if not cur.fetchone():
    print("original shift not recorded — nothing to revert"); sys.exit(0)
cur.execute("SELECT 1 FROM one_time_migrations WHERE name='ts_tx_tz_reverted'")
if cur.fetchone():
    print("ALREADY REVERTED — aborting"); sys.exit(0)
cur.execute("""UPDATE transactions SET
    tx_date   = to_char(tx_date::timestamp + interval '3 hours','YYYY-MM-DD HH24:MI:SS'),
    tx_month  = to_char(tx_date::timestamp + interval '3 hours','YYYY-MM'),
    created_at = created_at + interval '3 hours',
    updated_at = NOW()
  WHERE deal_id>=8000000000 AND deal_id<9000000000 AND tx_date ~ '^[0-9]{4}-'""")
print(f"reverted: {cur.rowcount} rows (+3h)")
cur.execute("INSERT INTO one_time_migrations (name) VALUES ('ts_tx_tz_reverted')")
conn.commit()
cur.execute("""SELECT tx_date FROM transactions WHERE deal_id>=8000000000 AND deal_id<9000000000
  ORDER BY deal_id DESC LIMIT 3""")
print("newest TS rows now:", [r[0] for r in cur.fetchall()])
conn.close()
