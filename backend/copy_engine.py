"""
Copy-Trading replication engine.

Given a master/provider's trades, compute and (optionally) place the mirrored orders on
each active follower's account, sized by the follower's allocation / multiplier / copy_mode.

╔═══════════════════════════════════════════════════════════════════════════════════╗
║ SAFETY — READ BEFORE ENABLING LIVE                                                 ║
║ COPY_LIVE_ENABLED defaults to FALSE. While False, the engine is DRY-RUN: it writes ║
║ a `copy_mirror_orders` row describing each intended order with status='simulated'  ║
║ and NEVER calls the MT bridge. Going live requires:                                ║
║   1. a bridge OrderSend route (place_order_via_bridge below) implemented & tested, ║
║   2. providers linked to REAL MT logins (copy_providers.login),                    ║
║   3. a ONE-ACCOUNT live test first (per project SAFETY RULES),                     ║
║   4. flipping COPY_LIVE_ENABLED to True deliberately.                              ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
"""
import os
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

# Hard gate. Must be flipped deliberately (env COPY_LIVE_ENABLED=1) AND the bridge route wired.
COPY_LIVE_ENABLED = os.getenv("COPY_LIVE_ENABLED", "0") == "1"
BRIDGE_URL = os.getenv("COPY_BRIDGE_URL", "http://127.0.0.1:5000")

MASTER_BASE_CAPITAL = 10000.0   # provider's trading capital basis (seed equity)
MIN_LOT = 0.01
MAX_LOT = 50.0                  # hard cap per follower order (sanity)

MIRROR_DDL = """
CREATE TABLE IF NOT EXISTS copy_mirror_orders (
    id SERIAL PRIMARY KEY,
    provider_id INT, master_trade_id INT,
    follower_id INT, client_id INT, follower_login BIGINT,
    symbol VARCHAR(16), side VARCHAR(4),
    master_lots NUMERIC, follower_lots NUMERIC,
    copy_mode VARCHAR(16), multiplier NUMERIC, allocation NUMERIC,
    status VARCHAR(16) DEFAULT 'simulated',   -- simulated/sent/filled/rejected/skipped
    dry_run BOOLEAN DEFAULT TRUE,
    source VARCHAR(12) DEFAULT 'loop',         -- loop (daemon) / preview (admin one-off)
    pnl NUMERIC,                               -- computed copied P/L (dry-run)
    bridge_ref VARCHAR(64), error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
ALTER TABLE copy_mirror_orders ADD COLUMN IF NOT EXISTS source VARCHAR(12) DEFAULT 'loop';
ALTER TABLE copy_mirror_orders ADD COLUMN IF NOT EXISTS pnl NUMERIC;
CREATE INDEX IF NOT EXISTS ix_cmo_provider ON copy_mirror_orders (provider_id, created_at);
CREATE INDEX IF NOT EXISTS ix_cmo_client ON copy_mirror_orders (client_id);
CREATE INDEX IF NOT EXISTS ix_cmo_follower ON copy_mirror_orders (follower_id);

CREATE TABLE IF NOT EXISTS copy_provider_cursor (
    provider_id INT PRIMARY KEY,
    last_source_id BIGINT DEFAULT 0,
    processed INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- live lifecycle: one row per OPEN follower position, closed when the master closes
CREATE TABLE IF NOT EXISTS copy_positions (
    id SERIAL PRIMARY KEY,
    provider_id INT, follower_id INT, client_id INT, follower_login BIGINT,
    symbol VARCHAR(16), side VARCHAR(4), lots NUMERIC,
    master_open_id BIGINT, bridge_ref VARCHAR(64),
    status VARCHAR(12) DEFAULT 'open',      -- open/closed/error
    pnl NUMERIC, dry_run BOOLEAN DEFAULT TRUE,
    opened_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_cpos_follower ON copy_positions (follower_login, status);
CREATE INDEX IF NOT EXISTS ix_cpos_provider ON copy_positions (provider_id, status);
"""

def ensure_mirror_table(db: Session):
    for stmt in MIRROR_DDL.strip().split(";"):
        if stmt.strip():
            db.execute(text(stmt))
    db.commit()


def compute_follower_lots(master_lots: float, copy_mode: str, multiplier: float,
                          allocation: float, master_capital: float = MASTER_BASE_CAPITAL) -> float:
    """
    proportional : scale master size by the follower's share of the master's capital.
                   follower_lots = master_lots * (allocation / master_capital) * multiplier
    fixed        : ignore master size; trade a fixed lot = multiplier (acts as the lot size).
    mirror       : 1:1 copy of master size, scaled by multiplier.
    """
    m = max(master_lots or 0.0, 0.0)
    mult = multiplier if multiplier and multiplier > 0 else 1.0
    mode = (copy_mode or "proportional").lower()
    if mode == "fixed":
        lots = mult
    elif mode == "mirror":
        lots = m * mult
    else:  # proportional
        cap = master_capital if master_capital and master_capital > 0 else MASTER_BASE_CAPITAL
        lots = m * (max(allocation or 0.0, 0.0) / cap) * mult
    # round to 0.01, clamp
    lots = round(lots, 2)
    if lots < MIN_LOT:
        lots = MIN_LOT
    if lots > MAX_LOT:
        lots = MAX_LOT
    return lots


def place_order_via_bridge(follower_login: int, symbol: str, side: str, lots: float, dry: bool = False) -> dict:
    """
    LIVE order placement via the MT5 bridge /trade/open. GATED — only reached when
    COPY_LIVE_ENABLED is True. The bridge itself is independently gated (COPY_BRIDGE_TRADING +
    per-request dry + lots cap), so even here nothing fires unless every gate is open.
    """
    if not COPY_LIVE_ENABLED:
        raise RuntimeError("COPY_LIVE_ENABLED is False — live order placement is disabled.")
    r = requests.post(f"{BRIDGE_URL}/trade/open", timeout=12, json={
        "login": int(follower_login), "symbol": symbol, "side": (side or "").lower(),
        "lots": float(lots), "dry": dry})
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j.get("error") or f"bridge /trade/open failed ({r.status_code})")
    return {"ref": j.get("ref"), "dry": j.get("dry", True)}


