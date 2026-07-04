"""
reactivation.py — bring ARCHIVED leads/clients back to life when the person re-engages.

Rules (set by the desk):
  • An archived LEAD or CLIENT that does ANY action (portal login, deposit, a logged call, etc.)
    is moved back to the active list, gets +50 score, and a re-capture-style badge with a DISTINCT
    "came back from archive" symbol (📦).
  • An archived LEAD that fills our META lead form gets BOTH badges: ♻ re-capture + 📦 archive.

Badges:
  leads.match_badge='recapture'  -> ♻  (existing)
  leads/clients.reactivated_from_archive=TRUE -> 📦  (new, the "archive re-capture" symbol)

Everything here is additive + idempotent. Helpers are defensive (never raise into the caller).
"""
from sqlalchemy import text


def ensure_columns(db):
    """Add the reactivation columns once (idempotent)."""
    try:
        db.execute(text("""
            ALTER TABLE leads   ADD COLUMN IF NOT EXISTS reactivated_from_archive BOOLEAN DEFAULT FALSE;
            ALTER TABLE leads   ADD COLUMN IF NOT EXISTS reactivated_at TIMESTAMP;
            ALTER TABLE clients ADD COLUMN IF NOT EXISTS reactivated_from_archive BOOLEAN DEFAULT FALSE;
            ALTER TABLE clients ADD COLUMN IF NOT EXISTS reactivated_at TIMESTAMP;
            ALTER TABLE clients ADD COLUMN IF NOT EXISTS user_archived BOOLEAN DEFAULT FALSE;
            ALTER TABLE clients ADD COLUMN IF NOT EXISTS user_archived_at TIMESTAMP;
        """))
        db.commit()
    except Exception:
        db.rollback()


def reactivate_lead(db, lead_id, via: str = "action") -> bool:
    """Un-archive a lead, +50 score, badge it. via='meta' also sets the ♻ recapture badge.
    Returns True if the lead was archived and got reactivated."""
    try:
        row = db.execute(text(
            "SELECT COALESCE(is_archived,FALSE), COALESCE(score,0), match_badge FROM leads WHERE id=:id"
        ), {"id": lead_id}).fetchone()
        if not row or not row[0]:
            return False                      # not found or not archived -> nothing to do
        new_score = min(100, int(row[1] or 0) + 50)
        # Badge: a NEW Meta submission shows ♻+📦 ('recapture_archive'); any other re-engagement
        # shows the distinct 📦 ('reactivated'). Never downgrade an existing 'converted' badge.
        badge = "recapture_archive" if via == "meta" else "reactivated"
        set_badge = (row[2] or "") not in ("converted",)
        db.execute(text(f"""
            UPDATE leads SET is_archived=FALSE, status='new', score=:s,
                   reactivated_from_archive=TRUE, reactivated_at=NOW(),
                   {"match_badge=:badge," if set_badge else ""}
                   notes=CONCAT(COALESCE(notes,''), :note), updated_at=NOW()
            WHERE id=:id
        """), {"s": new_score, "id": lead_id, "badge": badge,
               "note": f"\n[{_now()}] Re-captured from archive (via {via}) +50 score."})
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def reactivate_client_logins(db, logins, via: str = "action") -> int:
    """A USER-archived client re-engaged (login / deposit / KYC / etc.) -> bring the WHOLE PERSON back
    to the Clients page: clear user_archived across all their accounts, +50 call_score, and keep the
    📦 'was archived' tag (reactivated_from_archive) so agents see they returned. Returns # rows.
    NOTE: this clears the PERSON-level archive only; per-account MT archive (is_archived) is untouched."""
    if not logins:
        return 0
    try:
        res = db.execute(text("""
            WITH targets AS (
                SELECT DISTINCT COALESCE(customer_no, 'L'||login) AS gk
                FROM clients WHERE login = ANY(:ls) AND COALESCE(user_archived,FALSE)=TRUE
            )
            UPDATE clients c
               SET user_archived=FALSE, reactivated_from_archive=TRUE, reactivated_at=NOW(),
                   call_score=LEAST(100, COALESCE(call_score,0)+50), lead_badge='reactivated', updated_at=NOW()
             WHERE COALESCE(c.customer_no, 'L'||c.login) IN (SELECT gk FROM targets)
            RETURNING c.login
        """), {"ls": list(logins)})
        n = len(res.fetchall())
        db.commit()
        return n
    except Exception:
        db.rollback()
        return 0


def sweep(db) -> dict:
    """Catch CLIENT re-engagement that didn't go through an app hook: an archived client with a
    transaction (deposit/etc.) dated AFTER they were archived = they came back -> reactivate.

    NOTE: we deliberately do NOT auto-reactivate archived leads here. A legacy-archived lead is only
    re-captured when the person genuinely re-engages — a NEW Meta-form submission (handled in
    fetch_meta_leads.py) or an explicit action (handled at the action hook). Reactivating by mere
    phone-match to an existing depositor would wrongly un-archive already-converted legacy leads.
    Safe to run on a schedule. Returns counts."""
    ensure_columns(db)
    clients_back = 0
    try:
        # a USER-archived person with ANY money movement after they were archived = they came back.
        # Bring the whole person back (by customer_no group), +50, keep the 'was archived' tag.
        r = db.execute(text("""
            WITH back AS (
                SELECT DISTINCT COALESCE(c.customer_no, 'L'||c.login) AS gk
                FROM clients c
                WHERE COALESCE(c.user_archived,FALSE)=TRUE
                  AND EXISTS (SELECT 1 FROM transactions t
                              WHERE t.login=c.login
                                AND (c.user_archived_at IS NULL OR t.tx_date::timestamp > c.user_archived_at))
            )
            UPDATE clients c
               SET user_archived=FALSE, reactivated_from_archive=TRUE, reactivated_at=NOW(),
                   call_score=LEAST(100, COALESCE(call_score,0)+50), lead_badge='reactivated', updated_at=NOW()
             WHERE COALESCE(c.customer_no, 'L'||c.login) IN (SELECT gk FROM back)
            RETURNING c.login
        """))
        clients_back = len(r.fetchall()); db.commit()
    except Exception:
        db.rollback()
    return {"clients_reactivated": clients_back}


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    # CLI: ensure columns + run a sweep
    import os, psycopg2  # noqa
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    url = None
    for ln in open(os.path.join(os.path.dirname(__file__) or ".", ".env"), encoding="utf-8"):
        if ln.strip().startswith("DATABASE_URL"):
            url = ln.split("=", 1)[1].strip(); break
    eng = create_engine(url)
    with Session(eng) as s:
        ensure_columns(s)
        print(sweep(s))
