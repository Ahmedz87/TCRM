"""Builds client_sender_blocks: each client -> the Qi sender-blocks (4/5/6-digit) seen in their
deposit history. A new deposit whose txid block is NOT in the client's set is suspicious.
Idempotent. Re-run after OCR batches. Uses the FIXED-anchored parse (unicode-safe)."""
import sys, io, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import db_config
from collections import defaultdict
FIXED="10121420010100166"
def norm(t):
    o=[]
    for ch in (t or ""):
        if ch.isdigit():
            try: o.append(str(unicodedata.digit(ch)))
            except Exception: pass
    return "".join(o)
c=db_config.connect(); c.autocommit=False; cur=c.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS client_sender_blocks(
  client_login BIGINT, block4 TEXT, block5 TEXT, block6 TEXT,
  sender_acct TEXT, n INT, first_seen DATE, last_seen DATE,
  PRIMARY KEY(client_login, block6))""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_csb_login ON client_sender_blocks(client_login)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_csb_b4 ON client_sender_blocks(block4)")
c.commit()
cur.execute("""SELECT d.client_login, q.ocr_txid, COALESCE(q.ocr_sender_acct,''), d.tx_date
  FROM deposit_documents d JOIN pay_qi_card q ON q.receipt_filename=d.receipt_filename
  WHERE d.client_login IS NOT NULL AND q.ocr_txid IS NOT NULL""")
agg=defaultdict(lambda:{"n":0,"snd":"","f":None,"l":None})
for login,tx,snd,txd in cur.fetchall():
    t=norm(tx)
    if len(t)!=37 or t[8:25]!=FIXED: continue
    b6=t[25:31]
    k=(login,b6)
    a=agg[k]; a["n"]+=1
    if snd.strip(): a["snd"]=snd.strip()
    d=str(txd)[:10]
    if a["f"] is None or d<a["f"]: a["f"]=d
    if a["l"] is None or d>a["l"]: a["l"]=d
cur.execute("TRUNCATE client_sender_blocks")
import psycopg2.extras as ex
rows=[(login, b6[:4], b6[:5], b6, a["snd"], a["n"], a["f"], a["l"]) for (login,b6),a in agg.items()]
ex.execute_batch(cur, """INSERT INTO client_sender_blocks
  (client_login,block4,block5,block6,sender_acct,n,first_seen,last_seen)
  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", rows, page_size=1000)
c.commit()
cur.execute("SELECT count(DISTINCT client_login), count(*), count(DISTINCT block4) FROM client_sender_blocks")
cl,rw,b4=cur.fetchone()
print(f"registry: {cl:,} clients | {rw:,} client-block rows | {b4:,} distinct 4-blocks")
# how many clients have exactly ONE 4-block (clean single-sender)?
cur.execute("SELECT client_login, count(DISTINCT block4) FROM client_sender_blocks GROUP BY 1")
one=sum(1 for _,n in cur.fetchall() if n==1)
print(f"clients with a single 4-block (one sender wallet): {one:,}")
c.close()
