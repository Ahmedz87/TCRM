"""Builds client_sender_blocks: per client + Qi sender-wallet (4-digit block), the set of blocks
they use AND a ROBUST max sequence (highest 8-digit global-counter value among their ON-CURVE
deposits — misreads excluded). Powers two live fraud checks:
  4e  block4 the client has never used  -> "copied receipt" flag
  4f  new deposit's 8-digit sequence < the client's max from that wallet -> "old/reused" flag
Idempotent. RE-RUN after OCR batches / periodically. python build_sender_blocks.py
Schema note: the table was rebuilt Jul 2026 (block4 PK + max_seq); old block5/block6 columns dropped.
"""
import sys, io, unicodedata, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import db_config
from collections import defaultdict
FIXED = "10121420010100166"


def norm(t):
    o = []
    for ch in (t or ""):
        if ch.isdigit():
            try: o.append(str(unicodedata.digit(ch)))
            except Exception: pass
    return "".join(o)


def main():
    c = db_config.connect(); c.autocommit = False; cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS client_sender_blocks")
    cur.execute("""CREATE TABLE client_sender_blocks(
      client_login BIGINT, block4 TEXT,
      max_seq BIGINT,        -- highest 8-digit sequence among this client's ON-CURVE deposits from this wallet
      n INT, first_seen DATE, last_seen DATE,
      PRIMARY KEY(client_login, block4))""")
    cur.execute("CREATE INDEX ix_csb_login ON client_sender_blocks(client_login)")
    c.commit()

    cur.execute("SELECT day, median_seq FROM qi_seq_curve WHERE n>=3 ORDER BY day")
    curve = cur.fetchall()

    def expected(d):
        lo = hi = None
        for cd, cm in curve:
            if cd <= d: lo = (cd, cm)
            if cd >= d and hi is None: hi = (cd, cm)
        if lo and hi and hi[0] != lo[0]:
            f = (d - lo[0]).days / (hi[0] - lo[0]).days
            return lo[1] + f * (hi[1] - lo[1])
        return lo[1] if lo else (hi[1] if hi else None)

    cur.execute("""SELECT d.client_login, q.ocr_txid, d.tx_date
      FROM deposit_documents d JOIN pay_qi_card q ON q.receipt_filename=d.receipt_filename
      WHERE d.client_login IS NOT NULL AND q.ocr_txid IS NOT NULL""")
    agg = defaultdict(lambda: {"n": 0, "max_onc": None, "max_all": None, "f": None, "l": None})
    for login, tx, txd in cur.fetchall():
        t = norm(tx)
        # [8 date][17 fixed][4-5 block][8 seq] -> 37 or 38 digits; block4 col holds either width
        if len(t) not in (37, 38) or t[8:25] != FIXED:
            continue
        b4 = t[25:-8]; seq = int(t[-8:])
        try:
            td = datetime.date(int(t[:4]), int(t[4:6]), int(t[6:8]))
        except ValueError:
            continue
        a = agg[(login, b4)]; a["n"] += 1
        a["max_all"] = seq if a["max_all"] is None else max(a["max_all"], seq)
        e = expected(td)
        if e is not None and abs(seq - e) < 400_000:      # ON-CURVE = trustworthy reference
            a["max_onc"] = seq if a["max_onc"] is None else max(a["max_onc"], seq)
        ds = str(txd)[:10]
        if a["f"] is None or ds < a["f"]: a["f"] = ds
        if a["l"] is None or ds > a["l"]: a["l"] = ds

    import psycopg2.extras as ex
    # max_seq is ON-CURVE only (NULL if this wallet has no trustworthy deposit) — never the raw max,
    # so a block seen only via misreads can't set a bogus (e.g. 67M) reference.
    rows = [(login, b4, a["max_onc"], a["n"], a["f"], a["l"]) for (login, b4), a in agg.items()]
    ex.execute_batch(cur, """INSERT INTO client_sender_blocks
      (client_login, block4, max_seq, n, first_seen, last_seen) VALUES (%s,%s,%s,%s,%s,%s)""",
      rows, page_size=1000)
    c.commit()
    cur.execute("SELECT count(DISTINCT client_login), count(*), count(*) FILTER (WHERE max_seq IS NOT NULL) "
                "FROM client_sender_blocks")
    cl, rw, withseq = cur.fetchone()
    cur.execute("SELECT count(*) FROM (SELECT client_login FROM client_sender_blocks GROUP BY 1 HAVING count(*)=1) t")
    one = cur.fetchone()[0]
    print(f"registry: {cl:,} clients | {rw:,} (client,wallet) rows | {withseq:,} with a sequence ref")
    print(f"single-wallet clients: {one:,}")
    c.close()


if __name__ == "__main__":
    main()
