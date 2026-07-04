"""
Copy-Trading API — two routers:
  • portal_copy  (prefix /portal/copy)  — client-facing: leaderboard, provider profile,
                  follow / unfollow, my-following, apply-to-become-provider.
  • admin_copy   (prefix /copy)          — staff: oversight, approve/reject applications,
                  feature, program KPIs.  Auth via get_current_user (staff JWT).

SAFETY: NO live MT order placement here. Following a provider records an ALLOCATION /
subscription only (the auto-replication engine is a later, separately-gated phase).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
from portal_router import get_current_client
import copy_features as CF

portal_copy = APIRouter(prefix="/portal/copy", tags=["Copy Trading (client)"])
admin_copy = APIRouter(prefix="/copy", tags=["Copy Trading (admin)"])

SORTS = {
    "return": "return_pct DESC", "followers": "followers DESC", "risk": "risk_level ASC",
    "winrate": "win_rate DESC", "drawdown": "max_drawdown ASC", "new": "days_active ASC",
    "aum": "aum DESC",
}

def _prov_card(r) -> dict:
    return {
        "id": r.id, "name": r.name, "country": r.country, "avatar": r.avatar,
        "strategy": r.strategy, "markets": r.markets, "risk_level": r.risk_level,
        "return_pct": float(r.return_pct or 0), "return_30d": float(r.return_30d or 0),
        "win_rate": float(r.win_rate or 0), "max_drawdown": float(r.max_drawdown or 0),
        "profit_factor": float(r.profit_factor or 0), "total_trades": r.total_trades,
        "avg_hold_min": float(r.avg_hold_min or 0), "days_active": r.days_active,
        "followers": r.followers, "aum": float(r.aum or 0), "fee_pct": float(r.fee_pct or 0),
        "min_investment": float(r.min_investment or 0), "verified": bool(r.verified),
        "featured": bool(r.featured), "status": r.status,
        "is_real": bool(getattr(r, "is_real", False)), "login": r.login,
        "active": bool(getattr(r, "active", True)),
        "last_trade_at": str(getattr(r, "last_trade_at", "") or "")[:10],
        "abuse_flag": getattr(r, "abuse_flag", None),
        "total_earned": float(getattr(r, "total_earned", 0) or 0),
    }

# ───────────────────────── CLIENT: LEADERBOARD ─────────────────────────
@portal_copy.get("/providers")
def list_providers(
    sort: str = "return", strategy: str = None, market: str = None, risk_max: int = None,
    search: str = None, featured: bool = False, real_only: bool = False, active_only: bool = False,
    limit: int = 60, client_id: int = Depends(get_current_client), db: Session = Depends(get_db),
):
    where = ["status='approved'", "COALESCE(suspended,FALSE)=FALSE"]
    params = {}
    if strategy: where.append("strategy = :st"); params["st"] = strategy
    if market:   where.append("markets ILIKE :mk"); params["mk"] = f"%{market}%"
    if risk_max: where.append("risk_level <= :rk"); params["rk"] = risk_max
    if search:   where.append("name ILIKE :se"); params["se"] = f"%{search}%"
    if featured: where.append("featured = TRUE")
    if real_only: where.append("COALESCE(is_real,FALSE) = TRUE")
    if active_only: where.append("COALESCE(active,TRUE) = TRUE")
    order = SORTS.get(sort, SORTS["return"])
    # always float active providers above inactive ones, then apply the chosen sort
    rows = db.execute(text(f"""
        SELECT * FROM copy_providers WHERE {' AND '.join(where)}
        ORDER BY COALESCE(active,TRUE) DESC, {order} NULLS LAST LIMIT :lim
    """), {**params, "lim": min(limit, 100)}).fetchall()
    # which providers does this client already follow?
    following = {r[0] for r in db.execute(text(
        "SELECT DISTINCT provider_id FROM copy_followers WHERE client_id=:c AND status='active'"
    ), {"c": client_id}).fetchall()}
    out = []
    for r in rows:
        card = _prov_card(r)
        card["following"] = r.id in following
        out.append(card)
    # filter chips
    strategies = [x[0] for x in db.execute(text(
        "SELECT DISTINCT strategy FROM copy_providers WHERE status='approved' ORDER BY 1")).fetchall()]
    return {"providers": out, "count": len(out), "strategies": strategies}

# ───────────────────────── CLIENT: PROVIDER DETAIL ─────────────────────────
@portal_copy.get("/providers/{pid}")
def provider_detail(pid: int, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    r = db.execute(text("SELECT * FROM copy_providers WHERE id=:p"), {"p": pid}).fetchone()
    if not r:
        raise HTTPException(404, "Provider not found")
    hist = db.execute(text(
        "SELECT day, equity, return_pct FROM copy_provider_history WHERE provider_id=:p ORDER BY day"
    ), {"p": pid}).fetchall()
    trades = db.execute(text("""
        SELECT symbol, side, lots, open_time, close_time, hold_min, pnl, pips
        FROM copy_provider_trades WHERE provider_id=:p ORDER BY close_time DESC LIMIT 40
    """), {"p": pid}).fetchall()
    foll = db.execute(text("""
        SELECT follower_name, allocation, pnl, started_at FROM copy_followers
        WHERE provider_id=:p ORDER BY started_at DESC LIMIT 12
    """), {"p": pid}).fetchall()
    mine = db.execute(text("""
        SELECT id, allocation, multiplier, copy_mode, pnl, started_at FROM copy_followers
        WHERE provider_id=:p AND client_id=:c AND status='active' LIMIT 1
    """), {"p": pid, "c": client_id}).fetchone()
    card = _prov_card(r)
    card.update({
        "bio": r.bio,
        "equity_curve": [{"day": str(h[0]), "equity": float(h[1]), "return_pct": float(h[2])} for h in hist],
        "recent_trades": [{
            "symbol": t[0], "side": t[1], "lots": float(t[2]),
            "open_time": str(t[3])[:16], "close_time": str(t[4])[:16],
            "hold_min": t[5], "pnl": float(t[6]), "pips": float(t[7]),
        } for t in trades],
        "recent_followers": [{
            "name": f[0], "allocation": float(f[1]), "pnl": float(f[2] or 0), "since": str(f[3])[:10],
        } for f in foll],
        "i_follow": ({
            "allocation": float(mine[1]), "multiplier": float(mine[2]),
            "copy_mode": mine[3], "pnl": float(mine[4] or 0), "since": str(mine[5])[:10],
        } if mine else None),
    })
    return card

# ───────────────────────── CLIENT: FOLLOW / UNFOLLOW ─────────────────────────
@portal_copy.post("/follow")
def follow(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    pid = payload.get("provider_id")
    allocation = float(payload.get("allocation") or 0)
    multiplier = float(payload.get("multiplier") or 1.0)
    copy_mode = (payload.get("copy_mode") or "proportional").strip()
    copy_existing = (payload.get("copy_existing") or "new").strip()        # new/all/skip_losing
    if copy_existing not in ("new", "all", "skip_losing"): copy_existing = "new"
    max_lot = payload.get("max_lot")
    stop_equity_pct = payload.get("stop_equity_pct")
    is_demo = bool(payload.get("is_demo", False))
    # RISK DISCLAIMER gate — client must have accepted once before copying
    CF.ensure_schema(db)
    if not is_demo:
        acked = db.execute(text("SELECT 1 FROM copy_acks WHERE client_id=:c"), {"c": client_id}).fetchone()
        if not acked:
            raise HTTPException(status_code=412, detail="disclaimer_required")
    prov = db.execute(text("SELECT min_investment, name FROM copy_providers WHERE id=:p AND status='approved'"),
                      {"p": pid}).fetchone()
    if not prov:
        raise HTTPException(404, "Provider not available")
    if allocation < float(prov[0] or 0):
        raise HTTPException(400, f"Minimum investment for {prov[1]} is ${float(prov[0] or 0):,.0f}")
    # one active subscription per (client, provider)
    existing = db.execute(text(
        "SELECT id FROM copy_followers WHERE client_id=:c AND provider_id=:p AND status='active'"
    ), {"c": client_id, "p": pid}).fetchone()
    cname = db.execute(text("SELECT name FROM clients WHERE id=:c"), {"c": client_id}).scalar()
    sett = {"a": allocation, "m": multiplier, "cm": copy_mode, "ce": copy_existing,
            "ml": max_lot, "se": stop_equity_pct, "dm": is_demo}
    if existing:
        db.execute(text("""UPDATE copy_followers SET allocation=:a, multiplier=:m, copy_mode=:cm,
            copy_existing=:ce, max_lot=:ml, stop_equity_pct=:se, is_demo=:dm WHERE id=:id"""),
            {**sett, "id": existing[0]})
    else:
        fid = db.execute(text("""INSERT INTO copy_followers
            (provider_id,client_id,follower_name,allocation,multiplier,copy_mode,copy_existing,
             max_lot,stop_equity_pct,is_demo,status,pnl)
            VALUES (:p,:c,:n,:a,:m,:cm,:ce,:ml,:se,:dm,'active',0) RETURNING id"""),
            {**sett, "p": pid, "c": client_id, "n": cname or f"Client #{client_id}"}).scalar()
        db.execute(text("UPDATE copy_providers SET followers=followers+1 WHERE id=:p"), {"p": pid})
        # snapshot their currently-open positions as copied positions (simulation), capped by max_lot
        if copy_existing != "new":
            _snapshot_positions(db, pid, fid, client_id, allocation, multiplier, copy_mode, copy_existing, max_lot)
        CF.notify(db, client_id, "copy_started", f"Started copying {prov[1]}",
                  f"You're now copying {prov[1]} with ${allocation:,.0f}" + (" (demo)" if is_demo else "") + ".")
    db.commit()
    existed_note = "Copying their currently-open positions. " if copy_existing != "new" else "Copying new trades only. "
    return {"ok": True, "simulation": True,
            "message": f"Now copying {prov[1]} with ${allocation:,.0f}. {existed_note}(Positions are recorded; live execution activates in a later release — no orders placed yet.)"}

# ── Provider's CURRENT open positions (live from the bridge for real providers) ──
def _get_open_positions(db: Session, pid: int):
    login = db.execute(text("SELECT login FROM copy_providers WHERE id=:p"), {"p": pid}).scalar()
    if login:
        try:
            import requests as _rq
            r = _rq.get(f"http://127.0.0.1:5000/positions/{login}", timeout=6)
            if r.status_code == 200:
                return r.json().get("positions", []), "live"
        except Exception:
            pass
    # fallback: infer "open" from the most recent trades (bridge route inactive until restart)
    rows = db.execute(text("""
        SELECT symbol, side, lots, pnl, close_time FROM copy_provider_trades
        WHERE provider_id=:p ORDER BY close_time DESC LIMIT 4
    """), {"p": pid}).fetchall()
    return [{"symbol": r[0], "side": r[1], "lots": float(r[2]), "profit": float(r[3] or 0),
             "open_time": str(r[4])[:16]} for r in rows], "recent"

@portal_copy.get("/providers/{pid}/open-positions")
def provider_open_positions(pid: int, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    positions, source = _get_open_positions(db, pid)
    return {"positions": positions, "source": source}

# ── snapshot a provider's open positions into the follower's copied positions ──
def _snapshot_positions(db: Session, pid: int, follower_id: int, client_id: int,
                        allocation: float, multiplier: float, copy_mode: str, copy_existing: str,
                        max_lot=None):
    from copy_engine import compute_follower_lots, ensure_mirror_table
    ensure_mirror_table(db)
    positions, _src = _get_open_positions(db, pid)
    flogin = db.execute(text("SELECT login FROM clients WHERE id=:c"), {"c": client_id}).scalar()
    n = 0
    for p in positions:
        if copy_existing == "skip_losing" and float(p.get("profit", 0)) < 0:
            continue
        m_lots = float(p.get("lots", 0)) or 0.0
        f_lots = CF.cap_to_max_lot(compute_follower_lots(m_lots, copy_mode, multiplier, allocation), max_lot)
        proj_pnl = round(float(p.get("profit", 0)) * (f_lots / m_lots), 2) if m_lots > 0 else 0.0
        db.execute(text("""INSERT INTO copy_positions
            (provider_id,follower_id,client_id,follower_login,symbol,side,lots,master_open_id,
             status,pnl,dry_run)
            VALUES (:p,:fid,:c,:fl,:sym,:sd,:l,NULL,'open',:pnl,TRUE)"""),
            {"p": pid, "fid": follower_id, "c": client_id, "fl": flogin,
             "sym": p.get("symbol", ""), "sd": p.get("side", ""), "l": f_lots, "pnl": proj_pnl})
        n += 1
    return n

@portal_copy.post("/unfollow")
def unfollow(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """Disconnect a provider. close_positions=True closes the copied open positions;
    False leaves them open (the ZuluTrade keep-or-close choice)."""
    pid = payload.get("provider_id")
    close_positions = bool(payload.get("close_positions", False))
    res = db.execute(text(
        "UPDATE copy_followers SET status='stopped' WHERE client_id=:c AND provider_id=:p AND status='active'"
    ), {"c": client_id, "p": pid})
    if res.rowcount:
        db.execute(text("UPDATE copy_providers SET followers=GREATEST(followers-1,0) WHERE id=:p"), {"p": pid})
    closed = 0
    if close_positions:
        cr = db.execute(text("""UPDATE copy_positions SET status='closed', closed_at=NOW()
            WHERE client_id=:c AND provider_id=:p AND status='open'"""), {"c": client_id, "p": pid})
        closed = cr.rowcount
    db.commit()
    return {"ok": True, "stopped": res.rowcount, "positions_closed": closed,
            "positions_kept": (not close_positions)}

# ── follower's COPIED OPEN TRADES (across all providers) — table for My Copies ──
@portal_copy.get("/my-open-trades")
def my_open_trades(provider_id: int = None, symbol: str = None,
                   client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    where = ["cp.client_id=:c", "cp.status='open'"]
    params = {"c": client_id}
    if provider_id: where.append("cp.provider_id=:pid"); params["pid"] = provider_id
    if symbol:      where.append("cp.symbol=:sym"); params["sym"] = symbol
    rows = db.execute(text(f"""
        SELECT cp.id, cp.provider_id, p.name, p.avatar, cp.symbol, cp.side, cp.lots, cp.pnl, cp.opened_at
        FROM copy_positions cp JOIN copy_providers p ON p.id = cp.provider_id
        WHERE {' AND '.join(where)} ORDER BY cp.opened_at DESC
    """), params).fetchall()
    trades = [{
        "id": r[0], "provider_id": r[1], "provider": r[2], "avatar": r[3],
        "symbol": r[4], "side": r[5], "lots": float(r[6] or 0), "pnl": float(r[7] or 0),
        "opened_at": str(r[8])[:16],
    } for r in rows]
    # filter options
    provs = db.execute(text("""SELECT DISTINCT p.id, p.name FROM copy_positions cp
        JOIN copy_providers p ON p.id=cp.provider_id WHERE cp.client_id=:c AND cp.status='open' ORDER BY p.name"""),
        {"c": client_id}).fetchall()
    syms = db.execute(text("SELECT DISTINCT symbol FROM copy_positions WHERE client_id=:c AND status='open' ORDER BY symbol"),
                      {"c": client_id}).fetchall()
    return {"trades": trades, "providers": [{"id": p[0], "name": p[1]} for p in provs],
            "symbols": [s[0] for s in syms],
            "total_pnl": round(sum(t["pnl"] for t in trades), 2)}

@portal_copy.post("/positions/{position_id}/close")
def close_position(position_id: int, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    """Manually close one copied open trade (verifies ownership)."""
    r = db.execute(text("""UPDATE copy_positions SET status='closed', closed_at=NOW()
        WHERE id=:id AND client_id=:c AND status='open'"""), {"id": position_id, "c": client_id})
    db.commit()
    if not r.rowcount:
        raise HTTPException(404, "Position not found")
    return {"ok": True, "closed": r.rowcount}

@portal_copy.get("/my-following")
def my_following(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT p.id, p.name, p.avatar, p.strategy, p.markets, p.return_pct, p.win_rate,
               p.risk_level, f.allocation, f.multiplier, f.copy_mode, f.pnl, f.started_at, f.copy_existing,
               (SELECT COUNT(*) FROM copy_positions cp WHERE cp.client_id=f.client_id
                  AND cp.provider_id=p.id AND cp.status='open') AS open_trades
        FROM copy_followers f JOIN copy_providers p ON p.id = f.provider_id
        WHERE f.client_id=:c AND f.status='active'
        ORDER BY f.started_at DESC
    """), {"c": client_id}).fetchall()
    fee_rows = db.execute(text("""
        SELECT f.provider_id, p.fee_pct, GREATEST(COALESCE(f.peak_pnl,0),0)
        FROM copy_followers f JOIN copy_providers p ON p.id=f.provider_id
        WHERE f.client_id=:c AND f.status='active'
    """), {"c": client_id}).fetchall()
    fee_by_prov = {fr[0]: round(float(fr[2]) * float(fr[1] or 0) / 100.0, 2) for fr in fee_rows}
    items = [{
        "provider_id": r[0], "name": r[1], "avatar": r[2], "strategy": r[3], "markets": r[4],
        "return_pct": float(r[5] or 0), "win_rate": float(r[6] or 0), "risk_level": r[7],
        "allocation": float(r[8] or 0), "multiplier": float(r[9] or 1), "copy_mode": r[10],
        "pnl": float(r[11] or 0), "since": str(r[12])[:10], "copy_existing": r[13] or "new",
        "open_trades": int(r[14] or 0), "fee_owed": fee_by_prov.get(r[0], 0.0),
    } for r in rows]
    return {
        "following": items,
        "totals": {
            "count": len(items),
            "allocated": round(sum(i["allocation"] for i in items), 2),
            "pnl": round(sum(i["pnl"] for i in items), 2),
        },
    }

