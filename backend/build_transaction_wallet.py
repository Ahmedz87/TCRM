"""Builds transaction_wallet: links OCR'd payment receipts -> deposit transactions.
Idempotent (TRUNCATE + rebuild). RE-RUN as OCR completes (esp. ZainCash) to grow coverage.
Maps: pay_* (ocr_txid = wallet id, ocr_sender_acct = sender wallet, ocr_receiver_acct =
company card -> payment_cards.card_name) -> deposit_documents (by receipt_filename)
-> transactions (by login + amount + closest tx_date).
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
cur.execute("ALTER TABLE transaction_wallet ADD COLUMN IF NOT EXISTS receiver_acct TEXT")
cur.execute("ALTER TABLE transaction_wallet ADD COLUMN IF NOT EXISTS card_name TEXT")
cur.execute("ALTER TABLE transaction_wallet ADD COLUMN IF NOT EXISTS sender_src TEXT")  # 'ocr' | 'inferred'
c.commit()
cur.execute("TRUNCATE transaction_wallet")
# acct normalization: full digits when they form a real number (>=8); keep the raw
# masked/partial string when it still has >=4 digits (Sham prints 3759************ —
# the mask IS the information); pure names (ZainCash office names) -> NULL.
NORM = ("CASE WHEN length(regexp_replace({x},'\\D','','g')) >= 8 "
        "THEN regexp_replace({x},'\\D','','g') "
        "WHEN length(regexp_replace({x},'\\D','','g')) >= 4 THEN trim({x}) "
        "ELSE NULL END")
cur.execute(f"""
INSERT INTO transaction_wallet (transaction_id, wallet_id, sender_acct, sender_block,
                                receiver_acct, method, receipt_filename, source, confidence)
