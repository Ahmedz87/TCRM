"""loyalty_router.py — API for the TN Point Program (loyalty)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import rbac

router = APIRouter(prefix="/loyalty", tags=["Loyalty"])

TIER_RATE = {"bronze": 4, "silver": 5, "gold": 6, "platinum": 7}
PROMO_STREAK = {"bronze": 30, "silver": 30, "gold": 40}
NEXT_TIER = {"bronze": "silver", "silver": "gold", "gold": "platinum", "platinum": None}
PASS_EARN_EVERY = 10   # mirror loyalty_engine constants for the UI
PASS_MAX = 4


@router.get("/stats")
def stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _scope = rbac.scope_agent_ids(db, current_user)
    sjoin = "JOIN clients c ON c.id = la.client_id" if _scope is not None else ""
    sw    = "WHERE c.assigned_agent_id = ANY(:aids)" if _scope is not None else ""
    sp    = {"aids": _scope} if _scope is not None else {}
    r = db.execute(text(f"""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE la.tier='bronze'),
               COUNT(*) FILTER (WHERE la.tier='silver'),
               COUNT(*) FILTER (WHERE la.tier='gold'),
               COUNT(*) FILTER (WHERE la.tier='platinum'),
               COALESCE(SUM(la.points_balance),0),
               COALESCE(SUM(la.lifetime_points),0)
        FROM loyalty_accounts la {sjoin} {sw}
    """), sp).fetchone()
    return {
        "members": r[0] or 0, "bronze": r[1] or 0, "silver": r[2] or 0,
        "gold": r[3] or 0, "platinum": r[4] or 0,
        "points_outstanding": float(r[5] or 0), "lifetime_points": float(r[6] or 0),
    }


@router.get("/leaderboard")
def leaderboard(limit: int = Query(50), search: str = Query(""),
                tier: str = Query("all"),
                db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    where = "WHERE 1=1"
    params = {"limit": limit}
    if tier != "all":
        where += " AND la.tier=:tier"; params["tier"] = tier
    if search:
        where += " AND (c.name ILIKE :s OR CAST(la.client_id AS TEXT) LIKE :s2)"
        params["s"] = f"%{search}%"; params["s2"] = f"%{search}%"
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        where += " AND c.assigned_agent_id = ANY(:aids)"
        params["aids"] = _scope
    rows = db.execute(text(f"""
        SELECT la.client_id, c.name, la.tier, la.points_balance,
               la.lifetime_points, la.current_streak, la.best_streak, la.last_trade_date, la.best_tier,
               la.pass_tokens, c.login
        FROM loyalty_accounts la
        LEFT JOIN clients c ON c.id = la.client_id
        {where}
        ORDER BY la.lifetime_points DESC
        LIMIT :limit
    """), params).fetchall()
    return {"members": [{
        "client_id": r[0], "name": r[1] or f"Client #{r[0]}", "country": "",
        "tier": r[2], "points_balance": float(r[3] or 0), "lifetime_points": float(r[4] or 0),
        "current_streak": r[5], "best_streak": r[6],
        "last_trade_date": str(r[7]) if r[7] else None,
        "best_tier": r[8] if len(r)>8 else r[2],
        "pass_tokens": r[9] if len(r)>9 and r[9] is not None else 0,
        # the client's TRADING LOGIN — the identifier the Clients page opens/filters by
        # (client_id here is the internal clients.id, NOT a login). See goToClient in Loyalty.tsx.
        "login": r[10] if len(r)>10 else None,
    } for r in rows]}


@router.get("/search")
def search(q: str = "", db: Session = Depends(get_db),
           current_user: models.User = Depends(get_current_user)):
    q = (q or "").strip()
    if len(q) < 2:
        return {"results": []}
    like = f"%{q}%"
    _scope = rbac.scope_agent_ids(db, current_user)
    sw = " AND c.assigned_agent_id = ANY(:aids)" if _scope is not None else ""
    sp = {"like": like}
    if _scope is not None:
        sp["aids"] = _scope
    rows = db.execute(text(f"""
        SELECT DISTINCT la.client_id, c.name, c.email, c.phone, la.tier, la.points_balance
        FROM loyalty_accounts la
        JOIN clients c ON c.id = la.client_id
        WHERE (c.name ILIKE :like OR c.email ILIKE :like OR c.phone ILIKE :like
              OR CAST(la.client_id AS TEXT) LIKE :like){sw}
        ORDER BY la.points_balance DESC
        LIMIT 20
    """), sp).fetchall()
    return {"results": [{
        "client_id": r[0],
        "name": r[1] or f"Client #{r[0]}",
        "email": r[2] or "",
        "phone": r[3] or "",
        "tier": r[4],
        "points": float(r[5] or 0),
    } for r in rows]}


@router.get("/member/{client_id}")
def member(client_id: int, db: Session = Depends(get_db),
           current_user: models.User = Depends(get_current_user)):
    a = db.execute(text("""
        SELECT la.client_id, c.name, la.tier, la.points_balance, la.lifetime_points,
               la.current_streak, la.best_streak, la.last_trade_date, la.referral_code, la.best_tier,
               la.pass_tokens, la.pass_days_used
        FROM loyalty_accounts la LEFT JOIN clients c ON c.id=la.client_id
        WHERE la.client_id=:id
    """), {"id": client_id}).fetchone()
    if not a:
        return {"error": "not found"}

    # Role-based visibility: only own/team clients' loyalty
    owner = db.execute(text("SELECT assigned_agent_id FROM clients WHERE id=:id"), {"id": client_id}).scalar()
    if not rbac.can_see_agent(db, current_user, owner):
        return {"error": "forbidden"}

    tier = a[2]
    streak = a[5]
    promo_needed = PROMO_STREAK.get(tier)
    nxt = NEXT_TIER.get(tier)
    streak_to_promo = max(0, promo_needed - streak) if promo_needed else None

    # inactivity countdown (days since last trade -> demotion at 30)
    import datetime
    days_inactive = None
    demote_in = None
    if a[7]:
        days_inactive = (datetime.date.today() - a[7]).days
        if tier != "bronze":
            demote_in = max(0, 30 - days_inactive)

    # recent ledger
    led = db.execute(text("""
        SELECT kind, points, lots, tier, symbol, trade_date
        FROM loyalty_ledger WHERE client_id=:id
        ORDER BY id DESC LIMIT 30
    """), {"id": client_id}).fetchall()

    # redemptions
    reds = db.execute(text("""
        SELECT reward_name, cost_points, status, created_at
        FROM loyalty_redemptions WHERE client_id=:id ORDER BY id DESC LIMIT 10
    """), {"id": client_id}).fetchall()

    # Days the client actually traded in the last ~60 days, for the ✓/✗ calendar. Sourced from the
    # LIVE deals feed — NOT loyalty_ledger, which is a periodic rebuild snapshot that lags the current
    # month, so active clients (live streak, last_trade_date=today) had 0 ledger rows this month and
    # the calendar rendered every day as ✗. deals.deal_time is epoch seconds (bigint). Same mapping
    # the loyalty engine uses: a deal's login -> this member via trading_accounts.client_id or clients.id.
    lrows = db.execute(text("""
        SELECT login FROM clients WHERE id=:id AND login IS NOT NULL
        UNION
        SELECT login FROM trading_accounts WHERE client_id=:id AND login IS NOT NULL
    """), {"id": client_id}).fetchall()
    logins = [r[0] for r in lrows]
    trade_days = []
    if logins:
        tdays = db.execute(text("""
            SELECT DISTINCT to_timestamp(d.deal_time)::date AS td
            FROM deals d
            WHERE d.login = ANY(:lg) AND d.entry=1 AND d.action IN (0,1)
              AND d.deal_time >= EXTRACT(EPOCH FROM (CURRENT_DATE - INTERVAL '60 days'))
        """), {"lg": logins}).fetchall()
        trade_days = [str(t[0]) for t in tdays if t[0]]

    return {
        "client_id": a[0], "name": a[1] or f"Client #{a[0]}", "country": "",
        "tier": tier, "tier_rate": TIER_RATE.get(tier, 4),
        "points_balance": float(a[3] or 0), "lifetime_points": float(a[4] or 0),
        "current_streak": streak, "best_streak": a[6],
        "next_tier": nxt, "streak_to_promotion": streak_to_promo,
        "promo_streak_needed": promo_needed,
        "last_trade_date": str(a[7]) if a[7] else None,
        "days_inactive": days_inactive, "demote_in_days": demote_in,
        "referral_code": a[8], "best_tier": a[9] if len(a)>9 else tier,
        "pass_tokens": a[10] if len(a)>10 and a[10] is not None else 0,
        "pass_days_used": a[11] if len(a)>11 and a[11] is not None else 0,
        "pass_max": PASS_MAX, "pass_earn_every": PASS_EARN_EVERY,
        "trade_days": trade_days,
        "ledger": [{"kind": l[0], "points": float(l[1] or 0), "lots": float(l[2] or 0),
                    "tier": l[3], "symbol": l[4], "date": str(l[5]) if l[5] else None} for l in led],
        "redemptions": [{"reward": r[0], "cost": float(r[1] or 0), "status": r[2],
                         "date": str(r[3])[:10] if r[3] else None} for r in reds],
    }


@router.get("/rewards")
def rewards(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT id, name, cost_points, category, description, active
        FROM loyalty_rewards WHERE active=TRUE ORDER BY sort_order, cost_points
    """)).fetchall()
    return {"rewards": [{"id": r[0], "name": r[1], "cost_points": float(r[2]),
                         "category": r[3], "description": r[4]} for r in rows]}


