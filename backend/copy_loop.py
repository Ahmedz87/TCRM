"""
Copy-Trading replication daemon — DRY-RUN.

Tails each approved provider's master trades and fans them out to followers via the engine,
in DRY-RUN (no MT orders; gated by copy_engine.COPY_LIVE_ENABLED which stays False). Computes
each follower's copied P/L and writes it back to copy_followers.pnl so 'My Copies' shows real
results. A per-provider cursor (copy_provider_cursor) makes it incremental & idempotent.

Master-trade SOURCE per provider:
  • real provider (copy_providers.login set) -> live `deals` rows for that login (future masters)
  • synthetic provider (login NULL, the seeded 50) -> replays `copy_provider_trades` as the feed

Usage:
  python copy_loop.py --once                 one cycle then exit (great for testing)
  python copy_loop.py --loop [--interval 20] run forever
  python copy_loop.py --status               show per-provider progress
  python copy_loop.py --reset                clear cursors + loop mirror orders + zero follower pnl
"""
import sys, time, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from database import SessionLocal
from sqlalchemy import text
import copy_engine as ce

BATCH = 15        # master trades pulled per provider per cycle
CAP = 40          # demo cap: stop pulling from the synthetic backlog after this many/provider

def get_cursor(db, pid):
    r = db.execute(text("SELECT last_source_id, processed FROM copy_provider_cursor WHERE provider_id=:p"),
                   {"p": pid}).fetchone()
    if not r:
        db.execute(text("INSERT INTO copy_provider_cursor (provider_id,last_source_id,processed) VALUES (:p,0,0)"),
                   {"p": pid}); db.commit()
        return 0, 0
    return int(r[0] or 0), int(r[1] or 0)

def set_cursor(db, pid, last_id, processed):
    db.execute(text("""UPDATE copy_provider_cursor
        SET last_source_id=:l, processed=:n, updated_at=NOW() WHERE provider_id=:p"""),
        {"l": last_id, "n": processed, "p": pid})
    db.commit()

def fetch_new_master_trades(db, prov, last_id):
    """Return [{id,symbol,side,lots,pnl}] newer than last_id for this provider."""
    pid, login = prov[0], prov[1]
    if login:  # real master — tail the deals table (dormant until providers get real logins)
        rows = db.execute(text("""
            SELECT id, symbol, CASE WHEN action=0 THEN 'Buy' ELSE 'Sell' END,
                   volume/10000.0, profit
            FROM deals WHERE login=:lg AND entry=1 AND action IN (0,1) AND id > :c
            ORDER BY id LIMIT :b
        """), {"lg": login, "c": last_id, "b": BATCH}).fetchall()
    else:      # synthetic provider — replay seeded trades as the live feed
        rows = db.execute(text("""
            SELECT id, symbol, side, lots, pnl FROM copy_provider_trades
            WHERE provider_id=:p AND id > :c ORDER BY id LIMIT :b
        """), {"p": pid, "c": last_id, "b": BATCH}).fetchall()
    return [{"id": r[0], "symbol": r[1], "side": r[2], "lots": float(r[3] or 0),
             "pnl": float(r[4]) if r[4] is not None else None} for r in rows]

def recompute_follower_pnl(db, pid):
    """Follower P/L = sum of their loop mirror-order P/L for this provider."""
    db.execute(text("""
        UPDATE copy_followers f
        SET pnl = COALESCE((SELECT SUM(m.pnl) FROM copy_mirror_orders m
                            WHERE m.follower_id=f.id AND m.source='loop'), 0)
        WHERE f.provider_id=:p AND f.status='active'
    """), {"p": pid})
    db.commit()

def cycle(db):
    ce.ensure_mirror_table(db)
    provs = db.execute(text(
        "SELECT id, login FROM copy_providers WHERE status='approved' ORDER BY id"
    )).fetchall()
    total_orders = 0; active_provs = 0
    for prov in provs:
        pid = prov[0]
        last_id, processed = get_cursor(db, pid)
        if processed >= CAP and not prov[1]:
            continue  # synthetic backlog caught up (demo cap)
        trades = fetch_new_master_trades(db, prov, last_id)
        if not trades:
            continue
        active_provs += 1
        for mt in trades:
            orders = ce.replicate_trade(db, pid, mt, dry_run=True, source="loop")
            total_orders += len(orders)
            last_id = mt["id"]; processed += 1
            if processed >= CAP and not prov[1]:
                break
        set_cursor(db, pid, last_id, processed)
        recompute_follower_pnl(db, pid)
    # safety sweeps each cycle: enforce stops, suspend flagged, notify inactive, settle payouts
    try:
        import copy_features as CF
        CF.enforce_risk(db); CF.auto_suspend_flagged(db)
        CF.notify_inactive_providers(db); CF.settle_payouts(db)
    except Exception:
        db.rollback()
    return total_orders, active_provs, len(provs)

def show_status(db):
    ce.ensure_mirror_table(db)
    tot = db.execute(text("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM copy_mirror_orders WHERE source='loop'")).fetchone()
    cur = db.execute(text("SELECT COUNT(*), COALESCE(SUM(processed),0) FROM copy_provider_cursor")).fetchone()
    print(f"providers with cursor: {cur[0]} | master trades processed: {cur[1]}")
    print(f"loop mirror orders: {tot[0]} | aggregate copied P/L: ${float(tot[1]):,.2f}")
    print("\nTop 6 followers by copied P/L:")
    for r in db.execute(text("""
        SELECT f.follower_name, p.name, f.allocation, f.pnl
        FROM copy_followers f JOIN copy_providers p ON p.id=f.provider_id
        WHERE f.status='active' AND f.pnl IS NOT NULL ORDER BY f.pnl DESC LIMIT 6""")).fetchall():
        print(f"  {r[0]:18} copying {r[1]:20} ${float(r[2]):>8,.0f} alloc -> P/L ${float(r[3]):>10,.2f}")

def reset(db):
    ce.ensure_mirror_table(db)
    db.execute(text("DELETE FROM copy_mirror_orders WHERE source='loop'"))
    db.execute(text("DELETE FROM copy_provider_cursor"))
    db.execute(text("UPDATE copy_followers SET pnl=0 WHERE status='active'"))
    db.commit()
    print("reset: cleared loop mirror orders, cursors, and follower P/L.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=20)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        if a.reset:   reset(db); return
        if a.status:  show_status(db); return
        if a.loop:
            print(f"copy_loop DRY-RUN daemon (COPY_LIVE_ENABLED={ce.COPY_LIVE_ENABLED}) — interval {a.interval}s")
            while True:
                o, ap_, tp = cycle(db)
                print(f"  cycle: {o} mirror orders across {ap_}/{tp} providers")
                time.sleep(a.interval)
        else:  # default: one cycle
            o, ap_, tp = cycle(db)
            print(f"one cycle: {o} mirror orders across {ap_}/{tp} providers (DRY-RUN, COPY_LIVE_ENABLED={ce.COPY_LIVE_ENABLED})")
            show_status(db)
    finally:
        db.close()

if __name__ == "__main__":
    main()
