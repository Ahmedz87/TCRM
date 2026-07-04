"""
refresh_loyalty_commission.py — keep the two MANUAL-rebuild datasets LIVE.

Both were one-off scripts that only ran when someone ran them by hand, so they froze:
  • ib_commissions   (feeds the live sales commission = (markup - IB) x pct)  — was stuck Jun 17
  • loyalty_accounts (points / tiers / streaks)                               — was stuck Jun 16

This recomputes both from current `deals` and is wired to a daily Task Scheduler job
(BrokerCRM-LoyaltyCommission). DB-only — no MT bridge / interactive session needed.

Run manually any time:  python refresh_loyalty_commission.py
"""
import sys, time, datetime
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from database import SessionLocal
from sqlalchemy import text


def main():
    t0 = time.time()
    now = datetime.datetime.now()
    print(f"=== refresh start {now:%Y-%m-%d %H:%M:%S} ===", flush=True)

    # 1) IB commissions — fast set-based rebuild (atomic DELETE+INSERT). Feeds sales commission.
    print("[1/2] ib_commissions ...", flush=True)
    import populate_ib_commissions as PIC
    PIC.run()
    print(f"      ib_commissions done in {time.time()-t0:.1f}s", flush=True)

    # 2) Loyalty — full rebuild over a ROLLING window through today (so new months aren't dropped).
    t1 = time.time()
    print("[2/2] loyalty rebuild ...", flush=True)
    import loyalty_engine as LE
    db = SessionLocal()
    try:
        LE.ensure_schema(db)
        start = datetime.date(2025, 1, 1)
        end   = datetime.date.today() + datetime.timedelta(days=1)   # inclusive of today
        LE.rebuild_from_trades(db, start, end)
        r = db.execute(text("""
            SELECT COUNT(*), ROUND(SUM(points_balance)::numeric,0),
                   COUNT(*) FILTER (WHERE tier='gold'), COUNT(*) FILTER (WHERE tier='platinum')
            FROM loyalty_accounts
        """)).fetchone()
        print(f"      loyalty members={r[0]} points={r[1]} gold={r[2]} platinum={r[3]}", flush=True)
    finally:
        db.close()
    print(f"      loyalty done in {time.time()-t1:.1f}s", flush=True)
    print(f"=== refresh OK total {time.time()-t0:.1f}s ===", flush=True)


if __name__ == "__main__":
    main()
