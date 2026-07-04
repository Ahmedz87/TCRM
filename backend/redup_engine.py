"""
redup_engine.py — greedy ONE-TO-ONE re-dedup of TradeSoft-vs-MT transactions.

The old race-dedup flagged a TradeSoft row *_dup whenever ANY MT deal of the same login+amount fell
within ±1 day. That has two failure modes:
  • MISS  — crypto/USDT deposits settle slowly, so the MT credit lands >1 day after the TradeSoft row →
            neither is deduped → the SAME deposit is counted twice.
  • FALSE — a client genuinely makes two same-amount transactions in a window → the 2nd gets wrongly
            flagged a duplicate of the 1st's MT deal (which is already paired) → real money uncounted.

This engine fixes both: per (login, base_type, amount) it greedily matches each TradeSoft row to the
NEAREST-in-time UNUSED MT deal within WINDOW_DAYS (one MT deal pairs at most one TS row). Matched TS →
*_dup; unmatched TS → base type (un-dup). Idempotent — recomputes the correct state each run. Scoped to
recent rows so it's cheap; run every sync cycle. Robust fix is a deal-number in the comment (future).
"""
import db_config
import psycopg2
from psycopg2.extras import execute_values
from collections import defaultdict

WINDOW_DAYS = 7          # crypto can settle up to a week after the gateway records it
LOOKBACK_DAYS = 45       # only re-pair recent rows (cheap; older rows are settled)

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME,
          user=db_config.DB_USER, password=db_config.DB_PASSWORD)


def run(conn=None):
    own = conn is None
    if own:
        conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    win = WINDOW_DAYS * 86400
    cur.execute("""SELECT id, login, regexp_replace(tx_type,'_dup$','') bt, round(amount::numeric,2) a,
                          tx_date::timestamp ts, tx_type
                   FROM transactions
                   WHERE deal_id>=8000000000 AND deal_id<9000000000
                     AND tx_type IN ('deposit','deposit_dup','withdrawal','withdrawal_dup')
                     AND tx_date::timestamp > NOW() - INTERVAL '%s days'""" % LOOKBACK_DAYS)
    ts_rows = cur.fetchall()
    if not ts_rows:
        if own: conn.close()
        return (0, 0)
    logins = tuple(sorted({r[1] for r in ts_rows}))
    cur.execute("""SELECT login, tx_type bt, round(amount::numeric,2) a, tx_date::timestamp ts
                   FROM transactions WHERE deal_id<8000000000 AND tx_type IN ('deposit','withdrawal')
                     AND login IN %%s AND tx_date::timestamp > NOW() - INTERVAL '%s days'""" % (LOOKBACK_DAYS + 15),
                (logins,))
    mt = defaultdict(list)
    for L, bt, a, tsd in cur.fetchall():
        mt[(L, bt, a)].append({"ts": tsd, "used": False})
    for k in mt:
        mt[k].sort(key=lambda x: x["ts"])
    tsg = defaultdict(list)
    for r in ts_rows:
        tsg[(r[1], r[2], r[3])].append({"id": r[0], "ts": r[4], "cur": r[5]})
    to_dup, to_undup = [], []
    for k, rows in tsg.items():
        rows.sort(key=lambda x: x["ts"])
        cand = mt.get(k, [])
        for r in rows:
            best, bestd = None, None
            for m in cand:
                if m["used"]:
                    continue
                d = abs((r["ts"] - m["ts"]).total_seconds())
                if d <= win and (bestd is None or d < bestd):
                    best, bestd = m, d
            want_dup = best is not None
            if want_dup:
                best["used"] = True
            is_dup = r["cur"].endswith("_dup")
            if want_dup and not is_dup:
                to_dup.append(r["id"])
            elif (not want_dup) and is_dup:
                to_undup.append(r["id"])
    if to_dup:
        execute_values(cur, "UPDATE transactions t SET tx_type=t.tx_type||'_dup', updated_at=NOW() "
                            "FROM (VALUES %s) v(id) WHERE t.id=v.id AND t.tx_type NOT LIKE '%%_dup'",
                       [(i,) for i in to_dup])
    if to_undup:
        execute_values(cur, "UPDATE transactions t SET tx_type=regexp_replace(t.tx_type,'_dup$',''), updated_at=NOW() "
                            "FROM (VALUES %s) v(id) WHERE t.id=v.id",
                       [(i,) for i in to_undup])
    conn.commit()
    if own:
        conn.close()
    return (len(to_dup), len(to_undup))


if __name__ == "__main__":
    d, u = run()
    print(f"redup: flagged {d} duplicate(s), un-flagged {u}")
