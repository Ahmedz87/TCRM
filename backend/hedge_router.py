"""
hedge_router.py — API for the hedge-abuse detection tab.
Serves the flagged traders (ranked by score) and their hedge-trade evidence.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/hedge", tags=["Hedge Abuse"])


@router.get("/stats")
def hedge_stats(db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    r = db.execute(text("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE score>=75) AS critical,
          COUNT(*) FILTER (WHERE score>=60 AND score<75) AS high,
          COUNT(*) FILTER (WHERE score>=45 AND score<60) AS medium,
          COUNT(*) FILTER (WHERE has_bonus) AS with_bonus,
          COUNT(*) FILTER (WHERE strong_link) AS linked
        FROM hedge_flagged_traders
    """)).fetchone()
    return {
        "total": r[0] or 0, "critical": r[1] or 0, "high": r[2] or 0,
        "medium": r[3] or 0, "with_bonus": r[4] or 0, "linked": r[5] or 0,
    }


@router.get("/traders")
def hedge_traders(severity: str = Query("all"),
                  search: str = Query(""),
                  limit: int = Query(200),
                  db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    where = "WHERE 1=1"
    params = {"limit": limit}
    if severity == "critical":
        where += " AND f.score>=75"
    elif severity == "high":
        where += " AND f.score>=60 AND f.score<75"
    elif severity == "medium":
        where += " AND f.score>=45 AND f.score<60"
    elif severity == "bonus":
        where += " AND f.has_bonus"
    elif severity == "linked":
        where += " AND f.strong_link"
    if search:
        where += " AND CAST(f.login AS TEXT) LIKE :s"
        params["s"] = f"%{search}%"

    rows = db.execute(text(f"""
        SELECT f.login, f.score, f.hedged_ratio, f.total_positions, f.hedged_positions,
               f.hedged_volume_ratio, f.has_bonus, f.credit, f.strong_link, f.reasons,
               c.name, c.balance, c.country, c.total_deposits, c.total_withdrawals
        FROM hedge_flagged_traders f
        LEFT JOIN clients c ON c.login = f.login
        {where}
        ORDER BY f.score DESC
        LIMIT :limit
    """), params).fetchall()

    def sev(s):
        return "critical" if s>=75 else "high" if s>=60 else "medium"
    return {"traders": [{
        "login": r[0], "score": r[1], "severity": sev(r[1]),
        "hedged_ratio": float(r[2] or 0), "total_positions": r[3], "hedged_positions": r[4],
        "hedged_volume_ratio": float(r[5] or 0), "has_bonus": r[6], "credit": float(r[7] or 0),
        "strong_link": r[8], "reasons": r[9],
        "name": r[10] or f"#{r[0]}", "balance": float(r[11] or 0), "country": r[12] or "",
        "total_deposits": float(r[13] or 0), "total_withdrawals": float(r[14] or 0),
    } for r in rows]}


@router.get("/trader/{login}")
def hedge_trader_detail(login: int,
                        db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    f = db.execute(text("""
        SELECT f.login, f.score, f.hedged_ratio, f.total_positions, f.hedged_positions,
               f.hedged_volume_ratio, f.has_bonus, f.credit, f.strong_link, f.reasons,
               c.name, c.balance, c.country, c.total_deposits, c.total_withdrawals, c.is_islamic
        FROM hedge_flagged_traders f
        LEFT JOIN clients c ON c.login=f.login
        WHERE f.login=:l
    """), {"l": login}).fetchone()
    if not f:
        return {"error": "not found"}

    # the actual hedge trades: overlapping opposite positions for this login
    pairs = db.execute(text("""
        SELECT a.sym AS a_sym, a.direction AS a_dir, a.volume AS a_vol,
               a.open_time AS a_open, a.close_time AS a_close, a.profit AS a_profit,
               b.sym AS b_sym, b.direction AS b_dir, b.volume AS b_vol,
               b.open_time AS b_open, b.close_time AS b_close, b.profit AS b_profit,
               LEAST(a.close_time,b.close_time)-GREATEST(a.open_time,b.open_time) AS overlap,
               CASE WHEN a.sym=b.sym THEN 'same_symbol'
                    WHEN a.base=b.base THEN 'same_base'
                    ELSE 'same_quote' END AS relation
        FROM mt5_positions a
        JOIN mt5_positions b
          ON a.login=b.login AND a.position_id < b.position_id
         AND a.direction <> b.direction
         AND a.open_time <= b.close_time AND b.open_time <= a.close_time
         AND (a.sym=b.sym OR a.base=b.base OR (a.quote IS NOT NULL AND a.quote=b.quote))
        WHERE a.login=:l
        ORDER BY GREATEST(ABS(a.profit),ABS(b.profit)) DESC
        LIMIT 50
    """), {"l": login}).fetchall()

    # connections (how linked to other accounts)
    conns = db.execute(text("""
        SELECT CASE WHEN login_a=:l THEN login_b ELSE login_a END AS other, reason, value
        FROM network_edges
        WHERE (login_a=:l OR login_b=:l) AND reason IN ('ip','cid','mqid','family','ib')
        ORDER BY CASE reason WHEN 'cid' THEN 1 WHEN 'ip' THEN 2 WHEN 'mqid' THEN 3 ELSE 4 END
        LIMIT 30
    """), {"l": login}).fetchall()

    sev = "critical" if f[1]>=75 else "high" if f[1]>=60 else "medium"
    return {
        "login": f[0], "score": f[1], "severity": sev,
        "hedged_ratio": float(f[2] or 0), "total_positions": f[3], "hedged_positions": f[4],
        "hedged_volume_ratio": float(f[5] or 0), "has_bonus": f[6], "credit": float(f[7] or 0),
        "strong_link": f[8], "reasons": f[9],
        "name": f[10] or f"#{f[0]}", "balance": float(f[11] or 0), "country": f[12] or "",
        "total_deposits": float(f[13] or 0), "total_withdrawals": float(f[14] or 0),
        "is_islamic": bool(f[15]) if f[15] is not None else False,
        "recommendation": ("Freeze accounts & claw back bonus" if (f[1]>=75 and f[6])
                           else "Hold withdrawals & investigate" if f[1]>=60
                           else "Flag for monitoring"),
        "hedge_trades": [{
            "a_sym": p[0], "a_dir": p[1], "a_vol": float(p[2] or 0),
            "a_open": p[3], "a_close": p[4], "a_profit": float(p[5] or 0),
            "b_sym": p[6], "b_dir": p[7], "b_vol": float(p[8] or 0),
            "b_open": p[9], "b_close": p[10], "b_profit": float(p[11] or 0),
            "overlap_sec": p[12], "relation": p[13],
        } for p in pairs],
        "connections": [{"login": c[0], "reason": c[1], "value": c[2] or ""} for c in conns],
    }
