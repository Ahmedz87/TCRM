"""Import IB Rrferral link.xlsx -> ib_referral_links (old links kept working + linkable)."""
import openpyxl, re, psycopg2
from urllib.parse import urlparse, parse_qs
XLSX = r"C:\Broker-crm\IB setting\IB Rrferral link.xlsx"
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws = wb.worksheets[0]
rows = list(ws.iter_rows(values_only=True))[1:]
wb.close()

def qp(link, key):
    try: return (parse_qs(urlparse(link).query).get(key) or [None])[0]
    except Exception: return None

recs = []
for r in rows:
    email = (str(r[0]).strip().lower() if r[0] else "")
    ibcode = (str(r[1]).strip() if r[1] is not None else "")
    link = (str(r[3]).strip() if r[3] else "")
    if not link: continue
    recs.append({"email": email, "ib_code": ibcode, "banner": (str(r[2]).strip() if r[2] else ""),
                 "link": link, "referrer_id": qp(link,"referrer_id"),
                 "campaign": qp(link,"c") or qp(link,"utm_campaign")})

import db_config
conn = db_config.connect()
cur = conn.cursor()
cur.execute("""
  CREATE TABLE IF NOT EXISTS ib_referral_links (
    id SERIAL PRIMARY KEY,
    ib_id INTEGER, ib_code VARCHAR, email VARCHAR, banner VARCHAR,
    referrer_id VARCHAR, campaign_code VARCHAR, custom_link TEXT,
    source VARCHAR DEFAULT 'plugit', clicks INTEGER DEFAULT 0, created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS ix_ref_campaign ON ib_referral_links(campaign_code);
  CREATE INDEX IF NOT EXISTS ix_ref_ibcode ON ib_referral_links(ib_code);
""")
conn.commit()
# match ib by agent_id (=ib_code) or email
cur.execute("SELECT id, agent_id, LOWER(email) FROM ibs")
ibs = cur.fetchall()
by_code = {str(a[1]): a[0] for a in ibs}
by_email = {}
for a in ibs:
    if a[2]: by_email.setdefault(a[2], a[0])

cur.execute("TRUNCATE ib_referral_links RESTART IDENTITY")
matched = 0
for e in recs:
    ib_id = by_code.get(e["ib_code"]) or by_email.get(e["email"])
    if ib_id: matched += 1
    cur.execute("""INSERT INTO ib_referral_links (ib_id, ib_code, email, banner, referrer_id, campaign_code, custom_link)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (ib_id, e["ib_code"], e["email"], e["banner"], e["referrer_id"], e["campaign"], e["link"]))
conn.commit()
cur.execute("SELECT COUNT(*), COUNT(campaign_code), COUNT(ib_id) FROM ib_referral_links")
tot, wc, wib = cur.fetchone()
print(f"imported links: {tot} | with campaign_code: {wc} | matched to a CRM IB: {wib}")
cur.close(); conn.close()
