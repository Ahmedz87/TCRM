"""PHASE A — feed IB Profile 2.xlsx into My1 by EMAIL. Idempotent (self-cleans partial runs)."""
import openpyxl, re, psycopg2
XLSX = r"C:\Broker-crm\IB setting\IB Profile 2.xlsx"
def parse_pips(v):
    if v is None: return None
    s=str(v).strip().lower()
    if s in ('null',''): return None
    m=re.search(r'([\d.]+)', s); return float(m.group(1)) if m else None
def digits(s): 
    d=re.sub(r'\D','',str(s)); return int(d) if d else None

wb=openpyxl.load_workbook(XLSX,read_only=True,data_only=True); ws=wb.worksheets[0]
rows=list(ws.iter_rows(values_only=True))[1:]; wb.close()
recs=[]
for r in rows:
    ag=digits(r[2]) if r[2] not in (None,'') else None
    if ag is None: continue
    pips=parse_pips(r[3]); lvl = 0 if pips is None else max(5,min(9,round(pips*10)))
    recs.append({"agent":ag,"code":str(r[2]).strip(),"email":(str(r[1]).strip().lower() if r[1] else ""),
                 "name":(str(r[0]).strip() if r[0] else ""),"pips":pips,"level":lvl,"is_null":pips is None})
print("excel recs:",len(recs))

import db_config
conn=db_config.connect();conn.autocommit=True;cur=conn.cursor()
cur.execute("""ALTER TABLE ibs ADD COLUMN IF NOT EXISTS markup_pips DOUBLE PRECISION;
  ALTER TABLE ibs ADD COLUMN IF NOT EXISTS plugit_status VARCHAR;
  ALTER TABLE ibs ADD COLUMN IF NOT EXISTS ib_level_before_plugit INTEGER;
  ALTER TABLE ibs ADD COLUMN IF NOT EXISTS is_plugit_created BOOLEAN DEFAULT FALSE;
  CREATE UNIQUE INDEX IF NOT EXISTS ibs_agent_id_uq ON ibs(agent_id);""")
# SELF-CLEAN any prior run
cur.execute("DELETE FROM ibs WHERE is_plugit_created=TRUE")
cur.execute("UPDATE ibs SET ib_level=ib_level_before_plugit WHERE ib_level_before_plugit IS NOT NULL")
cur.execute("UPDATE ibs SET markup_pips=NULL,plugit_status=NULL,ib_level_before_plugit=NULL,is_plugit_created=FALSE")
cur.execute("""DROP TABLE IF EXISTS ib_plugit;
  CREATE TABLE ib_plugit(code VARCHAR PRIMARY KEY,email VARCHAR,name VARCHAR,pips DOUBLE PRECISION,
    level INTEGER,is_null BOOLEAN,in_crm BOOLEAN,ib_id INTEGER);""")

from collections import defaultdict
cur.execute("SELECT id, agent_id, LOWER(email) FROM ibs")
ibs=cur.fetchall()
by_email=defaultdict(list)
for a in ibs:
    if a[2]: by_email[a[2]].append(a)
by_agent={a[1]:a for a in ibs}
seen=set(); n_upd=n_new=n_null=0
for e in recs:
    # a person can have BOTH an MT4 and MT5 IB record (same email) -> update ALL of them
    matches=list(by_email.get(e["email"], [])) if e["email"] else []
    ag=by_agent.get(e["agent"])
    if ag and ag not in matches: matches.append(ag)
    if matches:
        for hit in matches:
            ib_id=hit[0]; seen.add(ib_id)
            if e["is_null"]:
                cur.execute("UPDATE ibs SET ib_level_before_plugit=COALESCE(ib_level_before_plugit,ib_level),ib_level=0,markup_pips=0,plugit_status='null' WHERE id=%s",(ib_id,)); n_null+=1
            else:
                cur.execute("UPDATE ibs SET ib_level_before_plugit=COALESCE(ib_level_before_plugit,ib_level),ib_level=%s,markup_pips=%s,plugit_status='synced' WHERE id=%s",(e["level"],e["pips"],ib_id)); n_upd+=1
        cur.execute("INSERT INTO ib_plugit VALUES(%s,%s,%s,%s,%s,%s,TRUE,%s) ON CONFLICT (code) DO NOTHING",(e["code"],e["email"],e["name"],e["pips"],e["level"],e["is_null"],matches[0][0]))
    else:
        # permanently-removed IBs (ib_removed / remove_from_IB.xlsx Jul 2026) must never come back
        # via a future Plugit export — skip by agent OR email.
        cur.execute("SELECT 1 FROM ib_removed WHERE agent_id=%s OR (COALESCE(%s,'')<>'' AND LOWER(email)=LOWER(%s)) LIMIT 1",
                    (e["agent"], e["email"], e["email"]))
        if cur.fetchone():
            continue
        status='null' if e["is_null"] else 'plugit_only'
        cur.execute("""INSERT INTO ibs(agent_id,ib_code,name,email,ib_level,markup_pips,plugit_status,is_plugit_created,total_clients)
            VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE,0) ON CONFLICT (agent_id) DO NOTHING RETURNING id""",
            (e["agent"],'IB'+str(e["agent"]),e["name"] or ('IB '+str(e["agent"])),e["email"],
             0 if e["is_null"] else e["level"],0 if e["is_null"] else e["pips"],status))
        row=cur.fetchone()
        if row: newid=row[0]; seen.add(newid); n_new+=(0 if e["is_null"] else 1); n_null+=(1 if e["is_null"] else 0)
        cur.execute("INSERT INTO ib_plugit VALUES(%s,%s,%s,%s,%s,%s,FALSE,%s) ON CONFLICT (code) DO NOTHING",(e["code"],e["email"],e["name"],e["pips"],e["level"],e["is_null"],row[0] if row else None))
cur.execute("UPDATE ibs SET plugit_status='no_plugit_update' WHERE id <> ALL(%s) AND COALESCE(plugit_status,'')=''",(list(seen) or [-1],))
print(f"synced(updated)={n_upd}  null={n_null}  created_plugit_only={n_new}")
cur.execute("SELECT plugit_status,COUNT(*) FROM ibs GROUP BY plugit_status ORDER BY 2 DESC"); print("plugit_status:",dict(cur.fetchall()))
cur.execute("SELECT COUNT(*) FROM ibs"); print("total ibs now:",cur.fetchone()[0])
cur.close();conn.close()
