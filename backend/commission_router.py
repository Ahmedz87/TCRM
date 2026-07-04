"""
commission_router.py — CRUD for IB commission profiles & rules + a live preview.

Mirrors the "Profile Configurations" screen:
  • a PROFILE (name, ib_level, platform) holds a list of RULES
  • a RULE = {name, priority, symbols(patterns), distribution, value}
  • preview: given a symbol+lots+level, returns the winning rule and the USD commission.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import ib_commission as IC

router = APIRouter(prefix="/commission", tags=["commission"])


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    IC_ensure(db)
    rows = db.execute(text("""
        SELECT p.id, p.name, p.ib_level, p.platform, COUNT(r.id) AS rules
        FROM commission_profiles p LEFT JOIN commission_rules r ON r.profile_id=p.id
        GROUP BY p.id ORDER BY p.ib_level, p.platform
    """)).fetchall()
    return {"profiles": [{"id": r[0], "name": r[1], "ib_level": r[2],
                          "platform": r[3], "rule_count": r[4]} for r in rows]}


@router.get("/profiles/{pid}")
def get_profile(pid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.execute(text("SELECT id,name,ib_level,platform FROM commission_profiles WHERE id=:i"), {"i": pid}).fetchone()
    if not p:
        raise HTTPException(404, "profile not found")
    # sequential rule ID: 16 per profile, leveled profiles first (5..10) then tiers, by id
    ids = [r[0] for r in db.execute(text(
        "SELECT id FROM commission_profiles ORDER BY COALESCE(ib_level,9999), id")).fetchall()]
    base = (ids.index(pid) * 16) if pid in ids else 0
    rules = db.execute(text("""
        SELECT id, name, priority, symbols, distribution, value
        FROM commission_rules WHERE profile_id=:i ORDER BY priority
    """), {"i": pid}).fetchall()
    return {
        "id": p[0], "name": p[1], "ib_level": p[2], "platform": p[3],
        "rules": [{"serial": base + i + 1, "id": r[0], "name": r[1], "priority": r[2],
                   "symbols": r[3], "distribution": r[4], "value": r[5]} for i, r in enumerate(rules)],
    }


@router.post("/profiles")
def create_profile(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    IC_ensure(db)
    pid = db.execute(text("""
        INSERT INTO commission_profiles (name, ib_level, platform)
        VALUES (:n,:l,:p) RETURNING id
    """), {"n": data.get("name", ""), "l": data.get("ib_level"), "p": data.get("platform", "MT5")}).scalar()
    db.commit()
    return {"ok": True, "id": pid}


@router.put("/profiles/{pid}")
def update_profile(pid: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("UPDATE commission_profiles SET name=:n, ib_level=:l, platform=:p WHERE id=:i"),
               {"n": data.get("name", ""), "l": data.get("ib_level"), "p": data.get("platform", "MT5"), "i": pid})
    db.commit()
    return {"ok": True}


@router.delete("/profiles/{pid}")
def delete_profile(pid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("DELETE FROM commission_rules WHERE profile_id=:i"), {"i": pid})
    db.execute(text("DELETE FROM commission_profiles WHERE id=:i"), {"i": pid})
    db.commit()
    return {"ok": True}


@router.post("/profiles/{pid}/rules")
def create_rule(pid: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rid = db.execute(text("""
        INSERT INTO commission_rules (profile_id, name, priority, symbols, distribution, value, entry)
        VALUES (:p,:n,:pr,:s,:d,:v,'out') RETURNING id
    """), {"p": pid, "n": data.get("name", ""), "pr": data.get("priority", 20),
           "s": data.get("symbols", "*"), "d": data.get("distribution", "pips"),
           "v": data.get("value", 0)}).scalar()
    db.commit()
    return {"ok": True, "id": rid}


@router.put("/rules/{rid}")
def update_rule(rid: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("""
        UPDATE commission_rules SET name=:n, priority=:pr, symbols=:s, distribution=:d, value=:v WHERE id=:i
    """), {"n": data.get("name", ""), "pr": data.get("priority", 20), "s": data.get("symbols", "*"),
           "d": data.get("distribution", "pips"), "v": data.get("value", 0), "i": rid})
    db.commit()
    return {"ok": True}


@router.delete("/rules/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("DELETE FROM commission_rules WHERE id=:i"), {"i": rid})
    db.commit()
    return {"ok": True}


@router.post("/preview")
def preview(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Given {symbol, lots, ib_level, platform} return the winning rule + USD commission."""
    symbol = (data.get("symbol") or "").strip()
    lots = float(data.get("lots") or 1)
    cur = db.connection().connection.cursor()
    pid = data.get("profile_id")
    if pid:
        rules = IC.load_rules_by_profile(cur, int(pid))
    else:
        rules = IC.load_profile_rules(cur, int(data.get("ib_level") or 5), data.get("platform", "MT5"))
    rule = IC.match_rule(rules, symbol)
    if not rule:
        return {"matched": False}
    comm = IC.commission_for(rule, lots, symbol)
    pip = IC.pip_value_usd(symbol, cur)
    return {
        "matched": True, "symbol": symbol, "lots": lots,
        "rule": rule["name"], "priority": rule["priority"],
        "distribution": rule["distribution"], "value": rule["value"],
        "pip_usd": pip, "commission_usd": comm,
    }


def IC_ensure(db):
    """Make sure the commission tables exist (idempotent)."""
    cur = db.connection().connection.cursor()
    IC.ensure_schema(cur)
    db.commit()
