"""
Admin payment & account-type settings — CRUD over payment_methods and account_types.
Admin-auth protected (reuses existing get_current_user). Secrets are NEVER stored or
returned here; auto methods reference .env key NAMES only.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])


def _method_row(r):
    return {
        "id": r[0], "code": r[1], "name": r[2], "logo": r[3], "kind": r[4], "provider": r[5],
        "blurb": r[6], "fee": r[7], "processing_time": r[8],
        "is_active": r[9], "deposit_enabled": r[10], "withdraw_enabled": r[11],
        "min_deposit": float(r[12]) if r[12] is not None else None,
        "max_deposit": float(r[13]) if r[13] is not None else None,
        "min_withdraw": float(r[14]) if r[14] is not None else None,
        "max_withdraw": float(r[15]) if r[15] is not None else None,
        "allow_countries": r[16] or [], "block_countries": r[17] or [],
        "manual_details": r[18] or {}, "env_keys": r[19] or [], "api_config": r[20] or {},
        "sort_order": r[21],
    }

_MCOLS = """id,code,name,logo,kind,provider,blurb,fee,processing_time,is_active,deposit_enabled,
    withdraw_enabled,min_deposit,max_deposit,min_withdraw,max_withdraw,allow_countries,block_countries,
    manual_details,env_keys,api_config,sort_order"""


# ───────────── PAYMENT METHODS ─────────────
@router.get("/methods")
def list_methods(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.execute(text(f"SELECT {_MCOLS} FROM payment_methods ORDER BY sort_order, id")).fetchall()
    return {"methods": [_method_row(r) for r in rows]}


@router.get("/methods/{mid}")
def get_method(mid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    r = db.execute(text(f"SELECT {_MCOLS} FROM payment_methods WHERE id=:id"), {"id": mid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return _method_row(r)


@router.post("/methods")
def create_method(payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    code = (payload.get("code") or "").strip().lower().replace(" ", "_")
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    exists = db.execute(text("SELECT 1 FROM payment_methods WHERE code=:c"), {"c": code}).fetchone()
    if exists:
        raise HTTPException(status_code=400, detail="A method with that code already exists")
    db.execute(text("""
        INSERT INTO payment_methods
        (code,name,logo,kind,provider,blurb,fee,processing_time,is_active,deposit_enabled,withdraw_enabled,
         min_deposit,max_deposit,min_withdraw,max_withdraw,allow_countries,block_countries,manual_details,
         env_keys,api_config,sort_order)
        VALUES (:code,:name,:logo,:kind,:provider,:blurb,:fee,:ptime,:active,:dep,:wd,
         :mind,:maxd,:minw,:maxw,CAST(:allow AS JSONB),CAST(:block AS JSONB),CAST(:manual AS JSONB),
         CAST(:env AS JSONB),CAST(:api AS JSONB),:sort)
    """), _method_params(payload, code))
    db.commit()
    return {"ok": True}


@router.put("/methods/{mid}")
def update_method(mid: int, payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    r = db.execute(text("SELECT code FROM payment_methods WHERE id=:id"), {"id": mid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    p = _method_params(payload, r[0])
    p["id"] = mid
    db.execute(text("""
        UPDATE payment_methods SET
          name=:name, logo=:logo, kind=:kind, provider=:provider, blurb=:blurb, fee=:fee,
          processing_time=:ptime, is_active=:active, deposit_enabled=:dep, withdraw_enabled=:wd,
          min_deposit=:mind, max_deposit=:maxd, min_withdraw=:minw, max_withdraw=:maxw,
          allow_countries=CAST(:allow AS JSONB), block_countries=CAST(:block AS JSONB),
          manual_details=CAST(:manual AS JSONB), env_keys=CAST(:env AS JSONB),
          api_config=CAST(:api AS JSONB), sort_order=:sort, updated_at=NOW()
        WHERE id=:id
    """), p)
    db.commit()
    return {"ok": True}


@router.patch("/methods/{mid}/toggle")
def toggle_method(mid: int, payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    field = payload.get("field")
    if field not in ("is_active", "deposit_enabled", "withdraw_enabled"):
        raise HTTPException(status_code=400, detail="invalid field")
    db.execute(text(f"UPDATE payment_methods SET {field} = NOT {field}, updated_at=NOW() WHERE id=:id"), {"id": mid})
    db.commit()
    r = db.execute(text(f"SELECT {field} FROM payment_methods WHERE id=:id"), {"id": mid}).fetchone()
    return {"ok": True, "field": field, "value": r[0] if r else None}


@router.delete("/methods/{mid}")
def delete_method(mid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("DELETE FROM payment_methods WHERE id=:id"), {"id": mid})
    db.commit()
    return {"ok": True}


def _method_params(payload: dict, code: str) -> dict:
    def num(v, d=None):
        if v is None or v == "":
            return d
        try:
            return float(v)
        except Exception:
            return d
    return {
        "code": code,
        "name": payload.get("name") or code,
        "logo": payload.get("logo") or "generic",
        "kind": payload.get("kind") if payload.get("kind") in ("manual", "auto") else "manual",
        "provider": payload.get("provider") or "",
        "blurb": payload.get("blurb") or "",
        "fee": payload.get("fee") or "0%",
        "ptime": payload.get("processing_time") or "",
        "active": bool(payload.get("is_active", True)),
        "dep": bool(payload.get("deposit_enabled", True)),
        "wd": bool(payload.get("withdraw_enabled", True)),
        "mind": num(payload.get("min_deposit"), 10),
        "maxd": num(payload.get("max_deposit"), None),
        "minw": num(payload.get("min_withdraw"), 50),
        "maxw": num(payload.get("max_withdraw"), 100000),
        "allow": json.dumps(payload.get("allow_countries") or []),
        "block": json.dumps(payload.get("block_countries") or []),
        "manual": json.dumps(payload.get("manual_details") or {}),
        "env": json.dumps(payload.get("env_keys") or []),
        "api": json.dumps(payload.get("api_config") or {}),
        "sort": int(payload.get("sort_order") or 100),
    }


# ───────────── ACCOUNT TYPES ─────────────
def _type_row(r):
    return {
        "id": r[0], "code": r[1], "name": r[2], "description": r[3],
        "first_deposit_min": float(r[4]) if r[4] is not None else 0,
        "leverages": r[5] or [], "default_leverage": r[6],
        "swap_free_available": r[7], "platforms": r[8] or [],
        "mt5_group": r[9] or "", "mt4_group": r[10] or "",
        "is_active": r[11], "sort_order": r[12],
    }

_TCOLS = """id,code,name,description,first_deposit_min,leverages,default_leverage,swap_free_available,
    platforms,mt5_group,mt4_group,is_active,sort_order"""


@router.get("/account-types")
def list_types(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.execute(text(f"SELECT {_TCOLS} FROM account_types ORDER BY sort_order, id")).fetchall()
    return {"account_types": [_type_row(r) for r in rows]}


@router.post("/account-types")
def create_type(payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    code = (payload.get("code") or "").strip().lower().replace(" ", "_")
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    if db.execute(text("SELECT 1 FROM account_types WHERE code=:c"), {"c": code}).fetchone():
        raise HTTPException(status_code=400, detail="That code already exists")
    db.execute(text("""
        INSERT INTO account_types
        (code,name,description,first_deposit_min,leverages,default_leverage,swap_free_available,
         platforms,mt5_group,mt4_group,is_active,sort_order)
        VALUES (:code,:name,:desc,:fdm,CAST(:lev AS JSONB),:defl,:swap,
         CAST(:plat AS JSONB),:g5,:g4,:active,:sort)
    """), _type_params(payload, code))
    db.commit()
    return {"ok": True}


@router.put("/account-types/{tid}")
def update_type(tid: int, payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    r = db.execute(text("SELECT code FROM account_types WHERE id=:id"), {"id": tid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    p = _type_params(payload, r[0]); p["id"] = tid
    db.execute(text("""
        UPDATE account_types SET name=:name, description=:desc, first_deposit_min=:fdm,
          leverages=CAST(:lev AS JSONB), default_leverage=:defl, swap_free_available=:swap,
          platforms=CAST(:plat AS JSONB), mt5_group=:g5, mt4_group=:g4, is_active=:active,
          sort_order=:sort, updated_at=NOW()
        WHERE id=:id
    """), p)
    db.commit()
    return {"ok": True}


@router.delete("/account-types/{tid}")
def delete_type(tid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("DELETE FROM account_types WHERE id=:id"), {"id": tid})
    db.commit()
    return {"ok": True}


def _type_params(payload: dict, code: str) -> dict:
    return {
        "code": code, "name": payload.get("name") or code,
        "desc": payload.get("description") or "",
        "fdm": float(payload.get("first_deposit_min") or 0),
        "lev": json.dumps(payload.get("leverages") or [50, 100, 200, 400, 500, 1000]),
        "defl": int(payload.get("default_leverage") or 500),
        "swap": bool(payload.get("swap_free_available", True)),
        "plat": json.dumps(payload.get("platforms") or ["MT5", "MT4"]),
        "g5": payload.get("mt5_group") or "", "g4": payload.get("mt4_group") or "",
        "active": bool(payload.get("is_active", True)),
        "sort": int(payload.get("sort_order") or 100),
    }
