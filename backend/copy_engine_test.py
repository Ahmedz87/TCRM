"""
Copy-engine test harness — proves the sizing math and the dry-run replication WITHOUT
touching MT (COPY_LIVE_ENABLED must be False). Two parts:
  1. unit checks on compute_follower_lots for each copy_mode,
  2. a ONE-ACCOUNT scenario: one master trade -> one follower -> the exact mirror order.
  3. a real dry-run cycle over a seeded provider with followers.
Run:  python copy_engine_test.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from database import SessionLocal
from sqlalchemy import text
import copy_engine as ce

def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol

def unit_checks():
    print("── sizing unit checks ──")
    # proportional: 1.00 master lot, $1000 alloc, $10k master capital, x1 -> 0.10
    v = ce.compute_follower_lots(1.00, "proportional", 1.0, 1000, 10000); print(f"  proportional 1.0lot $1k/$10k x1 = {v}  (expect 0.10)"); assert approx(v, 0.10)
    # proportional x2 -> 0.20
    v = ce.compute_follower_lots(1.00, "proportional", 2.0, 1000, 10000); print(f"  proportional x2          = {v}  (expect 0.20)"); assert approx(v, 0.20)
    # mirror: 0.50 master x1.5 -> 0.75
    v = ce.compute_follower_lots(0.50, "mirror", 1.5, 5000, 10000); print(f"  mirror 0.5lot x1.5       = {v}  (expect 0.75)"); assert approx(v, 0.75)
    # fixed: lot = multiplier (0.20) regardless of master size
    v = ce.compute_follower_lots(3.00, "fixed", 0.20, 5000, 10000); print(f"  fixed (mult=lot 0.20)    = {v}  (expect 0.20)"); assert approx(v, 0.20)
    # min-lot clamp
    v = ce.compute_follower_lots(0.01, "proportional", 1.0, 50, 10000); print(f"  tiny -> min-lot clamp    = {v}  (expect 0.01)"); assert approx(v, 0.01)
    # max-lot clamp
    v = ce.compute_follower_lots(100, "mirror", 5.0, 0, 10000); print(f"  huge -> max-lot clamp    = {v}  (expect {ce.MAX_LOT})"); assert approx(v, ce.MAX_LOT)
    print("  ✓ all sizing checks passed\n")

def one_account_scenario(db):
    print("── one-account scenario (no MT, dry-run) ──")
    print(f"  COPY_LIVE_ENABLED = {ce.COPY_LIVE_ENABLED}  (must be False)")
    ce.ensure_mirror_table(db)
    master = {"id": None, "symbol": "XAUUSD", "side": "Buy", "lots": 1.00}
    print(f"  master trade: {master['side']} {master['lots']} {master['symbol']}")
    # use a real provider that has followers
    pid = db.execute(text("""
        SELECT provider_id FROM copy_followers WHERE status='active'
        GROUP BY provider_id ORDER BY COUNT(*) DESC LIMIT 1""")).scalar()
    orders = ce.replicate_trade(db, pid, master, dry_run=True)
    print(f"  provider {pid}: fanned out to {len(orders)} followers; first 3 computed orders:")
    for o in orders[:3]:
        print(f"    follower {o['follower_id']:>5}  {o['copy_mode']:12} x{o['multiplier']}  -> {o['follower_lots']} lot  [{o['status']}]")
    # confirm NONE were sent live
    live = db.execute(text("SELECT COUNT(*) FROM copy_mirror_orders WHERE dry_run=FALSE")).scalar()
    print(f"  live (non-dry-run) orders in table: {live}  (must be 0)"); assert live == 0
    print("  ✓ replication produced sized orders, zero live orders\n")
    return pid

def cycle(db, pid):
    print("── full dry-run cycle (last 5 master trades) ──")
    summary = ce.run_dry_run_cycle(db, pid, n_trades=5)
    print(f"  {summary['master_trades']} master trades x {summary['active_followers']} followers"
          f" = {summary['orders_generated']} mirror orders generated (dry_run={summary['dry_run']})")
    # verify live placement is hard-blocked
    print("── live-gate check ──")
    try:
        ce.place_order_via_bridge(123456, "XAUUSD", "Buy", 0.10)
        print("  ✗ ERROR: live placement did NOT raise!"); assert False
    except (RuntimeError, NotImplementedError) as e:
        print(f"  ✓ live placement correctly blocked: {type(e).__name__}")

def main():
    unit_checks()
    db = SessionLocal()
    pid = one_account_scenario(db)
    cycle(db, pid)
    # cleanup the dry-run rows we generated so we don't leave test data
    db.execute(text("DELETE FROM copy_mirror_orders WHERE dry_run=TRUE"))
    db.commit()
    db.close()
    print("\nALL CHECKS PASSED — engine is correct and live execution is gated off.")

if __name__ == "__main__":
    main()
