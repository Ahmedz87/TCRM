#!/usr/bin/env python3
"""
Build ts_kyc_documents: every TradeSoft KYC file (from fx_users_view.files_name_backup JSON)
typed by slot (id_front/id_back/address_front/address_back/profile) and linked to our client/lead.
"""
import pymysql, psycopg2, psycopg2.extras, json, re

import ts_mysql_config
MY = dict(ts_mysql_config.MYSQL_SRC)
import db_config
PG = db_config.DSN

def doc_type(key):
    k = key.lower()
    if "id" in k and "front" in k: return "id_front"
    if "id" in k and "back" in k:  return "id_back"
    if "address" in k and "front" in k: return "address_front"
    if "address" in k and "back" in k:  return "address_back"
    if "front" in k or "profile" in k or k=="_front": return "profile"
    if "back" in k: return "id_back"
    return key.strip("_")[:30] or "other"

def basename(p):
    if not p: return None
    return p.replace("\\/","/").replace("\\","/").rstrip("/").split("/")[-1]

def parse_files(raw):
    """yields (slot_key, filename, orig_path)"""
    if not raw or raw.strip() in ("","[]","null"): return
    txt = raw.replace("\\/","/")
    try:
        data = json.loads(txt)
    except Exception:
        # fallback: regex extract "key":"path"
        for k,v in re.findall(r'"([^"]+)"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|pdf|jfif|webp|heic))"', txt, re.I):
            yield k, basename(v), v
        return
    items = data if isinstance(data, list) else [data]
    for obj in items:
        if not isinstance(obj, dict): continue
        for k,v in obj.items():
            if isinstance(v,str) and "." in v:
                yield k, basename(v), v

def main():
    pg = psycopg2.connect(PG); pg.autocommit=False; cur=pg.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS ts_kyc_documents (
        id BIGSERIAL PRIMARY KEY,
        legacy_user_id BIGINT, customer_no TEXT, client_id BIGINT, client_login BIGINT,
        lead_id BIGINT, is_lead BOOLEAN DEFAULT FALSE, person_name TEXT, is_kyc_verified INT,
        slot_key TEXT, doc_type TEXT, filename TEXT, orig_path TEXT,
        local_path TEXT, file_present BOOLEAN DEFAULT FALSE, mtime_year INT,
        ocr_json JSONB, ocr_status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT now(),
        UNIQUE (legacy_user_id, filename)
      )""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tskycdoc_fn ON ts_kyc_documents(filename)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tskycdoc_login ON ts_kyc_documents(client_login)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tskycdoc_type ON ts_kyc_documents(doc_type)")
    pg.commit()

    my = pymysql.connect(**MY); mc = my.cursor(pymysql.cursors.SSDictCursor)
    mc.execute("""SELECT id, name, is_kyc_verified, files_name_backup FROM fx_users_view
                  WHERE files_name_backup IS NOT NULL AND files_name_backup<>'' AND files_name_backup<>'[]'""")
    ins = """INSERT INTO ts_kyc_documents
      (legacy_user_id, person_name, is_kyc_verified, slot_key, doc_type, filename, orig_path)
      VALUES %s ON CONFLICT (legacy_user_id, filename) DO NOTHING"""
    batch=[]; users=0; files=0
    for r in mc:
        users+=1
        for slot,fn,path in parse_files(r["files_name_backup"]):
            if not fn: continue
            files+=1
            batch.append((r["id"], (r["name"] or "")[:120], r["is_kyc_verified"], slot, doc_type(slot), fn, path[:255]))
        if len(batch)>=5000:
            psycopg2.extras.execute_values(cur, ins, batch); pg.commit(); batch=[]
            if users % 40000 < 500: print(f"  {users:,} users, {files:,} kyc files ...", flush=True)
    if batch: psycopg2.extras.execute_values(cur, ins, batch); pg.commit()
    my.close()

    print("Linking KYC docs to clients/leads ...", flush=True)
    cur.execute("""UPDATE ts_kyc_documents d SET customer_no=c.customer_no
                   FROM customers c WHERE c.legacy_user_id=d.legacy_user_id::text AND d.customer_no IS NULL""")
    pg.commit()
    cur.execute("""UPDATE ts_kyc_documents d SET client_id=cl.id, client_login=cl.login
                   FROM clients cl WHERE cl.customer_no=d.customer_no AND d.client_id IS NULL""")
    pg.commit()
    # leads link (if leads has customer_no)
    try:
        cur.execute("""UPDATE ts_kyc_documents d SET lead_id=l.id, is_lead=TRUE
                       FROM leads l WHERE l.customer_no=d.customer_no AND d.client_id IS NULL AND d.lead_id IS NULL""")
        pg.commit()
    except Exception as e:
        pg.rollback(); print("  (leads link skipped:", e, ")")

    cur.execute("SELECT count(*), count(client_id), count(lead_id) FROM ts_kyc_documents")
    tot,cl,ld = cur.fetchone()
    print(f"\nts_kyc_documents: {tot:,} files | {cl:,} linked to client | {ld:,} linked to lead")
    cur.execute("SELECT doc_type, count(*) FROM ts_kyc_documents GROUP BY doc_type ORDER BY count(*) DESC")
    print("  by doc_type:")
    for t,n in cur.fetchall(): print(f"    {t:16} {n:>8,}")
    pg.close()

if __name__=="__main__": main()
