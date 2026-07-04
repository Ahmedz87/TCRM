#!/usr/bin/env python3
"""
OCR linked TradeSoft KYC ID docs (id_front/id_back) -> structured registration fields.
Streams each image from the tnfx_kyc SFTP by filename (no local copy needed), extracts with
kyc_ai (Claude Opus vision), stores ts_kyc_documents.ocr_json, and fills clients.* reg fields
(DOB, id_number, mother_name, issue/expiry, place_of_birth) ONLY where currently NULL.
Resumable via ocr_status. Non-destructive.
"""
import psycopg2, psycopg2.extras, paramiko, base64, io, re, threading, queue, sys, json, datetime
import kyc_ai

import db_config
PG = db_config.DSN
SFTP_HOST, SFTP_USER, SFTP_PW = "3.9.217.160", "tnfx_kyc", "5aj6r2UhzD"
WORKERS = 3
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 100000

def sftp_conn():
    t = paramiko.Transport((SFTP_HOST, 22)); t.banner_timeout=40
    t.connect(username=SFTP_USER, password=SFTP_PW)
    s = paramiko.SFTPClient.from_transport(t); s.get_channel().settimeout(120)
    return t, s

def parse_date(v):
    if not v or not isinstance(v, str): return None
    v = v.strip()
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%m/%d/%Y","%d.%m.%Y","%Y/%m/%d"):
        try: return datetime.datetime.strptime(v, fmt).date()
        except: pass
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", v)
    if m:
        try: return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except: return None
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", v)
    if m:
        try: return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except: return None
    return None

lock = threading.Lock()
stats = {"ok":0,"err":0,"nofile":0}

def worker(q):
    t, s = sftp_conn()
    pg = psycopg2.connect(PG); pg.autocommit=True; cur = pg.cursor()
    while True:
        try: row = q.get_nowait()
        except queue.Empty: break
        docid, fn, dtype = row
        try:
            buf = io.BytesIO()
            try:
                s.getfo("/"+fn, buf)
            except Exception:
                with lock: stats["nofile"]+=1
                cur.execute("UPDATE ts_kyc_documents SET ocr_status='no_file' WHERE id=%s",(docid,))
                continue
            b64 = base64.standard_b64encode(buf.getvalue()).decode()
            dt = "national_id_back" if dtype=="id_back" else "national_id"
            res = kyc_ai.extract_id_fields_from_b64(b64, doc_type=dt)
            st = res.get("_status")
            cur.execute("UPDATE ts_kyc_documents SET ocr_json=%s, ocr_status=%s WHERE id=%s",
                        (json.dumps(res, ensure_ascii=False), ("done" if not st else st), docid))
            with lock:
                if st: stats["err"]+=1
                else: stats["ok"]+=1
                n = stats["ok"]+stats["err"]+stats["nofile"]
            if n % 50 == 0: print(f"  ocr progress: ok={stats['ok']} err={stats['err']} nofile={stats['nofile']}", flush=True)
        except Exception as e:
            with lock: stats["err"]+=1
            try:
                cur.execute("UPDATE ts_kyc_documents SET ocr_status='error' WHERE id=%s",(docid,))
            except: pass
            try: t.close(); t,s = sftp_conn()
            except: pass
        finally:
            q.task_done()
    try: t.close()
    except: pass
    pg.close()

def apply_to_clients():
    """Merge each linked person's id_front+id_back OCR -> clients reg fields (fill NULLs only)."""
    pg = psycopg2.connect(PG); pg.autocommit=False; cur=pg.cursor()
    cur.execute("""SELECT client_id,
              jsonb_agg(ocr_json) FILTER (WHERE ocr_json IS NOT NULL) AS docs
              FROM ts_kyc_documents
              WHERE client_id IS NOT NULL AND ocr_status='done' AND doc_type IN ('id_front','id_back')
              GROUP BY client_id""")
    rows = cur.fetchall()
    upd=0
    for cid, docs in rows:
        merged={}
        for d in docs or []:
            for k,v in (d or {}).items():
                if k.startswith("_"): continue
                if v and not merged.get(k): merged[k]=v
        dob = parse_date(merged.get("date_of_birth"))
        iss = parse_date(merged.get("issue_date"))
        exp = parse_date(merged.get("expiry_date"))
        idn = (merged.get("id_number") or "").strip() or None
        mom = (merged.get("mother_name") or "").strip() or None
        pob = (merged.get("place_of_birth") or "").strip() or None
        cur.execute("""UPDATE clients SET
              date_of_birth = COALESCE(date_of_birth, %s),
              id_number     = COALESCE(id_number, %s),
              mother_name   = COALESCE(mother_name, %s),
              id_issue_date = COALESCE(id_issue_date, %s),
              id_expiry_date= COALESCE(id_expiry_date, %s),
              place_of_birth= COALESCE(place_of_birth, %s),
              id_type       = COALESCE(id_type, 'national_id'),
              kyc_ocr_source= 'tradesoft_kyc_ocr', kyc_ocr_at = now()
            WHERE id=%s""", (dob.isoformat() if dob else None, idn, mom, iss, exp, pob, cid))
        upd += cur.rowcount
    pg.commit()
    print(f"applied OCR to {len(rows):,} clients (rows touched {upd:,})")
    pg.close()

def main():
    pg = psycopg2.connect(PG); cur=pg.cursor()
    cur.execute("""SELECT id, filename, doc_type FROM ts_kyc_documents
                   WHERE doc_type IN ('id_front','id_back')
                     AND (client_id IS NOT NULL OR lead_id IS NOT NULL)
                     AND ocr_status='pending'
                   LIMIT %s""", (LIMIT,))
    work = cur.fetchall(); pg.close()
    print(f"OCR queue: {len(work):,} id docs (linked, pending)", flush=True)
    if not work:
        apply_to_clients(); return
    q = queue.Queue()
    for w in work: q.put(w)
    ths=[threading.Thread(target=worker, args=(q,)) for _ in range(WORKERS)]
    for th in ths: th.start()
    for th in ths: th.join()
    print(f"OCR done: {stats}", flush=True)
    apply_to_clients()

if __name__=="__main__": main()
