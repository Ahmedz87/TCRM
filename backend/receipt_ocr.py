#!/usr/bin/env python3
"""
OCR deposit receipts for a per-method table (pay_qi_card / pay_zaincash / pay_sham_cash).
Streams each receipt image from the deposit SFTP (folder 1 then folder 2), extracts payment
fields via deposit_fraud.ocr_deposit_proof (Claude Opus vision), stores them in the table.
Resumable via ocr_status. Usage: receipt_ocr.py <table> <limit> [status_filter]
"""
import psycopg2, paramiko, io, sys, json, re, threading, queue
import deposit_fraud as DF

import db_config
PG = db_config.DSN
HOST, PW = "3.9.217.160", "5aj6r2UhzD"
USERS = ["tnfx_storage_1", "tnfx_storage_2"]
WORKERS = 3

TABLE = sys.argv[1] if len(sys.argv) > 1 else "pay_sham_cash"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 300
STATUS = sys.argv[3] if len(sys.argv) > 3 else None   # e.g. 'completed'

def mime_of(fn):
    e = fn.rsplit(".",1)[-1].lower() if "." in fn else ""
    return {"png":"image/png","webp":"image/webp","gif":"image/gif"}.get(e, "image/jpeg")

def open_users():
    conns = []
    for u in USERS:
        t = paramiko.Transport((HOST,22)); t.banner_timeout=40
        t.connect(username=u, password=PW)
        s = paramiko.SFTPClient.from_transport(t); s.get_channel().settimeout(120)
        conns.append((t,s))
    return conns

def fetch_bytes(conns, fn):
    for _,s in conns:
        try:
            buf = io.BytesIO(); s.getfo("/"+fn, buf); return buf.getvalue()
        except Exception:
            continue
    return None

lock = threading.Lock(); stats={"ok":0,"nofile":0,"err":0}

def worker(q):
    conns = open_users()
    pg = psycopg2.connect(PG); pg.autocommit=True; cur=pg.cursor()
    while True:
        try: rid, fn, sysamt = q.get_nowait()
        except queue.Empty: break
        try:
            b = fetch_bytes(conns, fn)
            if not b:
                cur.execute(f"UPDATE {TABLE} SET ocr_status='no_file' WHERE id=%s",(rid,))
                with lock: stats["nofile"]+=1; q.task_done(); continue
            res = DF.ocr_deposit_proof(b, mime_of(fn))
            if res.get("_unavailable"):
                cur.execute(f"UPDATE {TABLE} SET ocr_status='ocr_unavail' WHERE id=%s",(rid,))
                with lock: stats["err"]+=1; q.task_done(); continue
            amt = None
            try: amt = float(res.get("amount")) if res.get("amount") not in (None,"") else None
            except: amt = None
            am_match = None
            if amt is not None and sysamt is not None:
                try: am_match = abs(float(amt)-float(sysamt))/max(float(sysamt),1) < 0.02
                except: am_match=None
            cur.execute(f"""UPDATE {TABLE} SET ocr_txid=%s, ocr_sender_acct=%s, ocr_receiver_acct=%s,
                          ocr_amount=%s, ocr_datetime=%s, ocr_raw=%s, amount_match=%s, ocr_status='done'
                          WHERE id=%s""",
                        (res.get("txid") or None, res.get("wallet_id") or None, res.get("card") or None,
                         amt, res.get("date") or None, json.dumps(res.get("_raw") or res, ensure_ascii=False),
                         am_match, rid))
            with lock:
                stats["ok"]+=1; n=stats["ok"]+stats["nofile"]+stats["err"]
            if n % 25 == 0: print(f"  {TABLE}: ok={stats['ok']} nofile={stats['nofile']} err={stats['err']}", flush=True)
        except Exception as e:
            with lock: stats["err"]+=1
            try: cur.execute(f"UPDATE {TABLE} SET ocr_status='error' WHERE id=%s",(rid,))
            except: pass
        finally:
            q.task_done()
    for t,_ in conns:
        try: t.close()
        except: pass
    pg.close()

def main():
    pg = psycopg2.connect(PG); cur=pg.cursor()
    extra = " AND status=%s" if STATUS else ""
    params = [LIMIT]
    sql = f"""SELECT id, receipt_filename, sys_amount FROM {TABLE}
              WHERE ocr_status='pending' AND receipt_filename IS NOT NULL {('AND status=%s' if STATUS else '')}
              ORDER BY (status='completed') DESC, tx_date DESC LIMIT %s"""
    if STATUS: cur.execute(sql, (STATUS, LIMIT))
    else: cur.execute(sql, (LIMIT,))
    work = cur.fetchall(); pg.close()
    print(f"{TABLE}: OCR queue {len(work):,}", flush=True)
    if not work: return
    q=queue.Queue()
    for w in work: q.put(w)
    ths=[threading.Thread(target=worker,args=(q,)) for _ in range(WORKERS)]
    for th in ths: th.start()
    for th in ths: th.join()
    print(f"{TABLE}: DONE {stats}", flush=True)

if __name__=="__main__": main()
