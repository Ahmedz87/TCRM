"""
flag_test_accounts.py — hide TradeSoft dummy/test accounts from the trading-accounts list + KPIs
WITHOUT destroying any data.

Some TradeSoft ECN accounts carry a FAKE round-number balance ($1M-$10M) backed only by a single
outlier "deposit" that the deposit-import already rejects (>= $1M cap) — so they show a huge balance
with 0 real deposits, 0 trades, and are not on MT. They are test entries, not real money.

Rule (all must hold): source='tradesoft' AND not on MT (mt_last_seen IS NULL) AND no real imported
deposits (total_deposits=0) AND balance >= $1,000,000 (same outlier threshold the deposit import uses).

We DON'T zero the balance (raw values kept). We set clients.archive_reason='tradesoft_test' +
archived_at (so the list, which hides archived rows, drops them) and trading_accounts.is_active=FALSE.
Idempotent. REVERSIBLE:
    UPDATE clients SET archived_at=NULL, archive_reason=NULL WHERE archive_reason='tradesoft_test';

Run:  python flag_test_accounts.py            (dry run — list them)
      python flag_test_accounts.py --commit   (apply)
"""
import sys
from sqlalchemy import text
from database import SessionLocal

BAL_CAP = 1_000_000

WHERE = f"""
    FROM clients cl JOIN trading_accounts ta ON ta.login = cl.login
    WHERE cl.archived_at IS NULL
      AND ta.source = 'tradesoft'
      AND cl.mt_last_seen IS NULL
      AND COALESCE(ta.total_deposits, 0) = 0
      AND COALESCE(ta.balance, 0) >= {BAL_CAP}
"""


def run(commit=False):
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT cl.login, cl.name, ta.balance, ta.group_name " + WHERE +
            " ORDER BY ta.balance DESC")).fetchall()
        print(f"Test accounts matching (fake >= ${BAL_CAP:,} balance, not on MT, 0 real deposits): {len(rows)}")
        for r in rows:
            print(f"   #{r[0]:<9} {str(r[1] or '')[:24]:24} ${float(r[2]):,.0f}  [{r[3]}]")
        if not rows:
            print("nothing to flag.")
            return {"flagged": 0}
        if not commit:
            print("\nDRY RUN — nothing changed. Re-run with --commit to hide these as test accounts.")
            return {"would_flag": len(rows)}
        logins = [r[0] for r in rows]
        db.execute(text(
            "UPDATE clients SET archived_at=NOW(), archive_reason='tradesoft_test' "
            "WHERE login = ANY(:l)"), {"l": logins})
        db.execute(text(
            "UPDATE trading_accounts SET is_active=FALSE WHERE login = ANY(:l)"), {"l": logins})
        db.commit()
        print(f"\nFlagged {len(logins)} account(s) as tradesoft_test (hidden from list + KPIs, data kept).")
        return {"flagged": len(logins)}
    finally:
        db.close()


if __name__ == "__main__":
    run(commit="--commit" in sys.argv)