# ───────────────────────── CLIENT: BECOME A PROVIDER ─────────────────────────
@portal_copy.get("/my-provider")
def my_provider(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    r = db.execute(text("SELECT * FROM copy_providers WHERE client_id=:c ORDER BY id DESC LIMIT 1"),
                   {"c": client_id}).fetchone()
    if not r:
        return {"application": None}
    card = _prov_card(r)
    card["earnings"] = {
        "perf_fee": float(getattr(r, "perf_fee_earned", 0) or 0),
        "commission": float(getattr(r, "commission_earned", 0) or 0),
        "total": float(getattr(r, "total_earned", 0) or 0),
        "fee_pct": float(r.fee_pct or 0),
    }
    return {"application": card}

@portal_copy.post("/apply")
def apply_provider(payload: dict, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    existing = db.execute(text(
        "SELECT id, status FROM copy_providers WHERE client_id=:c ORDER BY id DESC LIMIT 1"
    ), {"c": client_id}).fetchone()
    if existing and existing[1] in ("pending", "approved"):
        raise HTTPException(400, f"You already have a {existing[1]} provider profile.")
    # VETTING: require a real track record before applying
    ok, reason = CF.vet_applicant(db, client_id)
    if not ok:
        raise HTTPException(400, reason)
    c = db.execute(text("SELECT name, country, login FROM clients WHERE id=:c"), {"c": client_id}).fetchone()
    strategy = (payload.get("strategy") or "Intraday").strip()
    markets = (payload.get("markets") or "FX Majors").strip()
    bio = (payload.get("bio") or "").strip()[:500]
    fee = float(payload.get("fee_pct") or 20)
    min_inv = float(payload.get("min_investment") or 250)
    risk = int(payload.get("risk_level") or 5)
    db.execute(text("""INSERT INTO copy_providers
        (name,country,avatar,strategy,markets,risk_level,bio,fee_pct,min_investment,
         status,client_id,login,days_active,start_date,return_pct,return_30d,win_rate,
         max_drawdown,profit_factor,total_trades,avg_hold_min,followers,aum,pnl_total,
         verified,featured)
        VALUES (:n,:co,'📊',:st,:mk,:rk,:bio,:fee,:min,'pending',:c,:lg,0,CURRENT_DATE,
         0,0,0,0,0,0,0,0,0,0,FALSE,FALSE)"""),
        {"n": c[0] or f"Client #{client_id}", "co": c[1] or "", "st": strategy, "mk": markets,
         "rk": risk, "bio": bio, "fee": fee, "min": min_inv, "c": client_id, "lg": c[2]})
    db.commit()
    return {"ok": True, "message": "Application submitted. Our team will review your trading history and approve you as a signal provider."}

@portal_copy.get("/eligibility")
def apply_eligibility(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    ok, reason = CF.vet_applicant(db, client_id)
    return {"eligible": ok, "reason": reason}

# ───────────────────────── RISK DISCLAIMER ─────────────────────────
@portal_copy.get("/disclaimer")
def disclaimer_status(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    CF.ensure_schema(db)
    acked = db.execute(text("SELECT accepted_at FROM copy_acks WHERE client_id=:c"), {"c": client_id}).fetchone()
    return {"accepted": bool(acked), "accepted_at": str(acked[0])[:16] if acked else None}

@portal_copy.post("/disclaimer/accept")
def disclaimer_accept(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    CF.ensure_schema(db)
    db.execute(text("INSERT INTO copy_acks (client_id) VALUES (:c) ON CONFLICT (client_id) DO NOTHING"), {"c": client_id})
    db.commit()
    return {"ok": True}

# ───────────────────────── NOTIFICATIONS ─────────────────────────
@portal_copy.get("/notifications")
def list_notifications(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    CF.ensure_schema(db)
    rows = db.execute(text("""
        SELECT id, type, title, body, read, created_at FROM copy_notifications
        WHERE client_id=:c ORDER BY id DESC LIMIT 40
    """), {"c": client_id}).fetchall()
    return {"notifications": [{
        "id": r[0], "type": r[1], "title": r[2], "body": r[3], "read": bool(r[4]),
        "at": str(r[5])[:16],
    } for r in rows], "unread": sum(1 for r in rows if not r[4])}

@portal_copy.post("/notifications/read")
def mark_notifications_read(payload: dict = None, client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    CF.ensure_schema(db)
    db.execute(text("UPDATE copy_notifications SET read=TRUE WHERE client_id=:c AND read=FALSE"), {"c": client_id})
    db.commit()
    return {"ok": True}

# ───────────────────────── PROVIDER DASHBOARD (for an approved provider) ──────────
@portal_copy.get("/provider-dashboard")
def provider_dashboard(client_id: int = Depends(get_current_client), db: Session = Depends(get_db)):
    p = db.execute(text("SELECT id, name, fee_pct, perf_fee_earned, commission_earned, total_earned, followers, aum FROM copy_providers WHERE client_id=:c AND status='approved' ORDER BY id DESC LIMIT 1"),
                   {"c": client_id}).fetchone()
    if not p:
        return {"provider": None}
    pid = p[0]
    copiers = db.execute(text("""
        SELECT follower_name, allocation, pnl, started_at, status FROM copy_followers
        WHERE provider_id=:p ORDER BY allocation DESC LIMIT 50
    """), {"p": pid}).fetchall()
    payouts = db.execute(text("""
        SELECT kind, amount, status, created_at FROM copy_payouts WHERE provider_id=:p ORDER BY id DESC LIMIT 20
    """), {"p": pid}).fetchall()
    return {"provider": {
        "name": p[1], "fee_pct": float(p[2] or 0),
        "perf_fee": float(p[3] or 0), "commission": float(p[4] or 0), "total_earned": float(p[5] or 0),
        "followers": p[6], "aum": float(p[7] or 0),
        "copiers": [{"name": c[0], "allocation": float(c[1] or 0), "pnl": float(c[2] or 0),
                     "since": str(c[3])[:10], "status": c[4]} for c in copiers],
        "payouts": [{"kind": p_[0], "amount": float(p_[1] or 0), "status": p_[2], "at": str(p_[3])[:10]} for p_ in payouts],
    }}

# ═════════════════════════ ADMIN ═════════════════════════
@admin_copy.get("/admin/providers")
def admin_providers(status: str = None, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    where = "WHERE status=:s" if status else ""
    rows = db.execute(text(f"""
        SELECT * FROM copy_providers {where}
        ORDER BY (status='pending') DESC, return_pct DESC NULLS LAST
    """), ({"s": status} if status else {})).fetchall()
    return {"providers": [{**_prov_card(r), "client_id": r.client_id, "login": r.login,
                           "aum": float(r.aum or 0), "pnl_total": float(r.pnl_total or 0),
                           "perf_fee_earned": float(getattr(r, "perf_fee_earned", 0) or 0),
                           "commission_earned": float(getattr(r, "commission_earned", 0) or 0)} for r in rows]}

@admin_copy.get("/admin/stats")
def admin_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    s = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE status='approved'),
               COUNT(*) FILTER (WHERE status='pending'),
               COALESCE(SUM(followers),0), COALESCE(SUM(aum),0),
               COALESCE(AVG(return_pct) FILTER (WHERE status='approved'),0)
        FROM copy_providers
    """)).fetchone()
    active_followers = db.execute(text("SELECT COUNT(*) FROM copy_followers WHERE status='active'")).scalar()
    real_followers = db.execute(text("SELECT COUNT(*) FROM copy_followers WHERE status='active' AND client_id IS NOT NULL")).scalar()
    extra = db.execute(text("""SELECT COUNT(*) FILTER (WHERE COALESCE(active,TRUE)),
        COUNT(*) FILTER (WHERE NOT COALESCE(active,TRUE)),
        COUNT(*) FILTER (WHERE COALESCE(is_real,FALSE)),
        COALESCE(SUM(total_earned),0) FROM copy_providers WHERE status='approved'""")).fetchone()
    return {"approved": s[0], "pending": s[1], "total_followers": int(s[2]),
            "total_aum": float(s[3]), "avg_return": round(float(s[4]), 1),
            "follower_subscriptions": active_followers, "real_client_followers": real_followers,
            "active_providers": int(extra[0]), "inactive_providers": int(extra[1]),
            "real_providers": int(extra[2]), "provider_earnings": float(extra[3])}

@admin_copy.get("/admin/payouts")
def admin_payouts(status: str = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    CF.ensure_schema(db)
    where = "WHERE po.status=:s" if status else ""
    rows = db.execute(text(f"""
        SELECT po.id, po.provider_id, p.name, po.kind, po.amount, po.status, po.created_at, po.paid_at
        FROM copy_payouts po JOIN copy_providers p ON p.id=po.provider_id {where}
        ORDER BY (po.status='pending') DESC, po.id DESC
    """), ({"s": status} if status else {})).fetchall()
    tot = db.execute(text("SELECT COALESCE(SUM(amount) FILTER (WHERE status='pending'),0), COALESCE(SUM(amount) FILTER (WHERE status='paid'),0) FROM copy_payouts")).fetchone()
    return {"payouts": [{"id": r[0], "provider_id": r[1], "provider": r[2], "kind": r[3],
                         "amount": float(r[4] or 0), "status": r[5], "created_at": str(r[6])[:10],
                         "paid_at": str(r[7])[:10] if r[7] else None} for r in rows],
            "pending_total": float(tot[0]), "paid_total": float(tot[1])}

@admin_copy.post("/admin/payouts/settle")
def admin_payouts_settle(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return CF.settle_payouts(db)

@admin_copy.post("/admin/payouts/{payout_id}/pay")
def admin_pay(payout_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("UPDATE copy_payouts SET status='paid', paid_at=NOW() WHERE id=:i"), {"i": payout_id}); db.commit()
    return {"ok": True}

@admin_copy.post("/admin/maintenance")
def admin_maintenance(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Run the safety sweeps: enforce stops, suspend flagged providers, notify inactive, settle payouts."""
    return {"risk": CF.enforce_risk(db), "suspended": CF.auto_suspend_flagged(db),
            "inactive_notices": CF.notify_inactive_providers(db), "payouts": CF.settle_payouts(db)}

@admin_copy.post("/admin/providers/{pid}/approve")
def approve(pid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("UPDATE copy_providers SET status='approved' WHERE id=:p"), {"p": pid}); db.commit()
    return {"ok": True}

@admin_copy.post("/admin/providers/{pid}/reject")
def reject(pid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("UPDATE copy_providers SET status='rejected' WHERE id=:p"), {"p": pid}); db.commit()
    return {"ok": True}

@admin_copy.post("/admin/providers/{pid}/feature")
def feature(pid: int, payload: dict = None, db: Session = Depends(get_db),
            current_user: models.User = Depends(get_current_user)):
    val = bool((payload or {}).get("featured", True))
    db.execute(text("UPDATE copy_providers SET featured=:f WHERE id=:p"), {"f": val, "p": pid}); db.commit()
    return {"ok": True, "featured": val}

# ── Replication engine (DRY-RUN only; live is gated in copy_engine.COPY_LIVE_ENABLED) ──
@admin_copy.post("/admin/replicate/dry-run")
def replicate_dry_run(payload: dict, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    from copy_engine import run_dry_run_cycle
    pid = int(payload.get("provider_id") or 0)
    n = int(payload.get("n_trades") or 5)
    if not pid:
        raise HTTPException(400, "provider_id required")
    return run_dry_run_cycle(db, pid, n)

@admin_copy.get("/admin/mirror-orders")
def mirror_orders(provider_id: int = None, limit: int = 100, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    from copy_engine import ensure_mirror_table
    ensure_mirror_table(db)
    where = "WHERE provider_id=:p" if provider_id else ""
    rows = db.execute(text(f"""
        SELECT id, provider_id, follower_id, client_id, follower_login, symbol, side,
               master_lots, follower_lots, copy_mode, multiplier, allocation, status, dry_run, created_at
        FROM copy_mirror_orders {where} ORDER BY id DESC LIMIT :lim
    """), ({"p": provider_id, "lim": limit} if provider_id else {"lim": limit})).fetchall()
    return {"orders": [{
        "id": r[0], "provider_id": r[1], "follower_id": r[2], "client_id": r[3],
        "follower_login": r[4], "symbol": r[5], "side": r[6],
        "master_lots": float(r[7] or 0), "follower_lots": float(r[8] or 0),
        "copy_mode": r[9], "multiplier": float(r[10] or 1), "allocation": float(r[11] or 0),
        "status": r[12], "dry_run": bool(r[13]), "created_at": str(r[14])[:19],
    } for r in rows]}
