"""DRY-RUN (read-only): correct scope = only accounts ALREADY in an IB group get their level fixed."""
import psycopg2, re
from collections import Counter
import db_config
conn = db_config.connect()
cur = conn.cursor()
cur.execute("""
  WITH ib_person AS (
    SELECT i.id ib_id, i.ib_level, i.agent_id, oc.customer_no
    FROM ibs i LEFT JOIN clients oc ON oc.login = i.agent_id
    WHERE i.plugit_status='synced' AND i.ib_level IS NOT NULL
  )
  SELECT DISTINCT p.ib_id, p.ib_level, c.login, COALESCE(c.platform,'MT5') platform, c.group_name
  FROM ib_person p
  JOIN clients c ON (p.customer_no IS NOT NULL AND c.customer_no=p.customer_no) OR c.login=p.agent_id
  WHERE c.group_name ILIKE '%IB-%'
""")
rows = cur.fetchall()
def target(platform, lvl):
    return f"TNFX-IB-{lvl}" if str(platform).upper().startswith('MT4') else f"IB\IB-{lvl}"
changes=[]; already=0
for ib_id,lvl,login,platform,grp in rows:
    tgt=target(platform,lvl)
    if (grp or '')==tgt: already+=1
    else: changes.append((login,platform,grp,tgt))
print(f"IB-group accounts examined: {len(rows)}   already correct: {already}   WOULD change: {len(changes)}")
print("by platform:", dict(Counter(p for _,p,_,_ in changes)))
print("current-group patterns being changed:", dict(Counter(re.sub(r'\d+$','N',(g or '')) for _,_,g,_ in changes).most_common(10)))
print("\nsample (login | platform | current -> target):")
for login,platform,grp,tgt in changes[:20]:
    print(f"   {login} | {platform} | {grp!r} -> {tgt}")
cur.close(); conn.close()
