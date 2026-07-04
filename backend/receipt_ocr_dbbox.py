#!/usr/bin/env python3
"""
Receipt OCR that reads the downloaded receipt from the DB box (stable key SSH) instead of the
fragile source SFTP. Only processes receipts already present locally (join to receipt_phash).
Usage: receipt_ocr_dbbox.py <table> <limit>
"""
import psycopg2, paramiko, io, sys, os, json, threading, queue
import deposit_fraud as DF

import db_config
PG = db_config.DSN
DBBOX = "199.247.6.189"; KEY = r"C:\Users\Administrator\.ssh\id_ed25519"
BASE = "/var/lib/broker_docs/deposits"
TABLE = sys.argv[1] if len(sys.argv) > 1 else "pay_sham_cash"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 500
MODEL = sys.argv[3] if len(sys.argv) > 3 else "claude-opus-4-8"
WORKERS = int(sys.argv[4]) if len(sys.argv) > 4 else 3

def mime_of(fn):
    e = fn.rsplit(".",1)[-1].lower() if "." in fn else ""
    return {"png":"image/png","webp":"image/webp","gif":"image/gif"}.get(e, "image/jpeg")

def sftp():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(DBBOX, username="root", key_filename=KEY, timeout=20)
    s = c.open_sftp(); s.get_channel().settimeout(120)
    return c, s

lock=threading.Lock(); stats={"ok":0,"nofile":0,"err":0}

def worker(q):
    c,s = sftp(); pg=psycopg2.connect(PG); pg.autocommit=True; cur=pg.cursor()
    while True:
        try: rid, fn, sysamt, folder = q.get_nowait()
        except queue.Empty: break
        try:
            path = f"{BASE}/{folder}/{fn}"
            buf=io.BytesIO()
            try: s.getfo(path, buf)
            except Exception:
                # try the other folder
                alt = "f2" if folder=="f1" else "f1"
                try: s.getfo(f"{BASE}/{alt}/{fn}", buf)
                except Exception:
                    cur.execute(f"UPDATE {TABLE} SET ocr_status='no_file' WHERE id=%s",(rid,))
                    with lock: stats["nofile"]+=1
                    continue
            res = DF.ocr_deposit_proof(buf.getvalue(), mime_of(fn), model=MODEL)
            if res.get("_unavailable"):
                with lock: stats["err"]+=1
                continue
            amt=None
            try: amt=float(res.get("amount")) if res.get("amount") not in (None,"") else None
            except: amt=None
            am=None
            if amt is not None and sysamt is not None:
                try: am = abs(float(amt)-float(sysamt))/max(float(sysamt),1) < 0.02
                except: am=None
            cur.execute(f"""UPDATE {TABLE} SET ocr_txid=%s, ocr_sender_acct=%s, ocr_receiver_acct=%s,
                        ocr_amount=%s, ocr_datetime=%s, ocr_raw=%s, amount_match=%s,
                        file_present=TRUE, folder=%s, ocr_status='done' WHERE id=%s""",
                (res.get("txid") or None, res.get("wallet_id") or None, res.get("card") or None,
                 amt, res.get("date") or None, json.dumps(res.get("_raw") or res, ensure_ascii=False), am, folder, rid))
            with lock:
                stats["ok"]+=1; n=sum(stats.values())
            if n % 25==0: print(f"  {TABLE}: {stats}", flush=True)
        except Exception:
            with lock: stats["err"]+=1
            try: c.close(); c,s=sftp()
            except: pass
        finally:
            q.task_done()
    try: c.close()
    except: pass
    pg.close()

def main():
    pg=psycopg2.connect(PG); cur=pg.cursor()
    cur.execute(f"""SELECT t.id, t.receipt_filename, t.sys_amount, p.folder
                    FROM {TABLE} t JOIN receipt_phash p ON p.filename=t.receipt_filename
                    WHERE t.ocr_status='pending'
                    ORDER BY (t.status='completed') DESC LIMIT %s""",(LIMIT,))
    work=cur.fetchall(); pg.close()
    print(f"{TABLE}: OCR queue (present locally) {len(work):,}", flush=True)
    if not work: return
    q=queue.Queue()
    for w in work: q.put(w)
    ths=[threading.Thread(target=worker,args=(q,)) for _ in range(WORKERS)]
    for th in ths: th.start()
    for th in ths: th.join()
    print(f"{TABLE}: DONE {stats}", flush=True)

if __name__=="__main__": main()
