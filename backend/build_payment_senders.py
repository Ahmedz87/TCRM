"""Builds client_payment_senders: which real payment SENDER each client used, so the connection
engine can link clients who share a sender rather than merely the same payment METHOD.

Qi (Q-Card): linked by the SENDER NAME on the receipt (OCR), NOT by the Qi card/account number.
  Desk rule (Jul 2026): a shared Qi CARD NUMBER is NOT a family link — the same physical card is used
  by exchangers and rotates, so the card number links unrelated people. The stable identity of who
  actually funded the account is the sender's NAME on the transfer, which we now extract by OCR. So a
  Qi family/related link fires only when two DIFFERENT customers were funded by the SAME sender name.
  Name sources: transaction_wallet.card_name (+ pay_qi_card.ocr_sender_name when populated).
ZainCash: sender wallet/phone (ocr_sender_acct) — unchanged (its names are sparse).
Sham: masked -> UNUSABLE for linking (skipped).

`fanout` = how many DISTINCT clients used that sender. A high fanout = a money exchanger/agent (one
sender funding many unrelated clients), NOT a family — the engine excludes those (PAY_SENDER_MAX_FANOUT).
Idempotent. Re-run after OCR/sender-extraction batches. python build_payment_senders.py
"""
import re
import db_config
from collections import defaultdict


def norm_sender_name(s):
    """Normalise a transliterated Qi sender name for cross-receipt matching: lowercase, latin letters
    only, drop 1-char tokens, sort the tokens (so 'Walid Ibrahim' == 'Ibrahim Walid'). Returns '' when
    there aren't at least two real tokens (a single first name is too common to link on)."""
    toks = [t for t in re.sub(r"[^a-z ]", " ", (s or "").lower()).split() if len(t) >= 2]
    if len(toks) < 2:
        return ""
    key = " ".join(sorted(toks))
    return key if len(key) >= 5 else ""


def main():
    c = db_config.connect(); c.autocommit = False; cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS client_payment_senders(
        client_login BIGINT, method TEXT, sender_key TEXT,
        n_deposits INT, fanout INT,
        PRIMARY KEY(client_login, method, sender_key))""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_cps_key ON client_payment_senders(method, sender_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_cps_login ON client_payment_senders(client_login)")
    c.commit()

    pair = defaultdict(int)             # (login, method, sender_key) -> n
    sender_clients = defaultdict(set)   # (method, key) -> set(login)

    # --- Qi: by SENDER NAME (NOT the card number) ---
    # (A) transaction_wallet.card_name — the OCR'd name on the paying Qi card, joined to the client
    #     through the transaction it belongs to.
    cur.execute("""
        SELECT t.login, tw.card_name
        FROM transaction_wallet tw
        JOIN transactions t ON t.id = tw.transaction_id
        WHERE tw.method ILIKE '%qi%' AND COALESCE(tw.card_name,'') <> '' AND t.login IS NOT NULL
    """)
    qi_named = 0
    for login, nm in cur.fetchall():
        key = norm_sender_name(nm)
        if key:
            pair[(login, "qi", key)] += 1
            sender_clients[("qi", key)].add(login); qi_named += 1
    # (B) pay_qi_card.ocr_sender_name — the structured sender name (populated as the OCR backlog clears)
    cur.execute("""
        SELECT client_login, ocr_sender_name FROM pay_qi_card
        WHERE client_login IS NOT NULL AND COALESCE(ocr_sender_name,'') <> ''
    """)
    for login, nm in cur.fetchall():
        key = norm_sender_name(nm)
        if key:
            pair[(login, "qi", key)] += 1
            sender_clients[("qi", key)].add(login); qi_named += 1

    # --- ZainCash (sender wallet/phone — unchanged) ---
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
    print(f"qi sender-name deposit rows keyed: {qi_named:,}")
    cur.execute("SELECT method, count(*), count(DISTINCT client_login), count(DISTINCT sender_key) "
                "FROM client_payment_senders GROUP BY method")
    for m, r, cl, s in cur.fetchall():
        print(f"{m}: {r:,} rows | {cl:,} clients | {s:,} distinct senders")
    cur.execute("SELECT count(*) FROM (SELECT method,sender_key FROM client_payment_senders "
                "GROUP BY 1,2 HAVING count(DISTINCT client_login) BETWEEN 2 AND 6) t")
    print(f"family-candidate senders (shared by 2-6 clients): {cur.fetchone()[0]:,}")
    cur.execute("SELECT count(*) FROM (SELECT method,sender_key FROM client_payment_senders "
                "GROUP BY 1,2 HAVING count(DISTINCT client_login) > 6) t")
    print(f"exchanger senders (shared by >6 clients, excluded from family links): {cur.fetchone()[0]:,}")
    c.close()


if __name__ == "__main__":
    main()
