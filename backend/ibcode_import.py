"""Import IB Code.xlsx: unique IB ID + creation date + master/sub. Match by IBCode(agent_id),
propagate to the email-sibling (MT4/MT5), set parent_ib_id for sub-IBs."""
import openpyxl, re, psycopg2
from datetime import datetime
def pdate(s):
    if not s: return None
    s=re.sub(r'\s+',' ',str(s).strip())
    for fmt in ('%b %d %Y %I:%M%p','%b %d %Y %I:%M %p','%Y-%m-%d %H:%M:%S','%Y-%m-%d'):
        try: return datetime.strptime(s,fmt)
        except: pass
    return None
wb=openpyxl.load_workbook(r'C:\Broker-crm\IB setting\IB Code.xlsx',read_only=True,data_only=True)
data=list(wb.worksheets[0].iter_rows(values_only=True))[1:]; wb.close()

import db_config
conn=db_config.connect();conn.autocommit=True;cur=conn.cursor()
cur.execute("""ALTER TABLE ibs ADD COLUMN IF NOT EXISTS ext_ib_id INTEGER;
  ALTER TABLE ibs ADD COLUMN IF NOT EXISTS ib_creation_date TIMESTAMPTZ;
  ALTER TABLE ibs ADD COLUMN IF NOT EXISTS is_sub_ib BOOLEAN DEFAULT FALSE;""")
# maps
cur.execute("SELECT id, agent_id, LOWER(email) FROM ibs")
rows=cur.fetchall()
by_agent={r[1]:r for r in rows}
email_of={r[0]:r[2] for r in rows}
ids_by_email={}
for r in rows:
    if r[2]: ids_by_email.setdefault(r[2],[]).append(r[0])
code_to_ibid={}  # IBCode(agent_id) -> the my1 ib id (for master lookup)
n_set=n_sub=n_prop=0
subs=[]  # (child_ib_id, master_code)
for r in data:
    extid,name,code,iblevel,master,cdate = r[0],r[1],r[2],r[3],r[4],r[5]
    if code is None: continue
    hit=by_agent.get(code)
    if not hit: continue
    ib_id=hit[0]; code_to_ibid[code]=ib_id
    dt=pdate(cdate); is_sub=(iblevel==2)
    cur.execute("UPDATE ibs SET ext_ib_id=%s, ib_creation_date=%s, is_sub_ib=%s WHERE id=%s",(extid,dt,is_sub,ib_id)); n_set+=1
    # propagate id + date to email siblings (the person's other MT account record)
    em=email_of.get(ib_id)
    if em:
        for sid in ids_by_email.get(em,[]):
            if sid!=ib_id:
                cur.execute("UPDATE ibs SET ext_ib_id=%s, ib_creation_date=COALESCE(ib_creation_date,%s) WHERE id=%s",(extid,dt,sid)); n_prop+=1
    if is_sub and master and str(master).strip().upper()!='NONE':
        subs.append((ib_id, master))
# resolve master/sub -> parent_ib_id (master value is the parent's IBCode)
for child_id, master_code in subs:
    try: mc=int(master_code)
    except: continue
    parent=by_agent.get(mc)
    if parent:
        cur.execute("UPDATE ibs SET parent_ib_id=%s WHERE id=%s",(parent[0],child_id)); n_sub+=1
print(f"ext_ib_id set on matched={n_set}  propagated to siblings={n_prop}  sub-IB parent links={n_sub}/{len(subs)}")
cur.execute("SELECT COUNT(*) FILTER (WHERE ext_ib_id IS NOT NULL), COUNT(*) FILTER (WHERE ib_creation_date IS NOT NULL), COUNT(*) FILTER (WHERE is_sub_ib) FROM ibs")
print("ibs with ext_ib_id / creation_date / is_sub:",cur.fetchone())
cur.close();conn.close()
