"""
Copy-trading enrichment — schema + computed fields for the production layer:
  • provider ACTIVITY  : last_trade_at + active flag (de-rank/hide stale providers)
  • follower SETTINGS  : copy_existing / max_lot / stop_equity_pct (risk controls)
  • provider EARNINGS  : performance fee (high-water mark) + per-lot copier commission
  • provider INTEGRITY : abuse flag overlay (reuse abuse_account_flags)

Idempotent. READ-ONLY on deals/abuse; only writes copy_* columns. Run after seeding/promoting:
  python copy_enrich.py
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from database import SessionLocal
from sqlalchemy import text

ACTIVE_WINDOW_DAYS = 14
PROVIDER_COMMISSION_PER_LOT = 3.0   # copier-volume rebate to the provider ($/lot) — IB-style

DDL = """
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS last_trade_at TIMESTAMP;
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS abuse_flag VARCHAR(40);
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS copy_existing VARCHAR(12) DEFAULT 'new';   -- new/all/skip_losing
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS max_lot NUMERIC;
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS stop_equity_pct NUMERIC;
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS peak_pnl NUMERIC DEFAULT 0;
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS perf_fee_earned NUMERIC DEFAULT 0;
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS commission_earned NUMERIC DEFAULT 0;
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS total_earned NUMERIC DEFAULT 0;
"""

def main():
    db = SessionLocal()
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            db.execute(text(stmt))
    db.commit()
    now = int(time.time())
    cutoff = now - ACTIVE_WINDOW_DAYS * 86400

    provs = db.execute(text("SELECT id, login, is_real FROM copy_providers")).fetchall()
    n_active = 0
    for pid, login, is_real in provs:
        # last trade time
        if login:  # real -> from deals (epoch deal_time)
            last = db.execute(text(
                "SELECT MAX(deal_time) FROM deals WHERE login=:l AND entry=1 AND action IN (0,1)"
            ), {"l": login}).scalar()
            last_epoch = int(last) if last else None
        else:      # demo -> from seeded trades
            last = db.execute(text(
                "SELECT EXTRACT(EPOCH FROM MAX(close_time)) FROM copy_provider_trades WHERE provider_id=:p"
            ), {"p": pid}).scalar()
            last_epoch = int(last) if last else None
        active = bool(last_epoch and last_epoch >= cutoff)
        if active: n_active += 1
        # high-water-mark fees: peak_pnl per follower, fee = fee_pct% * peak profit; commission per copier lot
        db.execute(text("""
            UPDATE copy_followers SET peak_pnl = GREATEST(COALESCE(peak_pnl,0), COALESCE(pnl,0))
            WHERE provider_id=:p AND status='active'
        """), {"p": pid})
        fee_pct = db.execute(text("SELECT fee_pct FROM copy_providers WHERE id=:p"), {"p": pid}).scalar() or 0
        profit_gen = db.execute(text(
            "SELECT COALESCE(SUM(GREATEST(peak_pnl,0)),0) FROM copy_followers WHERE provider_id=:p AND status='active'"
        ), {"p": pid}).scalar() or 0
        perf_fee = round(float(profit_gen) * float(fee_pct) / 100.0, 2)
        copier_lots = db.execute(text(
            "SELECT COALESCE(SUM(follower_lots),0) FROM copy_mirror_orders WHERE provider_id=:p"
        ), {"p": pid}).scalar() or 0
        commission = round(float(copier_lots) * PROVIDER_COMMISSION_PER_LOT, 2)
        total = round(perf_fee + commission, 2)
        # abuse overlay (worst open case for this login)
        abuse = None
        if login:
            abuse = db.execute(text(
                "SELECT abuse_type FROM abuse_account_flags WHERE login=:l ORDER BY severity DESC LIMIT 1"
            ), {"l": login}).scalar()
        db.execute(text("""
            UPDATE copy_providers SET last_trade_at = CASE WHEN :le IS NULL THEN NULL ELSE to_timestamp(:le) END,
              active=:act, perf_fee_earned=:pf, commission_earned=:cm, total_earned=:tot, abuse_flag=:ab
            WHERE id=:p
        """), {"le": last_epoch, "act": active, "pf": perf_fee, "cm": commission,
               "tot": total, "ab": abuse, "p": pid})
    db.commit()

    tot = db.execute(text("""SELECT COUNT(*) FILTER (WHERE active),
        COUNT(*) FILTER (WHERE NOT active), COALESCE(SUM(total_earned),0) FROM copy_providers""")).fetchone()
    print(f"providers: {tot[0]} active / {tot[1]} inactive | total provider earnings ${float(tot[2]):,.0f}")
    print("\nInactive real providers (stale — will be de-ranked/hidden):")
    for r in db.execute(text("""SELECT name, login, last_trade_at FROM copy_providers
        WHERE is_real=TRUE AND active=FALSE ORDER BY last_trade_at DESC NULLS LAST LIMIT 12""")).fetchall():
        print(f"  {r[0][:24]:24} #{r[1]}  last trade {str(r[2])[:10]}")
    print("\nTop earning providers:")
    for r in db.execute(text("""SELECT name, total_earned, perf_fee_earned, commission_earned, followers
        FROM copy_providers WHERE total_earned>0 ORDER BY total_earned DESC LIMIT 8""")).fetchall():
        print(f"  {r[0][:24]:24} total ${float(r[1]):>10,.0f}  (fee ${float(r[2]):,.0f} + comm ${float(r[3]):,.0f})  {r[4]} copiers")
    db.close()

if __name__ == "__main__":
    main()