WITH dep_receipts AS (
  SELECT d.client_login AS login, d.amount AS amt, d.tx_date AS dep_date,
         d.payment_method AS method, d.receipt_filename, d.source,
         COALESCE(q.ocr_txid, z.ocr_txid, s.ocr_txid)                     AS wallet_id,
         {NORM.format(x="COALESCE(q.ocr_sender_acct, z.ocr_sender_acct, s.ocr_sender_acct)")} AS sender_acct,
         {NORM.format(x="COALESCE(q.ocr_receiver_acct, z.ocr_receiver_acct, s.ocr_receiver_acct)")} AS receiver_acct,
         -- txid = [8 date][17 fixed][4-5 block][8 seq] -> 37 or 38 digits; block = middle part
         CASE WHEN length(regexp_replace(q.ocr_txid,'\\D','','g')) IN (37,38)
               AND substr(regexp_replace(q.ocr_txid,'\\D','','g'),9,17)='10121420010100166'
              THEN substr(regexp_replace(q.ocr_txid,'\\D','','g'),26,
                          length(regexp_replace(q.ocr_txid,'\\D','','g'))-33) END AS sender_block
  FROM deposit_documents d
  LEFT JOIN pay_qi_card   q ON q.receipt_filename = d.receipt_filename
  LEFT JOIN pay_zaincash  z ON z.receipt_filename = d.receipt_filename
  LEFT JOIN pay_sham_cash s ON s.receipt_filename = d.receipt_filename
  WHERE d.client_login IS NOT NULL
    AND (COALESCE(q.ocr_txid, z.ocr_txid, s.ocr_txid) IS NOT NULL
         OR COALESCE(q.ocr_sender_acct, z.ocr_sender_acct, s.ocr_sender_acct) IS NOT NULL
         OR COALESCE(q.ocr_receiver_acct, z.ocr_receiver_acct, s.ocr_receiver_acct) IS NOT NULL)
),
cand AS (
  SELECT t.id AS txn_id, dr.wallet_id, dr.sender_acct, dr.sender_block, dr.receiver_acct,
         dr.method, dr.receipt_filename, dr.source,
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
SELECT txn_id, wallet_id, sender_acct, sender_block, receiver_acct, method, receipt_filename, source,
       CASE WHEN n = 1 THEN 'confident' ELSE 'ambiguous' END
FROM cand WHERE rn = 1
""")
n = cur.rowcount
c.commit()
# company card name from the receiver account (payment_cards.number OR account_number)
cur.execute("""
UPDATE transaction_wallet tw SET card_name = pc.card_name
FROM payment_cards pc
WHERE tw.receiver_acct IS NOT NULL AND pc.card_name IS NOT NULL AND pc.card_name <> ''
  AND regexp_replace(tw.receiver_acct,'\\D','','g') IN
      (regexp_replace(pc.number,'\\D','','g'),
       regexp_replace(COALESCE(pc.account_number,''),'\\D','','g'))
""")
named = cur.rowcount
c.commit()
cur.execute("UPDATE transaction_wallet SET sender_src='ocr' WHERE sender_acct IS NOT NULL")
c.commit()
# INFER the full sender for name-only receipts: the sender-block (from the txid) is
# deterministic per wallet, so if THIS CLIENT has another Qi deposit where the SAME block
# came with a full 10-digit sender account (and only one such account), reuse it.
cur.execute("""
WITH qi AS (
  SELECT q.client_login,
         regexp_replace(q.ocr_txid,'\\D','','g') AS d,
         regexp_replace(COALESCE(q.ocr_sender_acct,''),'\\D','','g') AS snd
  FROM pay_qi_card q
  WHERE q.client_login IS NOT NULL AND q.ocr_txid IS NOT NULL
),
map AS (
  SELECT client_login, substr(d, 26, length(d)-33) AS blk, MIN(snd) AS snd
  FROM qi
  WHERE length(d) IN (37,38) AND substr(d,9,17)='10121420010100166' AND length(snd)=10
  GROUP BY client_login, substr(d, 26, length(d)-33)
  HAVING count(DISTINCT snd) = 1
)
UPDATE transaction_wallet tw
SET sender_acct = map.snd, sender_src = 'inferred'
FROM transactions t, map
WHERE t.id = tw.transaction_id AND tw.sender_acct IS NULL AND tw.sender_block IS NOT NULL
  AND map.client_login = t.login AND map.blk = tw.sender_block
""")
inferred = cur.rowcount
c.commit()
# GLOBAL inference by (sender_block + sender NAME): blocks alone collide (~15% shared by
# several wallets) but block+name is a safe composite key. Teachers = receipts where the
# full 10-digit sender AND the name are known; students match on both.
import re as _re
def _norm_name(s):
    if not s:
        return ""
    s = str(s).strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"), ("ى", "ي"),
                 ("ة", "ه"), ("ئ", "ي"), ("ؤ", "و")):
        s = s.replace(a, b)
    s = _re.sub(r"[ً-ٰٟ]", "", s)          # diacritics
    s = _re.sub(r"[^0-9a-z؀-ۿ]+", "", s)        # keep letters/digits only
    return s

cur.execute("""
SELECT substr(regexp_replace(ocr_txid,'\\D','','g'),26,length(regexp_replace(ocr_txid,'\\D','','g'))-33),
       ocr_sender_name, regexp_replace(ocr_sender_acct,'\\D','','g')
FROM pay_qi_card
WHERE ocr_txid IS NOT NULL AND ocr_sender_name IS NOT NULL
  AND length(regexp_replace(ocr_txid,'\\D','','g')) IN (37,38)
  AND substr(regexp_replace(ocr_txid,'\\D','','g'),9,17)='10121420010100166'
  AND length(regexp_replace(COALESCE(ocr_sender_acct,''),'\\D','','g'))=10""")
byname = {}
for blk, nm, acct in cur.fetchall():
    k = (blk, _norm_name(nm))
    if k[1]:
        byname.setdefault(k, set()).add(acct)
gmap = {k: next(iter(v)) for k, v in byname.items() if len(v) == 1}
cur.execute("""
SELECT tw.transaction_id, tw.sender_block, q.ocr_sender_name
FROM transaction_wallet tw JOIN pay_qi_card q ON q.receipt_filename = tw.receipt_filename
WHERE tw.sender_acct IS NULL AND tw.sender_block IS NOT NULL AND q.ocr_sender_name IS NOT NULL""")
fills = []
for txn_id, blk, nm in cur.fetchall():
    acct = gmap.get((blk, _norm_name(nm)))
    if acct:
        fills.append((acct, txn_id))
if fills:
    import psycopg2.extras as _ex
    _ex.execute_batch(cur, "UPDATE transaction_wallet SET sender_acct=%s, sender_src='inferred' "
                           "WHERE transaction_id=%s AND sender_acct IS NULL", fills, page_size=1000)
c.commit()
cur.execute("CREATE INDEX IF NOT EXISTS ix_txwallet_sender ON transaction_wallet(sender_acct)")
c.commit()
print(f"sender inferred from same-client same-block history: {inferred:,}")
print(f"sender inferred globally by block+name: {len(fills):,} (map: {len(gmap):,} block+name keys)")
print(f"mapped {n:,} transactions in {time.time()-t0:.1f}s | company-card named: {named:,}")
cur.execute("SELECT confidence, count(*) FROM transaction_wallet GROUP BY confidence ORDER BY 1")
print("by confidence:", cur.fetchall())
cur.execute("SELECT count(*) FILTER (WHERE sender_acct IS NOT NULL), count(*) FILTER (WHERE receiver_acct IS NOT NULL) FROM transaction_wallet")
print("sender/receiver filled:", cur.fetchone())
c.close()
