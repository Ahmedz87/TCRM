#!/usr/bin/env python3
"""
Apply OCR'd KYC ID fields (ts_kyc_documents.ocr_json) to BOTH clients and leads.
Fills reg fields only where currently NULL (non-destructive). Idempotent — safe to re-run as more
KYC docs finish OCR. Merges a person's id_front + id_back extractions.
"""
import psycopg2, re, datetime
import db_config
PG = db_config.DSN

def parse_date(v):
    if not v or not isinstance(v,str): return None
    v=v.strip()
    for f in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%m/%d/%Y","%d.%m.%Y","%Y/%m/%d"):
        try: return datetime.datetime.strptime(v,f).date()
        except: pass
    m=re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",v)
    if m:
        try: return datetime.date(int(m[1]),int(m[2]),int(m[3]))
        except: return None
    return None

def merge(docs):
    m={}
    for d in docs or []:
        for k,v in (d or {}).items():
            if k.startswith("_"): continue
            if v and not m.get(k): m[k]=v
    return m

def ensure_cols(cur, table):
    for col,typ in [("id_number","TEXT"),("mother_name","TEXT"),("id_issue_date","DATE"),
                    ("id_expiry_date","DATE"),("place_of_birth","TEXT"),("date_of_birth","DATE"),
                    ("id_type","TEXT"),("kyc_ocr_source","TEXT"),("kyc_ocr_at","TIMESTAMP")]:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")

def apply_for(cur, key_col, table, dob_is_text=False):
    cur.execute(f"""SELECT {key_col}, jsonb_agg(ocr_json) FILTER (WHERE ocr_json IS NOT NULL)
                    FROM ts_kyc_documents
                    WHERE {key_col} IS NOT NULL AND ocr_status='done' AND doc_type IN ('id_front','id_back')
                    GROUP BY {key_col}""")
    rows=cur.fetchall(); touched=0
    for kid, docs in rows:
        m=merge(docs)
        dob=parse_date(m.get("date_of_birth"))
        dob_val = (dob.isoformat() if dob else None) if dob_is_text else dob   # clients.date_of_birth is TEXT
        vals=(dob_val, (m.get("id_number") or "").strip() or None,
              (m.get("mother_name") or "").strip() or None, parse_date(m.get("issue_date")),
              parse_date(m.get("expiry_date")), (m.get("place_of_birth") or "").strip() or None, kid)
        cur.execute(f"""UPDATE {table} SET
            date_of_birth=COALESCE(date_of_birth,%s), id_number=COALESCE(id_number,%s),
            mother_name=COALESCE(mother_name,%s), id_issue_date=COALESCE(id_issue_date,%s),
            id_expiry_date=COALESCE(id_expiry_date,%s), place_of_birth=COALESCE(place_of_birth,%s),
            id_type=COALESCE(id_type,'national_id'), kyc_ocr_source='tradesoft_kyc_ocr', kyc_ocr_at=now()
            WHERE id=%s""", vals)
        touched+=cur.rowcount
    return len(rows), touched

def main():
    pg=psycopg2.connect(PG); pg.autocommit=False; cur=pg.cursor()
    ensure_cols(cur,"leads"); pg.commit()
    nc,tc=apply_for(cur,"client_id","clients", dob_is_text=True); pg.commit()
    nl,tl=apply_for(cur,"lead_id","leads", dob_is_text=False); pg.commit()
    print(f"clients: {nc} people updated; leads: {nl} people updated")
    for tbl in ("clients","leads"):
        cur.execute(f"""SELECT count(*) FILTER (WHERE kyc_ocr_at IS NOT NULL),
          count(*) FILTER (WHERE id_number IS NOT NULL), count(*) FILTER (WHERE mother_name IS NOT NULL),
          count(*) FILTER (WHERE date_of_birth IS NOT NULL), count(*) FILTER (WHERE id_expiry_date IS NOT NULL)
          FROM {tbl}""")
        print(f"  {tbl}: ocr_applied=%s id_number=%s mother=%s dob=%s expiry=%s" % cur.fetchone())
    pg.close()

if __name__=="__main__": main()
