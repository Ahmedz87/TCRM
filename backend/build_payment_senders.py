"""Builds client_payment_senders: which real payment SENDER each client used, so the connection
engine can link clients who share a sender (same Qi card / same wallet) rather than merely the same
payment METHOD. Uses ACCURATE full sender identifiers only (no collision-prone 4-digit blocks):
  qi    -> full 10-digit ocr_sender_acct (non-masked)          [accurate; needs sender OCR]
  zain  -> sender phone/wallet (ocr_sender_acct)               [sparse until ZainCash OCR]
  sham  -> masked -> UNUSABLE for linking (skipped)
`fanout` = how many DISTINCT clients used that sender. A high fanout = a money exchanger/agent
(one card funding many unrelated clients), NOT a family — the engine treats those separately.
Idempotent. Re-run after OCR/sender-extraction batches. python build_payment_senders.py
"""
import re
import db_config
from collections import defaultdict


def main():
    c = db_config.connect(); c.autocommit = False; cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS client_payment_senders(
        client_login BIGINT, method TEXT, sender_key TEXT,
        n_deposits INT, fanout INT,
        PRIMARY KEY(client_login, method, sender_key))""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_cps_key ON client_payment_senders(method, sender_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_cps_login ON client_payment_senders(client_login)")
    c.commit()

    # (login, method, sender_key) -> n
    pair = defaultdict(int)
    sender_clients = defaultdict(set)   # (method,key) -> set(login)

    # --- Qi (full 10-digit sender account, non-masked) ---
    cur.execute("""SELECT d.client_login, regexp_replace(q.ocr_sender_acct,'\\D','','g') AS snd
        FROM deposit_documents d JOIN pay_qi_card q ON q.receipt_filename=d.receipt_filename
        WHERE d.client_login IS NOT NULL AND q.ocr_sender_acct IS NOT NULL
          AND q.ocr_sender_acct NOT LIKE '%*%' AND q.ocr_sender_acct NOT LIKE '%X%'""")
    for login, snd in cur.fetchall():
        if snd and 8 <= len(snd) <= 12:
            pair[(login, "qi", snd)] += 1
            sender_clients[("qi", snd)].add(login)

    # --- ZainCash (sender wallet/phone) ---
    cur.execute("""SELECT d.client_login, regexp_replace(z.ocr_sender_acct,'\\D','','g') AS snd
        FROM deposit_documents d JOIN pay_zaincash z ON z.receipt_filename=d.receipt_filename
        WHERE d.client_login IS NOT NULL AND z.ocr_sender_acct IS NOT NULL
          AND z.ocr_sender_acct NOT LIKE '%*%'""")
    for login, snd in cur.fetchall():
        if snd and 5 <= len(snd) <= 13:
            pair[(login, "zain", snd)] += 1
            sender_clients[("zain", snd)].add(login)

    fanout = {k: len(v) for k, v in sender_clients.items()}
    cur.execute("TRUNCATE client_payment_senders")
    import psycopg2.extras as ex
    rows = [(login, m, k, n, fanout[(m, k)]) for (login, m, k), n in pair.items()]
    ex.execute_batch(cur, """INSERT INTO client_payment_senders
        (client_login, method, sender_key, n_deposits, fanout) VALUES (%s,%s,%s,%s,%s)""",
        rows, page_size=1000)
    c.commit()
    cur.execute("SELECT method, count(*), count(DISTINCT client_login), count(DISTINCT sender_key) "
                "FROM client_payment_senders GROUP BY method")
    for m, r, cl, s in cur.fetchall():
        print(f"{m}: {r:,} rows | {cl:,} clients | {s:,} senders")
    cur.execute("SELECT count(*) FROM (SELECT method,sender_key FROM client_payment_senders "
                "GROUP BY 1,2 HAVING count(DISTINCT client_login) BETWEEN 2 AND 6) t")
    print(f"family-candidate senders (shared by 2-6 clients): {cur.fetchone()[0]:,}")
    cur.execute("SELECT count(*) FROM (SELECT method,sender_key FROM client_payment_senders "
                "GROUP BY 1,2 HAVING count(DISTINCT client_login) > 6) t")
    print(f"exchanger senders (shared by >6 clients, excluded from family links): {cur.fetchone()[0]:,}")
    c.close()


if __name__ == "__main__":
    main()
