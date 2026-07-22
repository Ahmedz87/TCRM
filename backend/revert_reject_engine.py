"""revert_reject_engine — flag the ORIGINAL withdrawal of each withdrawal_revert as rejected.

A 'withdrawal_revert' means the client's withdrawal was REJECTED by back-office and the money
refunded to the MT account — so the original withdrawal never really left and must not count
in withdrawal totals (rule set Jul 2026; July was ~$126k over-counted before this).

Matching is GREEDY-ALL, 1:1, per (login, round(amount,2)):
  each revert (time order) consumes the CLOSEST EARLIER unused withdrawal of ANY status —
  if that row is already 'rejected' the revert is considered handled (no-op); if it is
  approved it gets flagged 'rejected'. Consuming rejected rows first is what makes re-runs
  IDEMPOTENT and is empirically the accurate pairing (per-login error vs TradeSoft ~$1.8k
  over 423 July logins; naive alternatives mis-reject by $25k+ or, worse, walk past an
  already-handled original and reject a GENUINE withdrawal — a ~$1.3M mistake avoided).

Windows: reverts from the last REVERT_DAYS, withdrawals from the last WD_DAYS (wider so an
original never falls outside while its revert is in scope). Standalone run: full history.
"""
import sys
from collections import defaultdict

REVERT_DAYS = 45
WD_DAYS     = 90


def run(conn=None, full_history=False):
    """Returns the number of withdrawals newly flagged rejected. Idempotent."""
    own = conn is None
    if own:
        import db_config
        conn = db_config.connect()
    cur = conn.cursor()
    win_rv = "" if full_history else \
        f"AND tx_date > to_char(NOW() - INTERVAL '{REVERT_DAYS} days','YYYY-MM-DD')"
    win_wd = "" if full_history else \
        f"AND tx_date > to_char(NOW() - INTERVAL '{WD_DAYS} days','YYYY-MM-DD')"

    cur.execute(f"""SELECT login, round(amount::numeric,2), tx_date
        FROM transactions WHERE tx_type='withdrawal_revert' {win_rv} ORDER BY tx_date""")
    reverts = cur.fetchall()
    cur.execute(f"""SELECT id, login, round(amount::numeric,2), tx_date, COALESCE(status,'')
        FROM transactions WHERE tx_type='withdrawal' {win_wd} ORDER BY tx_date""")
    idx = defaultdict(list)                    # (login, amt) -> [(date, id, status)] sorted
    for wid, lg, amt, dt, st in cur.fetchall():
        idx[(lg, float(amt))].append((str(dt), wid, st))

    used, to_reject = set(), []
    for lg, amt, rdt in reverts:
        best = None
        for dt, wid, st in idx.get((lg, float(amt)), []):
            if wid in used:
                continue
            if dt <= str(rdt):
                best = (wid, st)               # keep walking: closest earlier wins
            else:
                break
        if best:
            used.add(best[0])
            if best[1] != 'rejected':
                to_reject.append(best[0])

    if to_reject:
        for i in range(0, len(to_reject), 1000):
            cur.execute("""UPDATE transactions SET status='rejected', updated_at=NOW()
                           WHERE id = ANY(%s) AND COALESCE(status,'') <> 'rejected'""",
                        (to_reject[i:i + 1000],))
        conn.commit()
    if own:
        conn.close()
    return len(to_reject)


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    full = '--full' in sys.argv
    n = run(full_history=full)
    print(f"revert_reject_engine: {n} original withdrawal(s) flagged rejected"
          f" ({'full history' if full else f'last {REVERT_DAYS}d reverts'})")
