"""
payment_gateway_router.py — online deposit gateways (Paymaxis/USDT-Hero, BridgerPay, Ptop).

  portal  (prefix /portal): list enabled online methods, create a deposit session (-> payment_url
                            or cashier token). Ownership-checked.
  public  (prefix /payments): the gateway webhook/callback endpoints (signature-verified) that
                            credit the deposit on success.

All gateways are DISABLED until gateway_config.py has credentials + enabled=True (see
gateway_config.example.py). Until then /portal/deposit/online returns "unavailable" and no
webhook can credit anything. Live execution = the same ledger record as a manually-approved
deposit (deal_id 9e9+rid); real MT crediting via the bridge stays a separate gated step.
"""
import json
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
from payment_cards_router import require_backoffice   # payment settings = back-office only
import payment_gateways as PG

try:
    from portal_router import get_current_client, _assert_owns_login
except Exception:
    def get_current_client():
        raise RuntimeError("client auth unavailable")
    def _assert_owns_login(db, cid, login):
        return None

portal = APIRouter(prefix="/portal", tags=["Portal online deposit"])
public = APIRouter(prefix="/payments", tags=["Payment gateways"])


def _ensure(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS portal_money_requests (
        id SERIAL PRIMARY KEY, client_id INT, login BIGINT, kind VARCHAR(20), amount NUMERIC,
        method VARCHAR(40), status VARCHAR(30), created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.execute(text("ALTER TABLE portal_money_requests ADD COLUMN IF NOT EXISTS gateway VARCHAR(20)"))
    db.execute(text("ALTER TABLE portal_money_requests ADD COLUMN IF NOT EXISTS gateway_ref VARCHAR(80)"))
    db.commit()


# ───────────────────────── PORTAL: methods + create session ─────────────────────────
@portal.get("/deposit/online-methods")
def online_methods(db: Session = Depends(get_db), client_id: int = Depends(get_current_client)):
    """The online gateways that are switched on right now (empty until configured)."""
    return {"methods": PG.list_methods()}


@portal.post("/deposit/online")
def create_online_deposit(payload: dict, db: Session = Depends(get_db),
                          client_id: int = Depends(get_current_client)):
    """Create a real online-gateway deposit session and return its payment URL / cashier token."""
    _ensure(db)
    gateway = (payload.get("gateway") or "").strip().lower()
    amount = float(payload.get("amount") or 0)
    login = int(payload.get("login") or 0)
    if gateway not in PG.ALL_GATEWAYS:
        return {"ok": False, "error": "Unknown payment method."}
    if amount <= 0:
        return {"ok": False, "error": "Enter a valid amount."}
    if not PG.is_enabled(gateway):
        return {"ok": False, "error": f"{PG.LABELS.get(gateway, gateway)} is not available right now."}
    if login:
        try:
            _assert_owns_login(db, client_id, login)
        except Exception:
            return {"ok": False, "error": "That account is not yours."}
    # client details for the gateway
    cl = db.execute(text("SELECT name, email FROM clients WHERE login=:l"), {"l": login}).fetchone()
    name = (cl[0] if cl else "") or "Client"
    email = (cl[1] if cl else "") or ""
    fn = name.split(" ")[0]; ln = " ".join(name.split(" ")[1:])
    cur = PG._cfg(gateway).get("currency", "USD")
    # 1) record a pending request -> its id is the gateway order_id
    rid = db.execute(text("""INSERT INTO portal_money_requests (client_id, login, kind, amount, method, status, gateway)
        VALUES (:c,:l,'deposit',:a,:m,'pending_payment',:g) RETURNING id"""),
        {"c": client_id, "l": login, "a": amount, "m": PG.LABELS.get(gateway, gateway), "g": gateway}).scalar()
    db.commit()
    # 2) create the gateway session
    res = PG.create_payment(gateway, amount=amount, currency=cur, order_id=rid,
                            email=email, first_name=fn, last_name=ln, reference=str(login or client_id),
                            description=f"TNFX deposit #{rid}")
    if not res.get("ok"):
        db.execute(text("UPDATE portal_money_requests SET status='failed' WHERE id=:i"), {"i": rid}); db.commit()
        return {"ok": False, "error": res.get("error", "Could not start the payment.")}
    if res.get("gateway_ref"):
        db.execute(text("UPDATE portal_money_requests SET gateway_ref=:r WHERE id=:i"),
                   {"r": str(res["gateway_ref"])[:80], "i": rid}); db.commit()
    return {"ok": True, "request_id": rid, "kind": res.get("kind"),
            "payment_url": res.get("payment_url"), "cashier": res.get("cashier"), "crypto": res.get("crypto")}


# ───────────────────────── PUBLIC: gateway webhooks ─────────────────────────
@public.post("/webhook/{gateway}")
async def gateway_webhook(gateway: str, request: Request, db: Session = Depends(get_db)):
    """Signature-verified callback. On success → mark the request approved + record the ledger
    deposit (deal_id 9e9+rid), exactly like a manually-approved deposit."""
    _ensure(db)
    gateway = (gateway or "").lower()
    raw = await request.body()
    if not PG.verify_webhook(gateway, dict(request.headers), raw):
        return {"ok": False, "error": "bad signature"}
    try:
        body = json.loads(raw.decode() or "{}")
    except Exception:
        body = {}
    ev = PG.parse_webhook(gateway, body)
    rid = ev.get("order_id")
    if not rid or not str(rid).isdigit():
        return {"ok": True, "note": "no order_id"}
    rid = int(rid)
    r = db.execute(text("SELECT login, amount, status FROM portal_money_requests WHERE id=:i"), {"i": rid}).fetchone()
    if not r:
        return {"ok": True, "note": "unknown request"}
    if r[2] == "approved":
        return {"ok": True, "note": "already credited"}   # idempotent
    if ev["status"] == "success":
        # MONEY SAFETY (P0, Jul 16): credit what was ACTUALLY PAID, not what the client requested.
        # The gateway reports the real paid amount+currency; if it differs from the request (under/
        # over-payment or a wrong currency), credit the paid amount and FLAG the row for review
        # rather than silently recording the requested figure.
        requested = float(r[1] or 0)
        paid = float(ev.get("amount") or 0)
        cur = (ev.get("currency") or "").upper()
        credit_amount = paid if paid > 0 else requested          # some gateways omit amount
        amt_mismatch = paid > 0 and abs(paid - requested) > max(0.01, requested * 0.01)
        cur_mismatch = bool(cur) and cur != "USD"
        note = f"{gateway} gateway deposit"
        review = amt_mismatch or cur_mismatch
        if review:
            note += f" ⚠ REVIEW: paid {paid:.2f} {cur or 'USD'} vs requested {requested:.2f} USD"
        db.execute(text("""INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method,
              status, notes, tx_date, tx_month, created_at, updated_at)
            VALUES (:d,:l,'deposit',:a,:cur,:m,:st,:note,
              to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'), to_char(NOW(),'YYYY-MM'), NOW(), NOW())
            ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING"""),
            {"d": 9_000_000_000 + rid, "l": r[0], "a": credit_amount, "cur": cur or "USD",
             "st": "review" if review else "approved",
             "m": PG.LABELS.get(gateway, gateway), "note": note})
        # keep status='approved' on the request so a duplicate webhook stays idempotent; the
        # transaction row carries the review flag + the true paid amount for the desk.
        db.execute(text("UPDATE portal_money_requests SET status='approved', gateway_ref=:gr WHERE id=:i"),
                   {"gr": str(ev.get("gateway_ref") or "")[:80], "i": rid})
        db.commit()
        return {"ok": True, "credited": True, "amount": credit_amount, "review": review}
    if ev["status"] == "failed":
        db.execute(text("UPDATE portal_money_requests SET status='rejected' WHERE id=:i"), {"i": rid}); db.commit()
    return {"ok": True, "status": ev["status"]}


# ───────────────────────── ADMIN: gateway status ─────────────────────────
@public.get("/gateways/status")
def gateways_status(db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    """Staff view: which gateways are enabled/sandbox (no secrets returned)."""
    out = []
    for gw in PG.ALL_GATEWAYS:
        is_ov = gw in PG._OV_KEYMAP
        c = PG._OV if is_ov else PG._cfg(gw)
        out.append({"gateway": gw, "label": PG.LABELS.get(gw, gw), "enabled": PG.is_enabled(gw),
                    "sandbox": bool(c.get("sandbox")), "currency": PG._currency(gw),
                    "has_credentials": bool(PG._ov_apikey(gw)) if is_ov else bool(c)})
    return {"gateways": out}
