# -*- coding: utf-8 -*-
"""Job handlers for the durable queue (job_queue.py). Each handler is idempotent and raises on
failure so the queue retries with backoff. Keep handlers pure: (db, payload) -> result dict."""
from sqlalchemy import text


def _ensure_grant_flag(db):
    # idempotency marker: once an MT credit lands for a grant, never credit it again
    db.execute(text("ALTER TABLE bonus_grants ADD COLUMN IF NOT EXISTS mt_credited_at TIMESTAMPTZ"))
    db.commit()


def bonus_mt_credit(db, payload):
    """Push a bonus grant's money to the REAL MT account as CREDIT (type 3), exactly once.
    payload: {grant_id}. Idempotent via bonus_grants.mt_credited_at."""
    _ensure_grant_flag(db)
    gid = int(payload.get("grant_id"))
    row = db.execute(text("""
        SELECT g.id, g.login, g.amount, g.kind, g.mt_credited_at, c.name, c.email
        FROM bonus_grants g JOIN clients c ON c.id = g.client_id
        WHERE g.id = :gid
    """), {"gid": gid}).fetchone()
    if not row:
        return {"skipped": "grant gone"}
    if row[4] is not None:
        return {"skipped": "already credited", "at": str(row[4])}
    login, amount, kind = row[1], float(row[2] or 0), row[3]
    if not login or int(login) <= 0:
        return {"skipped": "no login yet"}   # nothing to credit; done (not an error)

    import mt_provision
    # #204: every bonus credit must state WHAT it is on the account (deposit / welcome / birthday /
    # special), never a bare amount. This label becomes the MT credit's Comment (visible on the
    # terminal + in the transactions ledger) and the email wording.
    _BONUS_LABELS = {
        "welcome":    "Welcome Bonus",
        "birthday":   "Birthday Bonus",
        "deposit":    "Deposit Bonus",
        "deposit_50": "Deposit Bonus 50%",
        "deposit_20": "Deposit Bonus 20%",
        "special":    "Special Bonus",
        "manual":     "Special Bonus",
        "exception":  "Special Bonus",
    }
    friendly = _BONUS_LABELS.get(kind) or ((str(kind).replace("_", " ").title() + " Bonus") if kind else "Bonus")
    label = f"TNFX {friendly}"
    res = mt_provision.credit_account(int(login), amount, label, credit_type=3)
    if not res.get("ok"):
        # RAISE so the queue retries (this is the whole point — no more silent loss)
        raise RuntimeError(f"MT credit failed for login {login}: {res.get('error')}")
    # mark credited BEFORE the (best-effort) email so a mail failure can't cause a re-credit
    db.execute(text("UPDATE bonus_grants SET mt_credited_at=NOW() WHERE id=:gid AND mt_credited_at IS NULL"),
               {"gid": gid})
    db.commit()
    try:
        import email_send
        if row[6] and email_send.configured():
            nm = (row[5] or "").split(" ")[0]
            body = (f"Dear {nm},\n\nYour ${amount:,.0f} TNFX {friendly} has been credited to trading "
                    f"account #{login}. It appears as Credit (labelled “{label}”) on your terminal and "
                    f"increases your available margin.\n\nKind regards,\nTNFX")
            email_send.send(row[6], f"Your ${amount:,.0f} TNFX {friendly} has been credited", body)
    except Exception:
        pass
    return {"credited": amount, "login": login}


HANDLERS = {
    "bonus_mt_credit": bonus_mt_credit,
}
