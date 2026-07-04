#!/usr/bin/env python3
"""
Fake-deposit-document STUDY across Qi Card / ZainCash / Sham Cash.
Reads OCR'd receipts (pay_* tables) + perceptual hashes (receipt_phash), reverse-engineers each
method's transaction-ID format, runs fraud checks (currency-aware), writes a verdict per row,
and prints + saves a report.

Signals: A) reused screenshot (rich phash across >1 deposit)  B) duplicate txid  C) future date
         D) amount mismatch (currency-aware IQD/USD)  E) series/structure violation
         F) Qi sender-id instability + counter regression
"""
import re
from datetime import datetime, timezone, timedelta
from collections import Counter
import psycopg2
import db_config
PG = db_config.DSN
QI_FIXED = "10121420010100166"
IQD_LO, IQD_HI = 1200, 1550          # accepted IQD-per-USD band (manual-deposit broker rate)

def digits(s): return re.sub(r"\D","", s or "")

def _plausible_date(d8):
    try: dt=datetime.strptime(d8,"%Y%m%d"); return 2018<=dt.year<=2035
    except: return False

def nibbles_set(h):
    """count of distinct hex chars — used to drop degenerate (blank/solid) phashes."""
    return len(set((h or "").lower())) if h else 0

def amount_verdict(oamt, samt):
    """returns (match_bool, detected_currency) — handles IQD receipts vs USD system amount."""
    try:
        o=float(oamt); s=float(samt)
    except: return (None, None)
    if s<=0 or o<=0: return (None, None)
    r=o/s
    if 0.97<=r<=1.03: return (True, "USD")
    if IQD_LO<=r<=IQD_HI: return (True, "IQD")
    # near an IQD conversion but off (>±20%)? flag
    return (False, "IQD" if r>200 else "USD")

def learn_format(txids, keep_lens=None):
    ds=[digits(t) for t in txids if digits(t)]
    if keep_lens: ds=[d for d in ds if len(d) in keep_lens]
    if not ds: return {}
    lens=[len(d) for d in ds]; lc=Counter(lens)
    dated=sum(1 for d in ds if len(d)>=8 and _plausible_date(d[:8]))>=0.6*len(ds)
    def cp(strs):
        if not strs: return ""
        p=strs[0]
        for s in strs[1:]:
            i=0
            while i<len(p) and i<len(s) and p[i]==s[i]: i+=1
            p=p[:i]
        return p
    prefix=cp([d[8:] for d in ds]) if dated else cp(ds)
    return {"count":len(ds),"len_hist":dict(lc.most_common(6)),"dated":dated,
            "fixed_block_after_date":prefix,"sample":ds[0]}

