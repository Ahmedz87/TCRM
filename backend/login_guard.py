# -*- coding: utf-8 -*-
"""Shared brute-force lockout for login endpoints (P0, Jul 16 2026).

The portal login already had a DB-backed lockout, but the MAIN /auth/login (routers/auth_router)
— which authenticates BOTH staff (incl. admins, who move real money) AND clients, and is publicly
reachable on my1.tnfx.co — had NONE. This module reuses the SAME `portal_login_attempts` table so
a lock is unified across every login surface.

Tuning: per-identifier is the real protection (5 fails / 15 min). Per-IP is a secondary
spray guard and is GENEROUS (50) because up to ~80 staff share ONE office IP — a strict per-IP
limit would lock the whole floor when a few people fat-finger a password.
"""
from fastapi import HTTPException, Request
from sqlalchemy import text

MAX_FAILS_IDENT = 5
MAX_FAILS_IP    = 50
WINDOW_MIN      = 15


def _ensure(db):
    try:
        db.execute(text("SET lock_timeout = '4s'"))
        db.execute(text("""CREATE TABLE IF NOT EXISTS portal_login_attempts (
            id SERIAL PRIMARY KEY, ident VARCHAR(160), ip VARCHAR(64),
            ok BOOLEAN, created_at TIMESTAMP DEFAULT NOW())"""))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_pla_ident_time ON portal_login_attempts (ident, created_at)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_pla_ip_time ON portal_login_attempts (ip, created_at)"))
        db.commit()
    except Exception:
        db.rollback()


def client_ip(request: Request) -> str:
    """Real client IP behind nginx (X-Forwarded-For / X-Real-IP)."""
    if request is None:
        return "unknown"
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    xr = request.headers.get("x-real-ip")
    if xr:
        return xr.strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def check_and_raise(db, ident: str, ip: str):
    """Raise 429 if the identifier or IP is over the failed-attempt limit in the window.
    Call BEFORE verifying the password."""
    try:
        fails = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE ident=:i) AS by_ident,
                   COUNT(*) FILTER (WHERE ip=:p)    AS by_ip
            FROM portal_login_attempts
            WHERE ok=FALSE AND created_at > NOW() - make_interval(mins => :w)
        """), {"i": (ident or "").lower()[:160], "p": ip, "w": WINDOW_MIN}).fetchone()
    except Exception:
        db.rollback(); return  # never let the guard's own error block a legitimate login
    if (fails[0] or 0) >= MAX_FAILS_IDENT or (fails[1] or 0) >= MAX_FAILS_IP:
        raise HTTPException(status_code=429,
            detail=f"Too many failed attempts. Try again in {WINDOW_MIN} minutes.")


def record(db, ident: str, ip: str, ok: bool):
    """Log the attempt. A SUCCESS wipes that identifier's prior failures (unlocks them)."""
    try:
        db.execute(text("INSERT INTO portal_login_attempts (ident, ip, ok) VALUES (:i,:p,:o)"),
                   {"i": (ident or "").lower()[:160], "p": ip, "o": ok})
        if ok:
            db.execute(text("DELETE FROM portal_login_attempts WHERE ident=:i AND ok=FALSE"),
                       {"i": (ident or "").lower()[:160]})
        db.execute(text("DELETE FROM portal_login_attempts WHERE created_at < NOW() - INTERVAL '1 day'"))
        db.commit()
    except Exception:
        db.rollback()
