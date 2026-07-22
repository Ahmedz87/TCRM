# -*- coding: utf-8 -*-
"""Immutable audit trail for money & rule actions (P0, Jul 16 2026).

The audit_log table existed but nothing wrote to it. This helper writes an APPEND-ONLY row for
every sensitive action (withdrawal/deposit approve+reject, account freeze/clear, commission-rate
changes, bonus grants, role changes). A DB trigger blocks UPDATE/DELETE so the trail can't be
rewritten — what regulators and money disputes require.

Usage:
    import audit
    audit.log(db, user, "withdrawal_approve", "transaction", deal_id,
              old="pending", new="approved", amount=250.0, request=request)

NEVER lets an audit failure break the real operation — it logs best-effort and swallows errors.
"""
from sqlalchemy import text

_ENSURED = False


def _ensure(db):
    global _ENSURED
    if _ENSURED:
        return
    try:
        db.execute(text("SET lock_timeout = '4s'"))
        # make the table append-only: a trigger raises on any UPDATE/DELETE (superuser included,
        # unless it drops the trigger — which is itself an auditable server action).
        db.execute(text("""
            CREATE OR REPLACE FUNCTION audit_log_no_change() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;
        """))
        db.execute(text("DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log"))
        db.execute(text("""
            CREATE TRIGGER trg_audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_no_change();
        """))
        db.commit()
        _ENSURED = True
    except Exception:
        db.rollback()


def _ip(request):
    if request is None:
        return None
    try:
        xff = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
        if xff:
            return xff.split(",")[0].strip()[:64]
        return (request.client.host if request.client else None)
    except Exception:
        return None


def log(db, user, action, entity_type=None, entity_id=None, old=None, new=None,
        amount=None, request=None):
    """Append one immutable audit row. Best-effort — never raises into the caller.
    Commits its own row so it survives even if the surrounding request later rolls back."""
    _ensure(db)
    try:
        uid = getattr(user, "id", None) if user is not None else None
        nv = new
        if amount is not None:
            nv = f"{new} | amount={amount}" if new is not None else f"amount={amount}"
        db.execute(text("""
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, old_value, new_value,
                                   ip_address, user_agent, created_at)
            VALUES (:uid, :act, :et, :eid, :ov, :nv, :ip, :ua, NOW())
        """), {
            "uid": uid, "act": (action or "")[:80], "et": (entity_type or "")[:40],
            "eid": int(entity_id) if str(entity_id or "").lstrip("-").isdigit() else None,
            "ov": None if old is None else str(old)[:2000],
            "nv": None if nv is None else str(nv)[:2000],
            "ip": _ip(request),
            "ua": (request.headers.get("user-agent", "")[:200] if request else None),
        })
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