def main():
    pg=psycopg2.connect(PG); pg.autocommit=False; cur=pg.cursor()
    report=[]
    def P(*a):
        line=" ".join(str(x) for x in a); print(line); report.append(line)

    for table, method in [("pay_qi_card","Qi Card"),("pay_zaincash","ZainCash"),("pay_sham_cash","Sham Cash")]:
        P("\n"+"="*70); P(f"STUDY: {method}  [{table}]"); P("="*70)
        cur.execute(f"UPDATE {table} SET fraud_verdict=NULL, fraud_reasons=NULL WHERE ocr_status='done'")
        pg.commit()
        cur.execute(f"""SELECT id, client_login, sys_amount, status, tx_date, receipt_filename,
                        ocr_txid, ocr_sender_acct, ocr_receiver_acct, ocr_amount, ocr_datetime
                        FROM {table} WHERE ocr_status='done'""")
        rows=cur.fetchall()
        P(f"OCR'd receipts analysed: {len(rows):,}")
        if not rows:
            P("  (no OCR'd rows yet)"); continue

        # format (Qi: restrict to the real long txids 37-38; others: all)
        keep = {37,38} if method=="Qi Card" else None
        txids=[r[6] for r in rows if r[6]]
        fmt=learn_format(txids, keep)
        P(f"  txid present: {len(txids):,}/{len(rows):,}")
        P(f"  FORMAT{' (len 37-38)' if keep else ''}: lengths={fmt.get('len_hist')} dated={fmt.get('dated')} "
          f"fixed-block-after-date={fmt.get('fixed_block_after_date')!r}")
        P(f"  sample txid: {fmt.get('sample')}")

        # A) reused screenshot — RICH phash only (>=8 distinct nibbles) to drop blank/solid images
        cur.execute(f"""SELECT p.phash, count(DISTINCT t.id) n, count(DISTINCT t.client_login) cl
                        FROM {table} t JOIN receipt_phash p ON p.filename=t.receipt_filename
                        WHERE p.phash IS NOT NULL
                        GROUP BY p.phash HAVING count(DISTINCT t.id)>1 ORDER BY n DESC""")
        allg=cur.fetchall()
        rich=[(h,n,cl) for (h,n,cl) in allg if nibbles_set(h)>=8]
        multi_client=[g for g in rich if g[2]>1]
        P(f"  A) REUSED SCREENSHOTS (rich phash): {len(rich):,} groups; "
          f"{len(multi_client):,} span >1 client (worst {rich[0][1] if rich else 0} deposits/one image)")
        reused_phashes={h for (h,n,cl) in rich}

        # B) duplicate txid (>=15 digits to ignore short misreads)
        cur.execute(f"""SELECT ocr_txid, count(*) n FROM {table}
                        WHERE ocr_txid IS NOT NULL AND length(regexp_replace(ocr_txid,'\\D','','g'))>=15
                        GROUP BY ocr_txid HAVING count(*)>1 ORDER BY n DESC""")
        dup_txid=cur.fetchall()
        P(f"  B) DUPLICATE TXIDs: {len(dup_txid):,} (worst x{dup_txid[0][1] if dup_txid else 0})")

        # per-row verdicts
        suspects=0; rc={}; cur_by_sender={}
        qi_sid={}
        if method=="Qi Card":
            for r in rows:
                d=digits(r[6])
                if len(d)>=31 and d[8:25]==QI_FIXED and r[7]:
                    qi_sid.setdefault(r[7],set()).add(d[25:31])
        for r in rows:
            rid, login, sysamt, status, txd, fn, txid, sacct, racct, oamt, odt = r
            rs=[]; d=digits(txid)
            # C future txid date
            if len(d)>=8 and _plausible_date(d[:8]):
                try:
                    tdt=datetime.strptime(d[:8],"%Y%m%d").date()
                    if tdt>(datetime.now(timezone.utc)+timedelta(days=1)).date(): rs.append("future_txid_date")
                except: pass
            # D amount (currency-aware)
            m,ccy=amount_verdict(oamt, sysamt)
            if m is False: rs.append("amount_mismatch")
            # E series/structure
            if method=="Qi Card" and d:
                if len(d) in (37,38) and d[8:25]!=QI_FIXED: rs.append("qi_series_violation")
            # F Qi sender-id instability
            if method=="Qi Card" and sacct and sacct in qi_sid and len(qi_sid[sacct])>1:
                rs.append("qi_senderid_unstable")
            # A membership
            # (phash flagged separately below)
            if rs:
                suspects+=1
                for x in rs: rc[x]=rc.get(x,0)+1
                cur.execute(f"UPDATE {table} SET fraud_verdict='suspect', fraud_reasons=%s WHERE id=%s",
                            (",".join(rs), rid))
            else:
                cur.execute(f"UPDATE {table} SET fraud_verdict='clean' WHERE id=%s",(rid,))
        # duplicate txid -> suspect
        for txid,n in dup_txid:
            cur.execute(f"""UPDATE {table} SET fraud_verdict='suspect',
                fraud_reasons=CASE WHEN fraud_reasons IS NULL OR fraud_reasons=''
                    THEN 'duplicate_txid' ELSE fraud_reasons||',duplicate_txid' END
                WHERE ocr_txid=%s""",(txid,))
            rc['duplicate_txid']=rc.get('duplicate_txid',0)+1
        # reused screenshot -> suspect
        if reused_phashes:
            cur.execute(f"""UPDATE {table} t SET fraud_verdict='suspect',
                fraud_reasons=CASE WHEN t.fraud_reasons IS NULL OR t.fraud_reasons=''
                    THEN 'reused_screenshot' ELSE t.fraud_reasons||',reused_screenshot' END
                FROM receipt_phash p
                WHERE p.filename=t.receipt_filename AND p.phash = ANY(%s)""",(list(reused_phashes),))
        pg.commit()
        P(f"  -> per-row suspects (excl. reused-img): {suspects:,}  reasons={rc}")
        cur.execute(f"SELECT count(*) FILTER (WHERE fraud_verdict='suspect'), count(*) FILTER (WHERE fraud_verdict='clean') FROM {table} WHERE ocr_status='done'")
        s,c=cur.fetchone(); P(f"  -> TOTAL flagged suspect (incl reused-img+dup): {s:,} | clean: {c:,}")
        if method=="Qi Card":
            st=sum(1 for v in qi_sid.values() if len(v)==1); un=sum(1 for v in qi_sid.values() if len(v)>1)
            P(f"  Qi sender-id: {st} accounts stable, {un} with MULTIPLE sender-ids (forgery signal)")

    with open("deposit_fraud_study_report.txt","w",encoding="utf-8") as f:
        f.write("\n".join(report))
    P("\nreport saved -> deposit_fraud_study_report.txt")
    pg.close()

if __name__=="__main__": main()
