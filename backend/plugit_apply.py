"""Apply IB Profile 1.xlsx levels + tags to the CRM (safe, additive, re-runnable)."""
import openpyxl, re, psycopg2

XLSX = r"C:\Broker-crm\IB setting\IB Profile 1.xlsx"

def parse_pips(v):
    if v is None: return None
    s = str(v).strip().lower()
    if s in ('null',''): return None
    m = re.search(r'([\d.]+)', s)
    return float(m.group(1)) if m else None

def pips_to_level(p):
    if p is None: return None
    return max(5, min(10, round(p*10)))

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws = wb.worksheets[0]
rows = list(ws.iter_rows(values_only=True))[1:]
wb.close()
excel = []
for r in rows:
    if r[2] in (None, ''): continue
    p = parse_pips(r[3])
    excel.append({"code": str(r[2]).strip(), "email": (str(r[1]).strip().lower() if r[1] else ""),
                  "name": (str(r[0]).strip() if r[0] else ""), "pips": p, "level": pips_to_level(p)})

import db_config
conn = db_config.connect()
cur = conn.cursor()

# 1) schema (additive)
cur.execute("""
    ALTER TABLE ibs ADD COLUMN IF NOT EXISTS markup_pips DOUBLE PRECISION;
    ALTER TABLE ibs ADD COLUMN IF NOT EXISTS plugit_status VARCHAR;   -- synced | no_plugit_update
    ALTER TABLE ibs ADD COLUMN IF NOT EXISTS ib_level_before_plugit INTEGER;
    CREATE TABLE IF NOT EXISTS ib_plugit (
        code       VARCHAR PRIMARY KEY,
        email      VARCHAR,
        name       VARCHAR,
        pips       DOUBLE PRECISION,
        level      INTEGER,
        in_crm     BOOLEAN DEFAULT FALSE,
        ib_id      INTEGER,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
""")
conn.commit()

cur.execute("SELECT id, agent_id, LOWER(email), ib_level FROM ibs")
ibs = cur.fetchall()
by_code = {str(a[1]): a for a in ibs}
by_email = {}
for a in ibs:
    if a[2]: by_email.setdefault(a[2], a)

seen = set(); n_lvl = 0; n_synced = 0
# 2) reset plugit table + upsert all excel rows; update matched ibs
cur.execute("TRUNCATE ib_plugit")
for e in excel:
    hit = by_code.get(e["code"]) or (by_email.get(e["email"]) if e["email"] else None)
    ib_id = hit[0] if hit else None
    cur.execute("""INSERT INTO ib_plugit (code,email,name,pips,level,in_crm,ib_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (code) DO UPDATE SET email=EXCLUDED.email,name=EXCLUDED.name,
                     pips=EXCLUDED.pips,level=EXCLUDED.level,in_crm=EXCLUDED.in_crm,ib_id=EXCLUDED.ib_id""",
                (e["code"], e["email"], e["name"], e["pips"], e["level"], bool(hit), ib_id))
    if hit:
        seen.add(hit[0]); n_synced += 1
        if e["level"] is not None:
            # store old level once (only if not already stored)
            cur.execute("""UPDATE ibs SET
                             ib_level_before_plugit = COALESCE(ib_level_before_plugit, ib_level),
                             ib_level = %s, markup_pips = %s, plugit_status = 'synced'
                           WHERE id = %s""", (e["level"], e["pips"], hit[0]))
            n_lvl += 1
        else:
            cur.execute("UPDATE ibs SET markup_pips=%s, plugit_status='synced' WHERE id=%s", (e["pips"], hit[0]))

# 3) tag CRM IBs not in excel
cur.execute("UPDATE ibs SET plugit_status='no_plugit_update' WHERE id <> ALL(%s)", (list(seen) or [-1],))
conn.commit()

cur.execute("SELECT plugit_status, COUNT(*) FROM ibs GROUP BY plugit_status ORDER BY 2 DESC")
print("ibs.plugit_status:", cur.fetchall())
cur.execute("SELECT COUNT(*) FROM ib_plugit WHERE in_crm=false")
print("plugit_only (not in CRM):", cur.fetchone()[0])
print(f"levels updated: {n_lvl}   synced ibs: {n_synced}")
cur.close(); conn.close()
