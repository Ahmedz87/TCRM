"""
mt_provision.py — backend client for real MT5 account provisioning.

The MT manager DLL only works inside the bridge's INTERACTIVE session, so the actual UserAdd /
DealerBalance run in the bridge (Flask :5000), which holds the live manager connection. This
module just calls those endpoints over localhost HTTP — safe to call from the backend (uvicorn).
"""
import json
import urllib.request
import urllib.error

BRIDGE = "http://127.0.0.1:5000"


def real_group(account_type, islamic):
    """Map the chosen account type (+ Islamic) to an existing live MT5 group."""
    at = (account_type or "Standard").strip().lower()
    base = {"standard": "STD\\2-STD", "cent": "Cent\\2-Cent", "zero": "ZERO\\2-ZERO",
            "vip": "VIP\\2-VIP", "fix": "STD\\2-STD"}.get(at, "STD\\2-STD")
    return base + ("-IS" if islamic else "")


def _post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BRIDGE + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"ok": False, "error": f"bridge http {e.code}"}
    except Exception as e:
        return {"ok": False, "error": f"bridge unreachable: {e}"}


def create_account(group, first, last, leverage=500, email="", phone="", country="", city="", agent=0):
    return _post("/provision/create", {"group": group, "first": first, "last": last,
                                       "leverage": leverage, "email": email, "phone": phone,
                                       "country": country, "city": city, "agent": agent})


def credit_account(login, amount, comment="Deposit", credit_type=2):
    """credit_type: 2 = BALANCE (deposit), 3 = CREDIT (bonus credit — not freely withdrawable)."""
    return _post(f"/provision/credit/{int(login)}", {"amount": amount, "comment": comment, "type": int(credit_type)})


# ───────────────────────── IDEMPOTENT PROVISIONING (P0-9/10) ─────────────────────────
# create_account is NOT idempotent on the MT side: a retry after a bridge timeout (where the
# account WAS actually created) would create a SECOND real account. This guards it with a
# `provision_intents` claim table: exactly one caller ever runs UserAdd per intent_key. All others
# get the recorded login back (idempotent) — or, if a prior attempt is mid-flight, a "in progress"
# refusal instead of a duplicate. The fail direction is SAFE: it will never double-create; a crash
# between the MT create and the status update leaves the intent 'pending' (blocks retries) until an
# admin reconciles, rather than risking a duplicate live account.
from sqlalchemy import text as _text


def _ensure_provision_intents(db):
    db.execute(_text("""CREATE TABLE IF NOT EXISTS provision_intents (
        intent_key TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | failed
        login BIGINT,
        error TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.commit()


def create_account_idempotent(db, intent_key, group, first, last, **kw):
    """Create a real MT account AT MOST ONCE per intent_key (e.g. "reg_123"). Concurrent or retried
    calls with the same key never double-create: they get the recorded login (idempotent=True) or a
    'in progress' refusal. Returns the same dict as create_account (+ 'idempotent'/'pending' flags).
    On an idempotent hit master/investor are None (credentials are only returned on the first create)."""
    _ensure_provision_intents(db)
    # atomic claim: only the FIRST caller inserts the 'pending' row and proceeds to UserAdd
    claimed = db.execute(_text("""
        INSERT INTO provision_intents (intent_key, status) VALUES (:k,'pending')
        ON CONFLICT (intent_key) DO NOTHING RETURNING intent_key
    """), {"k": intent_key}).scalar()
    db.commit()
    if not claimed:
        row = db.execute(_text("SELECT status, login FROM provision_intents WHERE intent_key=:k"),
                         {"k": intent_key}).fetchone()
        if row and row[0] == "done" and row[1]:
            return {"ok": True, "login": int(row[1]), "idempotent": True, "master": None, "investor": None}
        if row and row[0] == "pending":
            return {"ok": False, "pending": True,
                    "error": "provisioning already in progress for this registration"}
        # prior attempt FAILED — re-claim atomically so exactly one retry proceeds
        reclaimed = db.execute(_text("""UPDATE provision_intents SET status='pending', updated_at=NOW()
                                        WHERE intent_key=:k AND status='failed' RETURNING intent_key"""),
                               {"k": intent_key}).scalar()
        db.commit()
        if not reclaimed:
            row = db.execute(_text("SELECT status, login FROM provision_intents WHERE intent_key=:k"),
                             {"k": intent_key}).fetchone()
            if row and row[0] == "done" and row[1]:
                return {"ok": True, "login": int(row[1]), "idempotent": True, "master": None, "investor": None}
            return {"ok": False, "pending": True, "error": "provisioning already in progress"}

    # we hold the claim: create exactly once
    res = create_account(group, first, last, **kw)
    if res.get("ok") and res.get("login"):
        db.execute(_text("UPDATE provision_intents SET status='done', login=:lg, updated_at=NOW() WHERE intent_key=:k"),
                   {"lg": int(res["login"]), "k": intent_key})
    else:
        db.execute(_text("UPDATE provision_intents SET status='failed', error=:e, updated_at=NOW() WHERE intent_key=:k"),
                   {"e": str(res.get("error"))[:500], "k": intent_key})
    db.commit()
    return res


def delete_account(login):
    return _post(f"/provision/delete/{int(login)}")


def set_password(login, password, kind="master"):
    """kind = 'master' | 'investor'."""
    return _post(f"/provision/password/{int(login)}", {"password": password, "kind": kind})


def set_leverage(login, leverage):
    return _post(f"/provision/leverage/{int(login)}", {"leverage": int(leverage)})