@router.post("/redeem")
def redeem(payload: dict, db: Session = Depends(get_db),
           current_user: models.User = Depends(get_current_user)):
    client_id = payload.get("client_id")
    reward_id = payload.get("reward_id")
    rw = db.execute(text("SELECT name, cost_points FROM loyalty_rewards WHERE id=:r"), {"r": reward_id}).fetchone()
    acc = db.execute(text("SELECT points_balance FROM loyalty_accounts WHERE client_id=:c"), {"c": client_id}).fetchone()
    if not rw or not acc:
        return {"error": "invalid reward or member"}
    cost = float(rw[1]); bal = float(acc[0])
    if bal < cost:
        return {"error": "insufficient points", "balance": bal, "needed": cost}
    db.execute(text("UPDATE loyalty_accounts SET points_balance=points_balance-:c, updated_at=NOW() WHERE client_id=:cid"),
               {"c": cost, "cid": client_id})
    db.execute(text("""INSERT INTO loyalty_redemptions (client_id, reward_id, reward_name, cost_points, status)
                       VALUES (:cid,:rid,:nm,:c,'pending')"""),
               {"cid": client_id, "rid": reward_id, "nm": rw[0], "c": cost})
    db.execute(text("""INSERT INTO loyalty_ledger (client_id, kind, points, ref)
                       VALUES (:cid,'redemption',:p,:ref)"""),
               {"cid": client_id, "p": -cost, "ref": rw[0]})
    db.commit()
    new_bal = bal - cost
    return {"ok": True, "reward": rw[0], "spent": cost, "new_balance": new_bal}


