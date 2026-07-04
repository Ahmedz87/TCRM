"""
Persist detected IB promotions (from commission_report_analyze.py) into ib_promotions,
linked to ibs by ext_ib_id. Idempotent: clears source='commission_report' rows then reinserts.
Also stamps ibs.last_promotion_at / last_promotion_level for quick display.
"""
import json, psycopg2, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import db_config

data = json.load(open("C:/Broker-crm/backend/commission_report_result.json", encoding="utf-8"))
promos = data["promotions"]
print("promotions to persist:", len(promos))

con = db_config.connect(); cur = con.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS ib_promotions (
    id           SERIAL PRIMARY KEY,
    ib_id        INTEGER,
    ext_ib_id    BIGINT,
    promo_date   DATE,
    from_level   INTEGER,
    to_level     INTEGER,
    note         TEXT,
    source       TEXT DEFAULT 'commission_report',
    created_at   TIMESTAMPTZ DEFAULT NOW()
)""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ib_promotions_ib ON ib_promotions(ib_id)")
cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS last_promotion_at DATE")
cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS last_promotion_level INTEGER")
cur.execute("DELETE FROM ib_promotions WHERE source='commission_report'")

# map ext_ib_id -> ib id
cur.execute("SELECT ext_ib_id, id FROM ibs WHERE ext_ib_id IS NOT NULL")
ext2id = {str(r[0]): r[1] for r in cur.fetchall()}

ins = 0; unlinked = 0
for p in promos:
    w = str(p["wallet"]); ibid = ext2id.get(w)
    if ibid is None:
        unlinked += 1
    note = f"XAUUSD/major commission-per-lot rose (level {p['from_level']}→{p['to_level']}) in the broker Commission Report"
    cur.execute("""INSERT INTO ib_promotions (ib_id, ext_ib_id, promo_date, from_level, to_level, note, source)
                   VALUES (%s,%s,%s,%s,%s,%s,'commission_report')""",
                (ibid, int(w) if w.isdigit() else None, p["date"], p["from_level"], p["to_level"], note))
    ins += 1

# stamp latest promotion per IB
cur.execute("""
    UPDATE ibs SET last_promotion_at = t.d, last_promotion_level = t.lv
    FROM (SELECT DISTINCT ON (ib_id) ib_id, promo_date d, to_level lv
          FROM ib_promotions WHERE ib_id IS NOT NULL
          ORDER BY ib_id, promo_date DESC) t
    WHERE ibs.id = t.ib_id""")
con.commit()
print(f"inserted {ins} promotions ({unlinked} had no matching IB); ibs stamped.")
cur.execute("SELECT COUNT(*), COUNT(DISTINCT ib_id) FROM ib_promotions WHERE ib_id IS NOT NULL")
print("linked promotions / distinct IBs:", cur.fetchone())
con.close()
