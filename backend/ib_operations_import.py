"""Import Operation Log.xlsx -> ib_operations. FAST batch insert."""
import openpyxl, re, psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
def pdate(s):
    if not s: return None
    s=str(s).strip()
    for f in ('%Y-%m-%dT%H:%M:%S.%f','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%d'):
        try: return datetime.strptime(s[:26],f)
        except: pass
    return None
def acc_id(s):
    m=re.match(r'\s*(\d+)', str(s or '')); return int(m.group(1)) if m else None
def famt(v):
    if v is None or v=='': return 0.0
    if isinstance(v,(int,float)): return float(v)
    m=re.search(r'-?[\d,]+\.?\d*', str(v).replace(',',''))
    return float(m.group()) if m else 0.0

wb=openpyxl.load_workbook(r'C:\Broker-crm\IB setting\Operation Log.xlsx',read_only=True,data_only=True)
data=list(wb.worksheets[0].iter_rows(values_only=True))[1:]; wb.close()
import db_config
conn=db_config.connect();cur=conn.cursor()
cur.execute("""DROP TABLE IF EXISTS ib_operations;
  CREATE TABLE ib_operations(id SERIAL PRIMARY KEY, ext_ib_id INTEGER, ib_id INTEGER, account VARCHAR, name VARCHAR,
    email VARCHAR, request_type VARCHAR, amount DOUBLE PRECISION, converted_amount DOUBLE PRECISION, payment_type VARCHAR,
    status VARCHAR, to_account VARCHAR, referral_id VARCHAR, comment TEXT, op_date TIMESTAMPTZ, action_date TIMESTAMPTZ,
    order_id VARCHAR, note TEXT);
  ALTER TABLE ibs ADD COLUMN IF NOT EXISTS total_payoff DOUBLE PRECISION DEFAULT 0;""")
conn.commit()
cur.execute("SELECT id, ext_ib_id, LOWER(email) FROM ibs")
by_ext={}; by_email={}
for iid,ext,em in cur.fetchall():
    if ext is not None: by_ext.setdefault(ext,iid)
    if em: by_email.setdefault(em,iid)
rows=[]
for r in data:
    if not any(r): continue
    ext=acc_id(r[0]); em=(str(r[2]).strip().lower() if r[2] else '')
    if ext is None and not em: continue   # skip total/summary rows (no IB account/email)
    ib_id=by_ext.get(ext) or by_email.get(em)
    rows.append((ext,ib_id,r[0],r[1],r[2],r[3],famt(r[4]),famt(r[5]),r[6],r[7],r[8],
        str(r[9]) if r[9] else None,r[10],pdate(r[11]),pdate(r[12]),str(r[13]) if r[13] else None,r[14]))
execute_values(cur,"""INSERT INTO ib_operations(ext_ib_id,ib_id,account,name,email,request_type,amount,converted_amount,
    payment_type,status,to_account,referral_id,comment,op_date,action_date,order_id,note) VALUES %s""",rows,page_size=1000)
conn.commit()
cur.execute("CREATE INDEX ix_ibop_ibid ON ib_operations(ib_id); CREATE INDEX ix_ibop_ext ON ib_operations(ext_ib_id)")
cur.execute("UPDATE ibs SET total_payoff=COALESCE((SELECT SUM(o.amount) FROM ib_operations o WHERE o.ib_id=ibs.id AND o.status='Approved'),0)")
conn.commit()
cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE ib_id IS NOT NULL) FROM ib_operations"); print("ops total/linked:",cur.fetchone())
cur.execute("SELECT ROUND(SUM(total_payoff)::numeric,0), COUNT(*) FILTER (WHERE total_payoff>0) FROM ibs"); print("total payoff / IBs:",cur.fetchone())
cur.close();conn.close()