def close_order_via_bridge(follower_login: int, symbol: str, dry: bool = False) -> dict:
    """Close a follower's open position on `symbol` via the bridge /trade/close (mirror of master close)."""
    if not COPY_LIVE_ENABLED:
        raise RuntimeError("COPY_LIVE_ENABLED is False — live close is disabled.")
    r = requests.post(f"{BRIDGE_URL}/trade/close", timeout=12, json={
        "login": int(follower_login), "symbol": symbol, "dry": dry})
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j.get("error") or f"bridge /trade/close failed ({r.status_code})")
    return {"ref": j.get("ref"), "dry": j.get("dry", True)}


def replicate_trade(db: Session, provider_id: int, master_trade: dict, dry_run: bool = True,
                    source: str = "loop") -> list:
    """
    Fan a single master trade out to every ACTIVE follower of the provider.
    If master_trade carries a 'pnl' + 'lots', each follower's copied P/L is computed
    (pnl_per_master_lot * follower_lots) and stored on the mirror order — this is what
    feeds the real 'My Copies' P/L in dry-run. Returns the computed mirror-order dicts.
    """
    followers = db.execute(text("""
        SELECT f.id, f.client_id, f.allocation, f.multiplier, f.copy_mode, c.login
        FROM copy_followers f
        LEFT JOIN clients c ON c.id = f.client_id
        WHERE f.provider_id = :p AND f.status = 'active'
    """), {"p": provider_id}).fetchall()

    m_lots = float(master_trade["lots"]) or 0.0
    m_pnl = master_trade.get("pnl")
    pnl_per_lot = (float(m_pnl) / m_lots) if (m_pnl is not None and m_lots > 0) else None
    live = (not dry_run) and COPY_LIVE_ENABLED
    out = []
    for f in followers:
        fid, client_id, allocation, mult, mode, flogin = f
        lots = compute_follower_lots(m_lots, mode, float(mult or 1), float(allocation or 0))
        f_pnl = round(pnl_per_lot * lots, 2) if pnl_per_lot is not None else None
        status, bridge_ref, err = "simulated", None, None
        if live:
            try:
                if flogin is None:
                    status, err = "skipped", "follower has no MT login"
                else:
                    res = place_order_via_bridge(flogin, master_trade["symbol"], master_trade["side"], lots)
                    status, bridge_ref = "sent", str(res.get("order") or res.get("ref") or "")
            except Exception as e:
                status, err = "rejected", str(e)[:300]
        db.execute(text("""
            INSERT INTO copy_mirror_orders
              (provider_id, master_trade_id, follower_id, client_id, follower_login,
               symbol, side, master_lots, follower_lots, copy_mode, multiplier, allocation,
               status, dry_run, source, pnl, bridge_ref, error)
            VALUES (:p,:mt,:fid,:cid,:fl,:sym,:sd,:ml,:flots,:cm,:mu,:al,:st,:dry,:src,:pnl,:ref,:err)
        """), {"p": provider_id, "mt": master_trade.get("id"), "fid": fid, "cid": client_id,
               "fl": flogin, "sym": master_trade["symbol"], "sd": master_trade["side"],
               "ml": m_lots, "flots": lots, "cm": mode, "mu": float(mult or 1),
               "al": float(allocation or 0), "st": status, "dry": not live, "src": source,
               "pnl": f_pnl, "ref": bridge_ref, "err": err})
        out.append({"follower_id": fid, "client_id": client_id, "follower_login": flogin,
                    "symbol": master_trade["symbol"], "side": master_trade["side"],
                    "master_lots": m_lots, "follower_lots": lots, "pnl": f_pnl,
                    "copy_mode": mode, "multiplier": float(mult or 1), "status": status, "error": err})
    db.commit()
    return out


def run_dry_run_cycle(db: Session, provider_id: int, n_trades: int = 5) -> dict:
    """
    DEMO/preview: take a provider's most-recent N trades and replicate each to all active
    followers in DRY-RUN (no MT orders). Idempotent — clears prior dry-run rows for this
    provider first. Returns a summary the admin UI can render.
    """
    ensure_mirror_table(db)
    # only clear our OWN preview rows — never disturb the daemon's 'loop' orders
    db.execute(text("DELETE FROM copy_mirror_orders WHERE provider_id=:p AND source='preview'"),
               {"p": provider_id})
    db.commit()
    trades = db.execute(text("""
        SELECT id, symbol, side, lots, pnl, close_time FROM copy_provider_trades
        WHERE provider_id=:p ORDER BY close_time DESC LIMIT :n
    """), {"p": provider_id, "n": n_trades}).fetchall()
    n_followers = db.execute(text(
        "SELECT COUNT(*) FROM copy_followers WHERE provider_id=:p AND status='active'"
    ), {"p": provider_id}).scalar()
    all_orders = []
    for t in trades:
        mt = {"id": t[0], "symbol": t[1], "side": t[2], "lots": float(t[3]), "pnl": float(t[4]) if t[4] is not None else None}
        all_orders.extend(replicate_trade(db, provider_id, mt, dry_run=True, source="preview"))
    return {
        "provider_id": provider_id, "dry_run": True, "live_enabled": COPY_LIVE_ENABLED,
        "master_trades": len(trades), "active_followers": int(n_followers or 0),
        "orders_generated": len(all_orders),
        "sample": all_orders[:25],
    }
