"""
Copy-trading production features (safe / no real money):
  • RISK ENFORCEMENT  — auto-close + stop a copy when its open loss hits stop_equity_pct; per-follower max_lot cap.
  • VETTING           — minimum track-record gate on apply; auto-suspend abuse-flagged providers.
  • FOLLOWER FEES      — what each copier owes the provider (fee_pct % of peak profit, high-water mark).
  • PAYOUTS            — settle provider earnings into a copy_payouts ledger (plugs into IB later).
  • NOTIFICATIONS      — client-scoped events (stop hit / provider inactive / provider flagged / copy started).
  • DISCLAIMER         — one-time risk-acknowledgment gate before a client can copy.

All DB-only / simulation. ensure_schema() is idempotent.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_APPLY_TRADES = 30        # provider applicants need a real track record
MIN_APPLY_DAYS = 7
MAX_LOT_HARD = 50.0

SCHEMA = """
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT FALSE;
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS stopped_reason VARCHAR(24);
ALTER TABLE copy_followers ADD COLUMN IF NOT EXISTS fee_accrued NUMERIC DEFAULT 0;
ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS copy_notifications (
    id SERIAL PRIMARY KEY, client_id INT, type VARCHAR(24), title TEXT, body TEXT,
    read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_cn_client ON copy_notifications (client_id, read, id);
CREATE TABLE IF NOT EXISTS copy_payouts (
    id SERIAL PRIMARY KEY, provider_id INT, kind VARCHAR(16), amount NUMERIC,
    status VARCHAR(16) DEFAULT 'pending', period_end DATE, created_at TIMESTAMP DEFAULT NOW(), paid_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS copy_acks (client_id INT PRIMARY KEY, accepted_at TIMESTAMP DEFAULT NOW());
"""

def ensure_schema(db: Session):
    for s in SCHEMA.strip().split(";"):
        if s.strip():
            db.execute(text(s))
    db.commit()

def notify(db: Session, client_id: int, ntype: str, title: str, body: str = ""):
    if not client_id:
        return
    db.execute(text("INSERT INTO copy_notifications (client_id,type,title,body) VALUES (:c,:t,:ti,:b)"),
               {"c": client_id, "t": ntype, "ti": title, "b": body})

# ───────────────────────── RISK ENFORCEMENT ─────────────────────────
def enforce_risk(db: Session) -> dict:
    """Close & stop copies whose open loss breached their stop_equity_pct. Returns a summary."""
    ensure_schema(db)
    rows = db.execute(text("""
        SELECT f.id, f.client_id, f.provider_id, f.allocation, f.stop_equity_pct, p.name,
               COALESCE((SELECT SUM(cp.pnl) FROM copy_positions cp
                         WHERE cp.follower_id=f.id AND cp.status='open'),0) AS open_pnl,
               (SELECT COUNT(*) FROM copy_positions cp WHERE cp.follower_id=f.id AND cp.status='open') AS n_open
        FROM copy_followers f JOIN copy_providers p ON p.id=f.provider_id
        WHERE f.status='active' AND f.stop_equity_pct IS NOT NULL AND f.allocation > 0
    """)).fetchall()
    stopped = 0
    for r in rows:
        fid, client_id, pid, alloc, stop_pct, pname, open_pnl, n_open = r
        if n_open == 0:
            continue
        loss_pct = (float(open_pnl) / float(alloc)) * 100.0   # negative when losing
        if loss_pct <= -abs(float(stop_pct)):
            db.execute(text("UPDATE copy_positions SET status='closed', closed_at=NOW() WHERE follower_id=:f AND status='open'"), {"f": fid})
            db.execute(text("UPDATE copy_followers SET status='stopped', stopped_reason='stop_loss' WHERE id=:f"), {"f": fid})
            db.execute(text("UPDATE copy_providers SET followers=GREATEST(followers-1,0) WHERE id=:p"), {"p": pid})
            notify(db, client_id, "stop_loss", f"Stop-loss hit on {pname}",
                   f"Your copy of {pname} hit your {abs(float(stop_pct)):.0f}% stop "
                   f"(open P/L {float(open_pnl):,.2f}). {n_open} position(s) closed and copying stopped.")
            stopped += 1
    db.commit()
    return {"checked": len(rows), "stopped": stopped}

def cap_to_max_lot(lots: float, max_lot) -> float:
    cap = float(max_lot) if max_lot not in (None, "", 0) else MAX_LOT_HARD
    return round(min(lots, cap), 2)

# ───────────────────────── VETTING ─────────────────────────
def vet_applicant(db: Session, client_id: int) -> tuple:
    """(ok, reason). Applicant must have a real track record on their own login."""
    login = db.execute(text("SELECT login FROM clients WHERE id=:c"), {"c": client_id}).scalar()
    if not login:
        return False, "No trading account is linked to your profile yet."
    row = db.execute(text("""
        SELECT COUNT(*), MIN(deal_time), MAX(deal_time)
        FROM deals WHERE login=:l AND entry=1 AND action IN (0,1)
    """), {"l": login}).fetchone()
    n = int(row[0] or 0)
    days = round(((int(row[2]) - int(row[1])) / 86400)) if (row[1] and row[2]) else 0
    if n < MIN_APPLY_TRADES:
        return False, f"You need at least {MIN_APPLY_TRADES} closed trades to apply (you have {n})."
    if days < MIN_APPLY_DAYS:
        return False, f"You need at least {MIN_APPLY_DAYS} days of trading history to apply."
    return True, f"Eligible — {n} trades over {days} days."

def auto_suspend_flagged(db: Session) -> int:
    """Suspend (hide from leaderboard) providers carrying an abuse flag; notify their copiers once."""
    ensure_schema(db)
    flagged = db.execute(text("""
        SELECT id, name FROM copy_providers
        WHERE abuse_flag IS NOT NULL AND COALESCE(suspended,FALSE)=FALSE
    """)).fetchall()
    for pid, name in flagged:
        db.execute(text("UPDATE copy_providers SET suspended=TRUE, active=FALSE WHERE id=:p"), {"p": pid})
        for (cid,) in db.execute(text("SELECT DISTINCT client_id FROM copy_followers WHERE provider_id=:p AND status='active' AND client_id IS NOT NULL"), {"p": pid}).fetchall():
            notify(db, cid, "provider_flagged", f"{name} was flagged for review",
                   "A provider you copy was suspended pending an integrity review. Consider stopping the copy.")
    db.commit()
    return len(flagged)

def notify_inactive_providers(db: Session) -> int:
    """One-time notice to copiers when a provider they follow goes inactive."""
    ensure_schema(db)
    pairs = db.execute(text("""
        SELECT DISTINCT f.client_id, p.id, p.name FROM copy_followers f
        JOIN copy_providers p ON p.id=f.provider_id
        WHERE f.status='active' AND f.client_id IS NOT NULL AND COALESCE(p.active,TRUE)=FALSE
          AND NOT EXISTS (SELECT 1 FROM copy_notifications n
                          WHERE n.client_id=f.client_id AND n.type='provider_inactive'
                            AND n.body LIKE '%' || p.name || '%')
    """)).fetchall()
    for cid, pid, name in pairs:
        notify(db, cid, "provider_inactive", f"{name} has gone inactive",
               f"{name} hasn't traded recently. Their copy is paused until they resume.")
    db.commit()
    return len(pairs)

# ───────────────────────── FOLLOWER FEE ─────────────────────────
def follower_fee_owed(db: Session, follower_id: int) -> float:
    r = db.execute(text("""
        SELECT p.fee_pct, GREATEST(COALESCE(f.peak_pnl,0),0)
        FROM copy_followers f JOIN copy_providers p ON p.id=f.provider_id WHERE f.id=:f
    """), {"f": follower_id}).fetchone()
    if not r:
        return 0.0
    return round(float(r[1]) * float(r[0] or 0) / 100.0, 2)

# ───────────────────────── PAYOUTS ─────────────────────────
def settle_payouts(db: Session) -> dict:
    """Snapshot each provider's earned fee+commission into copy_payouts as pending settlements."""
    ensure_schema(db)
    provs = db.execute(text("""
        SELECT id, perf_fee_earned, commission_earned FROM copy_providers
        WHERE COALESCE(total_earned,0) > 0
    """)).fetchall()
    created = 0
    for pid, fee, comm in provs:
        for kind, amt in (("perf_fee", float(fee or 0)), ("commission", float(comm or 0))):
            if amt <= 0:
                continue
            # only create a new pending row for the incremental (unsettled) amount
            settled = db.execute(text("SELECT COALESCE(SUM(amount),0) FROM copy_payouts WHERE provider_id=:p AND kind=:k"),
                                 {"p": pid, "k": kind}).scalar() or 0
            delta = round(amt - float(settled), 2)
            if delta > 0.5:
                db.execute(text("""INSERT INTO copy_payouts (provider_id,kind,amount,status,period_end)
                                   VALUES (:p,:k,:a,'pending',CURRENT_DATE)"""), {"p": pid, "k": kind, "a": delta})
                created += 1
    db.commit()
    return {"providers": len(provs), "payouts_created": created}
