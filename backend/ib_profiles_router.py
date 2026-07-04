"""
ib_profiles_router.py — settings API for the IB commission profile builder.

Register in main.py:
    from ib_profiles_router import router as ib_profiles_router
    app.include_router(ib_profiles_router)

Endpoints (under /settings/ib-profiles):
    GET    /settings/ib-profiles           -> all profiles + options + publish state
    POST   /settings/ib-profiles           -> create a profile
    PATCH  /settings/ib-profiles/{id}      -> update a profile
    POST   /settings/ib-profiles/{id}/duplicate  -> clone (optionally to another level)
    DELETE /settings/ib-profiles/{id}      -> delete
    POST   /settings/ib-profiles/publish   -> make active profiles live
"""
import os
import db_config
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/settings/ib-profiles", tags=["ib-profiles"])

DB = dict(
    host=os.getenv("PGHOST", db_config.DB_HOST), port=os.getenv("PGPORT", db_config.DB_PORT),
    dbname=os.getenv("PGDATABASE", db_config.DB_NAME), user=os.getenv("PGUSER", db_config.DB_USER),
    password=os.getenv("PGPASSWORD", db_config.DB_PASSWORD),
)
LEVELS = ["IB-3", "IB-5", "IB-6", "IB-7", "IB-8", "IB-9"]
ACCOUNT_TYPES = ["standard", "cent", "zero", "vip", "fix", "live"]
ASSET_CLASSES = ["forex", "metal", "crypto", "equity", "index", "energy"]
SUFFIXES = ["", ".", ".c", ".v", ".x", ".r", ".s", ".mttd"]


def db():
    return psycopg2.connect(**DB, cursor_factory=RealDictCursor)


class ProfileIn(BaseModel):
    name: str
    ib_level: str
    account_types: List[str] = []
    asset_class: Optional[str] = None
    match_symbols: List[str] = []
    match_suffixes: List[str] = []
    points: float = 0
    min_hold_minutes: int = 0
    priority: int = 100
    active: bool = True

class DupIn(BaseModel):
    ib_level: Optional[str] = None


def _mark_dirty(cur):
    pass  # publish state is derived from `published` flag per row


@router.get("")
def list_profiles():
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ib_profiles ORDER BY ib_level, priority, name")
        profiles = cur.fetchall()
        cur.execute("SELECT last_published_at FROM ib_profile_meta WHERE id=1")
        meta = cur.fetchone() or {"last_published_at": None}
        cur.execute("SELECT COUNT(*) AS n FROM ib_profiles WHERE active AND NOT published")
        dirty = cur.fetchone()["n"]
        return {
            "profiles": profiles,
            "options": {"levels": LEVELS, "account_types": ACCOUNT_TYPES,
                        "asset_classes": ASSET_CLASSES, "suffixes": SUFFIXES},
            "last_published_at": meta["last_published_at"],
            "has_unpublished": dirty > 0,
        }
    finally:
        conn.close()


def _insert(cur, p: ProfileIn):
    cur.execute("""INSERT INTO ib_profiles
        (name, ib_level, account_types, asset_class, match_symbols, match_suffixes,
         points, min_hold_minutes, priority, active, published)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE) RETURNING *""",
        (p.name, p.ib_level, p.account_types, p.asset_class, p.match_symbols,
         p.match_suffixes, p.points, p.min_hold_minutes, p.priority, p.active))
    return cur.fetchone()


@router.post("")
def create(p: ProfileIn):
    conn = db()
    try:
        cur = conn.cursor()
        row = _insert(cur, p)
        conn.commit()
        return row
    finally:
        conn.close()


@router.patch("/{pid}")
def update(pid: int, p: ProfileIn):
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("""UPDATE ib_profiles SET
            name=%s, ib_level=%s, account_types=%s, asset_class=%s, match_symbols=%s,
            match_suffixes=%s, points=%s, min_hold_minutes=%s, priority=%s, active=%s,
            published=FALSE, updated_at=now()
            WHERE id=%s RETURNING *""",
            (p.name, p.ib_level, p.account_types, p.asset_class, p.match_symbols,
             p.match_suffixes, p.points, p.min_hold_minutes, p.priority, p.active, pid))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Profile not found")
        conn.commit()
        return row
    finally:
        conn.close()


@router.post("/{pid}/duplicate")
def duplicate(pid: int, body: DupIn):
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ib_profiles WHERE id=%s", (pid,))
        src = cur.fetchone()
        if not src:
            raise HTTPException(404, "Profile not found")
        new_level = body.ib_level or src["ib_level"]
        new_name = src["name"].replace(src["ib_level"], new_level) \
            if src["ib_level"] in src["name"] else f"{new_level} / {src['name']}"
        cur.execute("""INSERT INTO ib_profiles
            (name, ib_level, account_types, asset_class, match_symbols, match_suffixes,
             points, min_hold_minutes, priority, active, published)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE) RETURNING *""",
            (new_name, new_level, src["account_types"], src["asset_class"], src["match_symbols"],
             src["match_suffixes"], src["points"], src["min_hold_minutes"], src["priority"], src["active"]))
        row = cur.fetchone()
        conn.commit()
        return row
    finally:
        conn.close()


@router.delete("/{pid}")
def delete(pid: int):
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ib_profiles WHERE id=%s", (pid,))
        conn.commit()
        return {"deleted": pid}
    finally:
        conn.close()


@router.post("/publish")
def publish():
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ib_profiles SET published = active")
        cur.execute("UPDATE ib_profile_meta SET last_published_at = now() WHERE id=1")
        conn.commit()
        return {"published": True}
    finally:
        conn.close()
