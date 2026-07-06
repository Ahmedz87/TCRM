"""Builds transaction_wallet: links OCR'd payment receipts -> deposit transactions.
Idempotent (TRUNCATE + rebuild). RE-RUN as OCR completes (esp. ZainCash) to grow coverage.
Maps: pay_* (ocr_txid = wallet id, ocr_sender_acct = shared card) -> deposit_documents
(by receipt_filename) -> transactions (by login + amount + closest tx_date).
confidence = 'confident' (one candidate txn) | 'ambiguous' (several same-amount deposits).
Usage: python build_transaction_wallet.py
"""
import db_config, time
c = db_config.connect(); c.autocommit = False; cur = c.cursor()
t0 = time.time()
cur.execute("""
CREATE TABLE IF NOT EXISTS transaction_wallet (
  transaction_id   BIGINT PRIMARY KEY,
  wallet_id        TEXT,      -- ocr_txid (payment reference)
  sender_acct      TEXT,      -- ocr_sender_acct (full sender card/wallet, accurate but sparse)
  sender_block     TEXT,      -- Qi sender-block (4 digits from the txid) — a sender id for EVERY clean Qi receipt
  method           TEXT,
  receipt_filename TEXT,
  source           TEXT,
  confidence       TEXT,      -- confident | ambiguous
  matched_at       TIMESTAMP DEFAULT NOW()
)""")
cur.execute("ALTER TABLE transaction_wallet ADD COLUMN IF NOT EXISTS sender_block TEXT")
c.commit()
cur.execute("TRUNCATE transaction_wallet")
cur.execute("""
INSERT INTO transaction_wallet (transaction_id, wallet_id, sender_acct, sender_block, method, receipt_filename, source, confidence)
WITH dep_receipts AS (
  SELECT d.client_login AS login, d.amount AS amt, d.tx_date AS dep_date,
         d.payment_method AS method, d.receipt_filename, d.source,
         COALESCE(q.ocr_txid, z.ocr_txid, s.ocr_txid)                     AS wallet_id,
         COALESCE(q.ocr_sender_acct, z.ocr_sender_acct, s.ocr_sender_acct) AS sender_acct,
         CASE WHEN length(regexp_replace(q.ocr_txid,'\\D','','g'))=37
               AND substr(regexp_replace(q.ocr_txid,'\\D','','g'),9,17)='10121420010100166'
              THEN substr(regexp_replace(q.ocr_txid,'\\D','','g'),26,4) END AS sender_block
  FROM deposit_documents d
  LEFT JOIN pay_qi_card   q ON q.receipt_filename = d.receipt_filename
  LEFT JOIN pay_zaincash  z ON z.receipt_filename = d.receipt_filename
  LEFT JOIN pay_sham_cash s ON s.receipt_filename = d.receipt_filename
  WHERE d.client_login IS NOT NULL
    AND COALESCE(q.ocr_txid, z.ocr_txid, s.ocr_txid) IS NOT NULL
),
cand AS (
  SELECT t.id AS txn_id, dr.wallet_id, dr.sender_acct, dr.sender_block, dr.method, dr.receipt_filename, dr.source,
         row_number() OVER (PARTITION BY t.id
             ORDER BY abs(extract(epoch FROM (t.tx_date::timestamp - dr.dep_date::timestamp)))) AS rn,
         count(*)     OVER (PARTITION BY t.id) AS n
  FROM transactions t
  JOIN dep_receipts dr
    ON dr.login = t.login
   AND abs(t.amount - dr.amt) < 0.01
   AND t.tx_type = 'deposit'
   AND abs(extract(epoch FROM (t.tx_date::timestamp - dr.dep_date::timestamp))) < 172800
)
SELECT txn_id, wallet_id, sender_acct, sender_block, method, receipt_filename, source,
       CASE WHEN n = 1 THEN 'confident' ELSE 'ambiguous' END
FROM cand WHERE rn = 1
""")
n = cur.rowcount
c.commit()
cur.execute("CREATE INDEX IF NOT EXISTS ix_txwallet_sender ON transaction_wallet(sender_acct)")
c.commit()
print(f"mapped {n:,} transactions in {time.time()-t0:.1f}s")
cur.execute("SELECT confidence, count(*) FROM transaction_wallet GROUP BY confidence ORDER BY 1")
print("by confidence:", cur.fetchall())
c.close()