@router.post("/referral")
def referral(payload: dict, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    referrer = payload.get("referrer_client_id")
    referred_login = payload.get("referred_login")
    bonus = float(payload.get("bonus_points", 100))
    name = payload.get("referred_name", "")
    phone = payload.get("referred_phone", "")
    db.execute(text("""INSERT INTO loyalty_referrals
                       (referrer_client_id, referred_login, referred_name, referred_phone, bonus_points, status)
                       VALUES (:r,:l,:n,:p,:b,'invited')"""),
               {"r": referrer, "l": referred_login or 0, "n": name, "p": phone, "b": bonus})
    db.commit()
    return {"ok": True, "message": "Invite recorded", "bonus_points": bonus}


@router.get("/referrals/{client_id}")
def referrals(client_id: int, db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    # ensure optional columns exist (idempotent)
    try:
        db.execute(text("ALTER TABLE loyalty_referrals ADD COLUMN IF NOT EXISTS referred_name VARCHAR(120)"))
        db.execute(text("ALTER TABLE loyalty_referrals ADD COLUMN IF NOT EXISTS referred_phone VARCHAR(40)"))
        db.commit()
    except Exception:
        db.rollback()
    rows = db.execute(text("""
        SELECT id, referred_name, referred_phone, referred_login, bonus_points, status, created_at
        FROM loyalty_referrals WHERE referrer_client_id=:id ORDER BY id DESC LIMIT 50
    """), {"id": client_id}).fetchall()
    won = sum(1 for r in rows if r[5] == 'won')
    pending = sum(1 for r in rows if r[5] in ('invited','pending','pending_admin_review','registered','verified','funded'))
    return {
        "client_id": client_id,
        "summary": {"total": len(rows), "won": won, "pending": pending,
                    "points_earned": sum(float(r[4] or 0) for r in rows if r[5] == 'won')},
        "invites": [{"id": r[0], "name": r[1] or "—", "phone": r[2] or "", "login": r[3],
                     "bonus": float(r[4] or 0), "status": r[5],
                     "date": str(r[6])[:10] if r[6] else None} for r in rows],
    }
