#!/usr/bin/env python3
"""
Build deposit_documents: every TradeSoft deposit receipt photo -> linked to our client.
Source: live MySQL gzvxcfqecm.fx_transactions_view (freshest).
Target: broker_crm (remote 199.247.6.189) public.deposit_documents.
Idempotent: ON CONFLICT (ts_txn_id, receipt_slot).
"""
import pymysql, psycopg2, psycopg2.extras, re, os

import ts_mysql_config
MY = dict(ts_mysql_config.MYSQL_SRC)
import db_config
PG = db_config.DSN

RECEIPT_COLS = ["receipt","receipt_2","receipt_2_1","receipt_2_2","receipt_2_3","receipt_2_4"]

def norm_method(m):
    if not m: return "Unknown"
    s = re.sub(r"[^a-z0-9]+"," ", m.lower()).strip()
    if "zain" in s: return "ZainCash"
    if s.startswith("qi") or "qi card" in s or s=="qicard": return "Qi Card"
    if "sham" in s: return "Sham Cash"
    if "zaincash" in s: return "ZainCash"
    if "tether" in s or "usdt" in s: return "USDT"
    if "perfect" in s: return "Perfect Money"
    if "visa" in s or "master" in s or "credit" in s or "debit" in s or "card payment" in s: return "Card"
    if "wallet cash" in s: return "Wallet Cash"
    if "taif" in s: return "Al Taif"
    if "asiahawala" in s: return "Asiahawala"
    if "asiapay" in s: return "Asiapay"
    if "fib" == s: return "FIB"
    if "fastpay" in s: return "FastPay"
    if "ptop" in s: return "Ptop"
    if "paymaxis" in s: return "Paymaxis"
    if "cryptomus" in s: return "Cryptomus"
    if "advcash" in s: return "AdvCash"
    if "payeer" in s: return "Payeer"
    if "airtm" in s: return "Airtm"
    return m.strip()[:60]

def basename_from(url):
    if not url: return None
    u = url.strip()
    if u in ("NULL","null",""): return None
    return u.rstrip("/").split("/")[-1]

def main():
    pg = psycopg2.connect(PG); pg.autocommit = False
    cur = pg.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS deposit_documents (
        id BIGSERIAL PRIMARY KEY,
        ts_txn_id BIGINT, legacy_user_id BIGINT, account_number BIGINT,
        customer_no TEXT, client_id BIGINT, client_login BIGINT, is_lead BOOLEAN DEFAULT FALSE,
        amount NUMERIC, currency TEXT,
        payment_method_raw TEXT, payment_method TEXT, status TEXT, tx_date TIMESTAMP,
        receipt_slot TEXT, receipt_filename TEXT, receipt_url TEXT,
        folder TEXT, local_path TEXT, file_present BOOLEAN DEFAULT FALSE,
        phash TEXT, ocr_json JSONB, ocr_status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT now(),
        UNIQUE (ts_txn_id, receipt_slot)
      )""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_depdoc_method ON deposit_documents(payment_method)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_depdoc_login ON deposit_documents(client_login)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_depdoc_fn ON deposit_documents(receipt_filename)")
    pg.commit()

    my = pymysql.connect(**MY); mc = my.cursor(pymysql.cursors.SSDictCursor)
    cols = ",".join(RECEIPT_COLS)
    # --recent N : only pull deposits created in the last N days (cheap, for the frequent near-real-time
    # pull). No flag = full idempotent rebuild (the nightly safety net). ON CONFLICT makes both safe.
    import sys as _sys
    _recent = ""
    if "--recent" in _sys.argv:
        try:
            _d = int(_sys.argv[_sys.argv.index("--recent") + 1])
        except Exception:
            _d = 2
        _recent = f" AND created_at >= (NOW() - INTERVAL {_d} DAY)"
    mc.execute(f"""SELECT id, user_id, account_number, amount, currency, payment_method, status, created_at, {cols}
                   FROM fx_transactions_view WHERE type='deposit'{_recent}""")
    batch=[]; total=0; rows_with_doc=0
    ins = """INSERT INTO deposit_documents
      (ts_txn_id, legacy_user_id, account_number, amount, currency, payment_method_raw, payment_method, status, tx_date, receipt_slot, receipt_filename, receipt_url)
      VALUES %s ON CONFLICT (ts_txn_id, receipt_slot) DO NOTHING"""
    for r in mc:
        total+=1
        any_doc=False
        for slot in RECEIPT_COLS:
            fn = basename_from(r[slot])
            if not fn: continue
            any_doc=True
            batch.append((r["id"], r["user_id"], r["account_number"], r["amount"], r["currency"],
                          r["payment_method"], norm_method(r["payment_method"]), r["status"], r["created_at"],
                          slot, fn, (r[slot] or "").strip()))
        if any_doc: rows_with_doc+=1
        if len(batch)>=5000:
            psycopg2.extras.execute_values(cur, ins, batch); pg.commit(); batch=[]
            if total % 50000 < 5000: print(f"  processed {total:,} deposits, {rows_with_doc:,} with docs ...", flush=True)
    if batch: psycopg2.extras.execute_values(cur, ins, batch); pg.commit()
    my.close()

    print("Resolving client links (account_number -> clients.login; user_id -> customers.customer_no) ...", flush=True)
    # link customer_no from customers via legacy_user_id
    cur.execute("""UPDATE deposit_documents d SET customer_no=c.customer_no
                   FROM customers c WHERE c.legacy_user_id = d.legacy_user_id::text AND d.customer_no IS NULL""")
    pg.commit()
    # link client_login/client_id by MT login (account_number)
    cur.execute("""UPDATE deposit_documents d SET client_login=cl.login, client_id=cl.id
                   FROM clients cl WHERE cl.login = d.account_number AND d.client_login IS NULL""")
    pg.commit()
    # fallback: by customer_no (pick one login)
    cur.execute("""UPDATE deposit_documents d SET client_login=cl.login, client_id=cl.id
                   FROM clients cl WHERE cl.customer_no = d.customer_no AND d.client_login IS NULL""")
    pg.commit()

    cur.execute("SELECT count(*), count(client_login), count(DISTINCT receipt_filename) FROM deposit_documents")
    tot, linked, uniqfn = cur.fetchone()
    print(f"\ndeposit_documents: {tot:,} receipt rows | {linked:,} linked to a client | {uniqfn:,} unique files")
    cur.execute("""SELECT payment_method, count(*), count(client_login) FROM deposit_documents
                   GROUP BY payment_method ORDER BY count(*) DESC LIMIT 12""")
    print("  by method (rows / linked):")
    for m,n,l in cur.fetchall(): print(f"    {m:16} {n:>8,} / {l:,}")
    pg.close()

if __name__=="__main__": main()
