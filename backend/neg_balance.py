"""
Negative Balance Protection - Phase 1 (core engine + dry run)
Finds flat accounts with balance < 0, covers from credit using broker's proven pattern.

DRY RUN by default (LIVE=False) - shows what it WOULD do, moves NO money.
Test one account:  python neg_balance.py --login 12345
Scan all:          python neg_balance.py
Go live (careful): edit LIVE=True
"""
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager
from database import SessionLocal
from sqlalchemy import text

LIVE = False  # <-- keep False until tested. True = real money moves.

MT5_SERVER, MT5_LOGIN, MT5_PASSWORD = "192.109.15.62:443", 1025, "ZjFb!vA0"

def get_mgr():
    mgr = MT5Manager.ManagerAPI()
    ok = mgr.Connect(MT5_SERVER, MT5_LOGIN, MT5_PASSWORD)
    if not ok:
        print("MT5 connect FAILED"); sys.exit()
    return mgr

def is_flat(mgr, login):
    """True if no open positions."""
    positions = mgr.PositionGet(login)
    if positions is None:
        return True  # None = no positions
    return len(positions) == 0

def cover_account(mgr, login, dry=True):
    """Cover one account's negative balance from credit."""
    acc = mgr.UserAccountGet(login)
    if not acc:
        return {"login": login, "status": "no account data"}

    balance = float(acc.Balance)
    credit  = float(acc.Credit)

    if balance >= 0:
        return {"login": login, "status": "balance not negative", "balance": balance}

    deficit = abs(balance)  # how much we need to cover

    if not is_flat(mgr, login):
        return {"login": login, "status": "HAS OPEN POSITIONS - skip", "balance": balance, "credit": credit}

    if credit < deficit:
        return {"login": login, "status": f"CREDIT TOO LOW (need {deficit:.2f}, have {credit:.2f}) - skip",
                "balance": balance, "credit": credit, "deficit": deficit}

    # Eligible: flat + credit covers deficit
    result = {"login": login, "balance": balance, "credit": credit, "deficit": deficit,
              "cover_amount": deficit}

    if dry:
        result["status"] = f"WOULD COVER {deficit:.2f} (balance {balance:.2f} -> 0, credit {credit:.2f} -> {credit-deficit:.2f})"
        return result

    # LIVE: two-step cover (broker's proven pattern)
    # Step 1: add to balance (action=5, Negative balance payoff)
    r1 = mgr.DealerBalance(login, deficit, 5, "Negative balance payoff")
    # Step 2: reduce credit (action=3, Credit Out)
    r2 = mgr.DealerBalance(login, -deficit, 3, "Credit Out")
    result["status"] = f"COVERED {deficit:.2f} (step1={r1}, step2={r2})"
    return result

def main():
    args = sys.argv
    single = None
    if "--login" in args:
        single = int(args[args.index("--login")+1])

    mgr = get_mgr()
    print(f"{'='*55}")
    print(f"NEGATIVE BALANCE PROTECTION  [{'LIVE' if LIVE else 'DRY RUN'}]")
    print(f"{'='*55}")

    if single:
        r = cover_account(mgr, single, dry=not LIVE)
        print(f"\nAccount {single}:")
        for k,v in r.items():
            print(f"  {k}: {v}")
    else:
        # Find negative-balance accounts from DB first (fast), then verify live
        db = SessionLocal()
        negs = db.execute(text("""
            SELECT login FROM clients WHERE balance < 0 AND platform='MT5' ORDER BY balance ASC
        """)).fetchall()
        db.close()
        print(f"\nFound {len(negs)} MT5 accounts with negative balance in DB\n")
        eligible = 0
        for (login,) in negs[:50]:  # first 50 for safety in dry run
            r = cover_account(mgr, login, dry=not LIVE)
            status = r.get("status","")
            if "WOULD COVER" in status or "COVERED" in status:
                eligible += 1
                print(f"  #{login}: {status}")
            else:
                print(f"  #{login}: {status}")
        print(f"\n{eligible} eligible for cover")

    mgr.Disconnect()

if __name__ == "__main__":
    main()
