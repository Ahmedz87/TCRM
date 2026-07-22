"""Builds the Qi txid GLOBAL-SEQUENCE reference curve + feeds bulk-OCR'd receipts into qi_txid_samples.

STUDY (Jul 2026, 3,382 clean receipts): Qi txid = [8 YYYYMMDD][17 fixed 10121420010100166]
[4 SENDER-ID][8 GLOBAL SEQUENCE]. The 4-digit sender-id is deterministic per sender wallet
(211/211 senders, 100%). The 8-digit tail is a SYSTEM-WIDE counter advancing ~25.5k/day
(2.63M Oct-2025 -> 6.61M Jun-2026); 99% of genuine receipts sit within ±256k of their
day's median. So a receipt's sequence must match its date on this curve — forged txids
and date-edited old receipts land far off it.

Creates/refreshes:
  qi_seq_curve(day DATE PK, median_seq BIGINT, n INT)  — daily medians from all clean txids
Also inserts clean bulk-OCR receipts into qi_txid_samples (source='ocr_bulk'; never used as
an 'approved' hard-reject reference, but powers the sender-block + counter soft checks).

Re-run periodically (or after big OCR batches): python build_qi_seq_curve.py
"""
import re, datetime, statistics
import db_config

FIXED = "10121420010100166"
AR = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
AR.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})


def norm(t):
    return re.sub(r"\D", "", (t or "").translate(AR))


def main():
    c = db_config.connect(); c.autocommit = False; cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS qi_seq_curve (
        day DATE PRIMARY KEY, median_seq BIGINT NOT NULL, n INT NOT NULL)""")

    # 1) collect every clean 37-digit txid we know: bulk OCR + curated samples
    txids = set()
    cur.execute("SELECT ocr_txid, COALESCE(ocr_sender_acct,''), COALESCE(ocr_receiver_acct,''), ocr_amount, ocr_datetime "
                "FROM pay_qi_card WHERE ocr_txid IS NOT NULL")
    bulk = cur.fetchall()
    cur.execute("SELECT txid FROM qi_txid_samples WHERE length(txid)=37")
    for (t,) in cur.fetchall():
        txids.add(t)

    by_day, feed = {}, []
    # txid = [8 date][17 fixed][4-5 block][8 seq] -> 37 or 38 digits; seq = LAST 8
    for tx, snd, rcv, amt, odt in bulk:
        t = norm(tx)
        if len(t) not in (37, 38) or t[8:25] != FIXED:
            continue
        try:
            d = datetime.date(int(t[:4]), int(t[4:6]), int(t[6:8]))
        except ValueError:
            continue
        if not (datetime.date(2020, 1, 1) <= d <= datetime.date.today() + datetime.timedelta(days=1)):
            continue
        by_day.setdefault(d, []).append(int(t[-8:]))
        if t not in txids and len(t) == 37:   # samples table keeps the 37-digit layout
            feed.append((t, snd.strip(), rcv.strip(), amt, t[:8], FIXED, t[25:31], t[31:]))
            txids.add(t)
    for t in list(txids):
        tt = norm(t)
        if len(tt) in (37, 38) and tt[8:25] == FIXED:
            try:
                d = datetime.date(int(tt[:4]), int(tt[4:6]), int(tt[6:8]))
                by_day.setdefault(d, []).append(int(tt[-8:]))
            except ValueError:
                pass

    # 2) refresh the curve (days with >=3 receipts -> stable medians)
    cur.execute("TRUNCATE qi_seq_curve")
    rows = [(d, int(statistics.median(v)), len(v)) for d, v in sorted(by_day.items()) if len(v) >= 3]
    cur.executemany("INSERT INTO qi_seq_curve (day, median_seq, n) VALUES (%s,%s,%s)", rows)

    # 3) feed the bulk receipts into the learning set (soft references only)
    fed = 0
    for t, snd, rcv, amt, dpart, fx, sid, tpart in feed:
        cur.execute("""INSERT INTO qi_txid_samples
            (txid, amount, sender_acct, receiver_acct, date_part, fixed_part, sender_id, txn_part, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ocr_bulk') ON CONFLICT (txid) DO NOTHING""",
            (t, amt, snd, rcv, dpart, fx, sid, tpart))
        fed += cur.rowcount
    c.commit()
    print(f"curve: {len(rows)} days (span {rows[0][0]} -> {rows[-1][0]})" if rows else "curve: no data")
    print(f"qi_txid_samples: +{fed} ocr_bulk receipts fed")
    cur.execute("SELECT count(*), count(DISTINCT sender_acct) FILTER (WHERE sender_acct<>'') FROM qi_txid_samples")
    n, s = cur.fetchone()
    print(f"total samples now: {n:,} ({s:,} distinct known senders)")
    c.close()


if __name__ == "__main__":
    main()
