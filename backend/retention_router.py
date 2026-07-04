"""
retention_router.py — Retention Engine API (Ticket #77).  Admin-only.

  GET /retention/rules              full 119-rule catalog (+ automatable flag)
  GET /retention/clients            ranked at-risk clients (filters: band, category, search; paginated)
  GET /retention/clients/{login}    per-client breakdown (fired rules + points + action + days)
  GET /retention/summary            counts per band + per category + meta
  POST /retention/rebuild           re-run the engine (bounded; admin trigger)
"""
import json
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user
from perf_cache import cached

router = APIRouter(prefix="/retention", tags=["Retention Engine"])

BAND_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Trusted": 4}


def _rows(db, sql, params=None):
    return [dict(r._mapping) for r in db.execute(text(sql), params or {}).fetchall()]


@router.get("/rules")
def get_rules(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """The full rule catalog, grouped-friendly (frontend groups by category)."""
    rules = _rows(db, """
        SELECT rule_id, category, description, risk_points, trigger_level,
               suggested_action, days_to_action, automatable
        FROM retention_rules ORDER BY rule_id
    """)
    cats = {}
    for r in rules:
        cats.setdefault(r["category"], {"category": r["category"], "count": 0, "automated": 0})
        cats[r["category"]]["count"] += 1
        if r["automatable"]:
            cats[r["category"]]["automated"] += 1
    return {
        "rules": rules,
        "categories": sorted(cats.values(), key=lambda c: c["category"]),
        "total": len(rules),
        "automated": sum(1 for r in rules if r["automatable"]),
    }


@router.get("/summary")
def get_summary(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # NOT role-scoped: retention_flags is a global at-risk snapshot, same for every staff
    # member (_user is auth-only). Fixed "all" scope, no params.
    return cached("retention:summary:all", 120, lambda: _build_retention_summary(db))


def _build_retention_summary(db):
    bands = {r["band"]: r["n"] for r in _rows(db,
        "SELECT band, count(*) n FROM retention_flags GROUP BY band")}
    band_list = [{"band": b, "count": bands.get(b, 0)} for b in
                 ("Critical", "High", "Medium", "Low", "Trusted")]

    # fired-rule category breakdown (unnest the json arrays in Python — small flag set)
    cat_counts = {}
    for r in db.execute(text("SELECT fired_rules FROM retention_flags")).fetchall():
        try:
            for f in json.loads(r[0] or "[]"):
                cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1
        except Exception:
            continue
    categories = sorted(
        [{"category": k, "fired": v} for k, v in cat_counts.items()],
        key=lambda x: -x["fired"])

    meta = db.execute(text(
        "SELECT count(*) n, max(computed_at) ts, "
        "       coalesce(sum(CASE WHEN band IN ('Critical','High') THEN 1 ELSE 0 END),0) at_risk "
        "FROM retention_flags")).fetchone()
    return {
        "bands": band_list,
        "categories": categories,
        "total_flagged": meta[0],
        "at_risk": meta[2],
        "computed_at": meta[1].isoformat() if meta[1] else None,
    }


@router.get("/clients")
def get_clients(
    band: str = Query("", description="Critical/High/Medium/Low/Trusted"),
    category: str = Query("", description="filter to clients with >=1 fired rule in this category"),
    search: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("score", description="score|band|fired|deposits"),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    # NOT role-scoped: the at-risk client list is global (_user is auth-only). Fixed "all"
    # scope; every filter/sort/page param is in the key so different views don't collide.
    cache_key = (f"retention:clients:all:{band}:{category}:{sort}:"
                 f"{page}:{page_size}:{search}")
    return cached(cache_key, 90, lambda: _build_retention_clients(
        db, band, category, search, page, page_size, sort))


def _build_retention_clients(db, band, category, search, page, page_size, sort):
    where = ["1=1"]
    params = {}
    if band:
        where.append("band = :band")
        params["band"] = band
    if search:
        where.append("(name ILIKE :q OR phone ILIKE :q OR CAST(login AS TEXT) ILIKE :q)")
        params["q"] = f"%{search}%"
    if category:
        where.append("fired_rules ILIKE :cat")
        params["cat"] = f'%"category": "{category}"%'
    wsql = " AND ".join(where)

    total = db.execute(text(f"SELECT count(*) FROM retention_flags WHERE {wsql}"), params).scalar()

    order = {
        "score": "score DESC",
        "band": "CASE band WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 "
                "WHEN 'Low' THEN 3 ELSE 4 END, score DESC",
        "fired": "fired_count DESC, score DESC",
        "deposits": "total_deposits DESC",
    }.get(sort, "score DESC")

    params["lim"] = page_size
    params["off"] = (page - 1) * page_size
    rows = _rows(db, f"""
        SELECT client_key, client_id, login, name, phone, platform, score, band,
               fired_count, top_action, top_days, n_logins,
               total_deposits, total_withdrawals, net_deposit
        FROM retention_flags
        WHERE {wsql}
        ORDER BY {order}
        LIMIT :lim OFFSET :off
    """, params)
    return {"clients": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/clients/{login}")
def get_client_detail(login: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT client_key, client_id, login, name, phone, platform, score, band,
               fired_rules, fired_count, top_action, top_days, n_logins,
               total_deposits, total_withdrawals, net_deposit, computed_at
        FROM retention_flags WHERE login = :l
        ORDER BY score DESC LIMIT 1
    """), {"l": login}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No retention flag for that client (not at-risk or not yet scored).")
    m = dict(row._mapping)
    try:
        fired = json.loads(m["fired_rules"] or "[]")
    except Exception:
        fired = []
    # sort fired rules: biggest positive risk first, trusted (negative) last
    fired.sort(key=lambda f: -f.get("points", 0))
    m["fired_rules"] = fired
    m["computed_at"] = m["computed_at"].isoformat() if m["computed_at"] else None
    return m


@router.post("/rebuild")
def rebuild(limit: int = Query(0, description="0 = all active clients; >0 bounds the run"),
            db: Session = Depends(get_db), _user=Depends(get_current_user)):
    import retention_engine as RE
    n = RE.build(db, score_all=False, limit=(limit or None), verbose=False)
    return {"ok": True, "flagged": n}
