#!/usr/bin/env python3
"""
Create per-method deposit tables (Qi Card / ZainCash / Sham Cash) and populate the STRUCTURED
side from deposit_documents. OCR-extracted receipt fields + fraud verdicts are filled by
receipt_ocr.py / the fraud studies. Idempotent.
"""
import psycopg2
import db_config
PG = db_config.DSN

METHODS = [("pay_qi_card","Qi Card"), ("pay_zaincash","ZainCash"), ("pay_sham_cash","Sham Cash")]

DDL = """CREATE TABLE IF NOT EXISTS {t} (
  id BIGSERIAL PRIMARY KEY,
  deposit_document_id BIGINT UNIQUE, ts_txn_id BIGINT,
  client_login BIGINT, client_id BIGINT, customer_no TEXT, person_name TEXT,
  sys_amount NUMERIC, currency TEXT, status TEXT, tx_date TIMESTAMP,
  receipt_filename TEXT, receipt_url TEXT, folder TEXT, local_path TEXT, file_present BOOLEAN DEFAULT FALSE,
  -- OCR-extracted from the receipt image:
  ocr_txid TEXT, ocr_sender_name TEXT, ocr_sender_acct TEXT,
  ocr_receiver_name TEXT, ocr_receiver_acct TEXT, ocr_amount NUMERIC, ocr_datetime TEXT,
  ocr_raw JSONB, ocr_status TEXT DEFAULT 'pending',
  -- fraud analysis:
  phash TEXT, dup_group INT, amount_match BOOLEAN,
  fraud_verdict TEXT, fraud_reasons TEXT,
  created_at TIMESTAMP DEFAULT now())"""

def main():
    pg = psycopg2.connect(PG); pg.autocommit=False; cur=pg.cursor()
    for t, method in METHODS:
        cur.execute(DDL.format(t=t))
        cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_login ON {t}(client_login)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_txid ON {t}(ocr_txid)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_phash ON {t}(phash)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_ocrstatus ON {t}(ocr_status)")
        pg.commit()
        cur.execute(f"""INSERT INTO {t}
          (deposit_document_id, ts_txn_id, client_login, client_id, customer_no, person_name,
           sys_amount, currency, status, tx_date, receipt_filename, receipt_url, folder, local_path, file_present)
          SELECT d.id, d.ts_txn_id, d.client_login, d.client_id, d.customer_no, cl.name,
                 d.amount, d.currency, d.status, d.tx_date, d.receipt_filename, d.receipt_url,
                 d.folder, d.local_path, d.file_present
          FROM deposit_documents d
          LEFT JOIN clients cl ON cl.id = d.client_id
          WHERE d.payment_method = %s
          ON CONFLICT (deposit_document_id) DO NOTHING""", (method,))
        pg.commit()
        cur.execute(f"SELECT count(*), count(client_login), count(*) FILTER (WHERE status='completed') FROM {t}")
        n, linked, comp = cur.fetchone()
        print(f"{t:16}: {n:>8,} rows | {linked:,} linked | {comp:,} completed")
    pg.close()

if __name__=="__main__": main()
