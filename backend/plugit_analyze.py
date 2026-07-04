"""Read-only analysis of IB Profile 1.xlsx vs the CRM ibs table."""
import openpyxl, re, psycopg2
from collections import Counter

XLSX = r"C:\Broker-crm\IB setting\IB Profile 1.xlsx"

def parse_pips(v):
    if v is None: return None
    s = str(v).strip().lower()
    if s in ('null',''): return None
    m = re.search(r'([\d.]+)', s)
    return float(m.group(1)) if m else None

def pips_to_level(p):
    if p is None: return None, True
    lvl = round(p*10)
    outlier = not (0.5 <= p <= 1.0)   # clean band maps 0.5..1.0 -> 5..10
    return max(5, min(10, lvl)), outlier

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws = wb.worksheets[0]
rows = list(ws.iter_rows(values_only=True))[1:]
wb.close()

excel = []
for r in rows:
    code = r[2]
    if code in (None, ''): continue
    pips = parse_pips(r[3])
    lvl, outlier = pips_to_level(pips)
    excel.append({"code": str(code).strip(), "email": (str(r[1]).strip().lower() if r[1] else ""),
                  "name": r[0], "pips": pips, "level": lvl, "outlier": outlier})

import db_config
conn = db_config.connect()
cur = conn.cursor()
cur.execute("SELECT id, agent_id, ib_code, name, LOWER(email), ib_level FROM ibs")
ibs = cur.fetchall()
by_code = {str(a[1]): a for a in ibs}
by_email = {}
for a in ibs:
    if a[4]: by_email.setdefault(a[4], a)

matched, plugit_only, outliers = [], [], []
seen_ib_ids = set()
for e in excel:
    hit = by_code.get(e["code"]) or (by_email.get(e["email"]) if e["email"] else None)
    if hit:
        matched.append((e, hit)); seen_ib_ids.add(hit[0])
        if e["outlier"]: outliers.append(e)
    else:
        plugit_only.append(e)

no_plugit = [a for a in ibs if a[0] not in seen_ib_ids]

print(f"Excel rows w/ code: {len(excel)}   (null-pips: {sum(1 for e in excel if e['pips'] is None)})")
print(f"CRM ibs total: {len(ibs)}")
print(f"--- MATCHED (update level): {len(matched)}")
print(f"    of which outlier pips (need review): {len(outliers)}")
print(f"--- CRM but NOT in Excel  -> tag 'no_plugit_update': {len(no_plugit)}")
print(f"--- Excel but NOT in CRM  -> tag 'plugit_only': {len(plugit_only)}")
# level change distribution among matched
chg = Counter()
for e, hit in matched:
    if e['level'] and e['level'] != hit[5]: chg[(hit[5], e['level'])] += 1
print("\nLevel changes (old->new): count")
for (o,n),c in sorted(chg.items()):
    print(f"   IB-{o} -> IB-{n}: {c}")
print("\nSample outliers (pips not in 0.5-1.0):")
for e in outliers[:12]:
    print(f"   {e['code']} {e['email']} pips={e['pips']} -> clamped IB-{e['level']}")
cur.close(); conn.close()
