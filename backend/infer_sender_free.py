# -*- coding: utf-8 -*-
"""FREE global sender inference: block + NAME match using the already-stored Tesseract text.
No API calls. The sender name is inside ocr_tess_text; instead of extracting it we compare
receipts on RARE tokens (names) after dropping boilerplate (labels/app text on every receipt).

validate : hold-out test on receipts whose full sender IS known -> accuracy report
apply    : fill transaction_wallet.sender_acct (sender_src='inferred') for block-only rows
Usage: python infer_sender_free.py [validate|apply]
"""
import sys, io, re, unicodedata
from collections import Counter, defaultdict
import db_config

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
FIXED = "10121420010100166"
MIN_SHARED = 3          # rare tokens shared to accept a match (2 lets relatives collide)
MARGIN = 2              # winner must beat the runner-up account by this many tokens
DF_CUT = 0.05           # tokens in >5% of receipts = boilerplate


def norm(s):
    out = []
    for ch in (s or ""):
        if ch.isdigit():
            try: out.append(str(unicodedata.digit(ch)))
            except Exception: pass
        else:
            out.append(ch)
    s = "".join(out).lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"), ("ى", "ي"),
                 ("ة", "ه"), ("ئ", "ي"), ("ؤ", "و")):
        s = s.replace(a, b)
    s = re.sub(r"[ً-ٰٟ]", "", s)
    return s


def tokens(text):
    # alpha tokens length>=3 (arabic or latin) — numbers/amounts/dates excluded
    return set(t for t in re.findall(r"[a-z؀-ۿ]{3,}", norm(text)))


def load(cur):
    cur.execute("""SELECT q.id, q.receipt_filename,
        regexp_replace(q.ocr_txid,'\\D','','g') AS d,
        regexp_replace(COALESCE(q.ocr_sender_acct,''),'\\D','','g') AS snd,
        q.ocr_tess_text
      FROM pay_qi_card q
      WHERE q.ocr_txid IS NOT NULL AND q.ocr_tess_text IS NOT NULL""")
    teachers, students, df = [], [], Counter()
    n = 0
    for rid, fn, d, snd, txt in cur.fetchall():
        if len(d) not in (37, 38) or d[8:25] != FIXED:
            continue
        blk = d[25:-8]
        tok = tokens(txt)
        if not tok:
            continue
        n += 1
        for t in tok: df[t] += 1
        (teachers if len(snd) == 10 else students).append((rid, fn, blk, snd, tok))
    boiler = {t for t, k in df.items() if k > n * DF_CUT}
    for lst in (teachers, students):
        for i, (rid, fn, blk, snd, tok) in enumerate(lst):
            lst[i] = (rid, fn, blk, snd, tok - boiler)
    return teachers, students


def best_match(blk, tok, tmap, skip_rid=None):
    """all teachers of this block scored by rare-token overlap; accept if the winners
    agree on ONE account with >=MIN_SHARED shared tokens."""
    cands = defaultdict(int)
    for rid, fn, snd, ttok in tmap.get(blk, ()):
        if rid == skip_rid:
            continue
        ov = len(tok & ttok)
        if ov > cands[snd]:
            cands[snd] = ov
    good = [(s, o) for s, o in cands.items() if o >= MIN_SHARED]
    if not good:
        return None
    good.sort(key=lambda x: -x[1])
    if len(good) > 1 and good[0][1] - good[1][1] < MARGIN:   # too close between accounts -> refuse
        return None
    return good[0][0]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "validate"
    c = db_config.connect(); cur = c.cursor()
    teachers, students = load(cur)
    tmap = defaultdict(list)
    for rid, fn, blk, snd, tok in teachers:
        tmap[blk].append((rid, fn, snd, tok))
    print(f"teachers {len(teachers):,} | students {len(students):,} | blocks with teachers {len(tmap):,}")

    if mode == "validate":
        # hold-out: teachers that share a block with ANOTHER teacher; hide their acct and predict
        tested = correct = wrong = 0
        for rid, fn, blk, snd, tok in teachers:
            if len(tmap[blk]) < 2:
                continue
            pred = best_match(blk, tok, tmap, skip_rid=rid)
            if pred is None:
                continue
            tested += 1
            if pred == snd: correct += 1
            else: wrong += 1
            if tested >= 4000:
                break
        pct = 100 * correct // max(tested, 1)
        print(f"hold-out: {tested:,} decided | correct {correct:,} ({pct}%) | wrong {wrong:,}")
        print("apply only if correct% >= 97")
    elif mode == "apply":
        # block-only transaction rows -> match their receipt
        cur.execute("""SELECT tw.transaction_id, tw.sender_block, tw.receipt_filename
          FROM transaction_wallet tw
          WHERE tw.sender_acct IS NULL AND tw.sender_block IS NOT NULL""")
        rows = cur.fetchall()
        bystu = {}
        for rid, fn, blk, snd, tok in students:
            bystu[fn] = (blk, tok)
        fills = []
        for txn_id, blk, fn in rows:
            st = bystu.get(fn)
            if not st or st[0] != blk:
                continue
            pred = best_match(blk, st[1], tmap)
            if pred:
                fills.append((pred, txn_id))
        import psycopg2.extras as ex
        ex.execute_batch(cur, """UPDATE transaction_wallet
            SET sender_acct=%s, sender_src='inferred'
            WHERE transaction_id=%s AND sender_acct IS NULL""", fills, page_size=1000)
        c.commit()
        print(f"filled {len(fills):,} transactions by free block+name(text) match")
    c.close()


if __name__ == "__main__":
    main()
