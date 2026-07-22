"""
payment_gateways.py — online deposit gateways: Paymaxis (USDT-Hero), BridgerPay, Ptop.

Unified surface used by payment_gateway_router.py:
  list_methods()                         -> [{gateway, label, currency, kind}]  (only ENABLED ones)
  create_payment(gateway, *, ...)        -> {ok, payment_url|cashier, gateway_ref, raw} | {ok:False, error}
  verify_webhook(gateway, headers, raw)  -> bool
  parse_webhook(gateway, body)           -> {order_id, status, amount, gateway_ref}  (status: success|failed|pending)

SAFETY: a gateway only works when gateway_config.py exists AND that gateway's
`enabled=True` with credentials present. Otherwise create_payment returns ok=False
("not configured") and NO real money can move. Build/scaffold is complete; flip gateways
live ONE at a time after a real end-to-end test (see gateway_config.example.py).
"""
import hmac, hashlib, json, time

try:
    import gateway_config as CFG
    _G = getattr(CFG, "GATEWAYS", {})
    _PUBLIC = getattr(CFG, "PUBLIC_BASE", "https://my1.tnfx.co")
    _OV = getattr(CFG, "OVADOT", {})
except Exception:
    _G, _PUBLIC, _OV = {}, "https://my1.tnfx.co", {}

LABELS = {"paymaxis": "Crypto (USDT)", "bridgerpay": "Card (Visa/Master)", "ptop": "Ptop",
          "ovadot_ewallet": "Ovadot Wallet", "ovadot_crypto": "Ovadot Crypto (USDT)", "ovadot_qcard": "Ovadot Q-Card"}
KIND   = {"paymaxis": "redirect", "bridgerpay": "cashier", "ptop": "redirect",
          "ovadot_ewallet": "redirect", "ovadot_crypto": "crypto", "ovadot_qcard": "redirect"}
# ovadot gateway-key suffix -> the OVADOT config key that holds its merchant apiKey
_OV_KEYMAP  = {"ovadot_ewallet": "ewallet_key", "ovadot_crypto": "crypto_key", "ovadot_qcard": "qcard_key"}
# per-method enable flag (a method shows in the portal ONLY when its flag is True)
_OV_FLAGMAP = {"ovadot_ewallet": "ewallet_enabled", "ovadot_crypto": "crypto_enabled", "ovadot_qcard": "qcard_enabled"}


def _ov_base():
    return _OV.get("base_sandbox") if _OV.get("sandbox") else _OV.get("base_live")


def _ov_apikey(gw):
    return _OV.get(_OV_KEYMAP.get(gw, ""), "")


def _cfg(gw):
    return _G.get(gw) or {}


def is_enabled(gw) -> bool:
    if gw in _OV_KEYMAP:
        return (bool(_OV.get("enabled")) and bool(_OV.get(_OV_FLAGMAP.get(gw, ""), False))
                and bool(_ov_apikey(gw)))
    c = _cfg(gw)
    if not c.get("enabled"):
        return False
    if gw == "paymaxis":
        return bool(c.get("api_key"))
    if gw == "bridgerpay":
        return bool(c.get("user_name") and c.get("password") and c.get("api_key"))
    if gw == "ptop":
        return bool(c.get("website_id") and c.get("secret_key"))
    return False


ALL_GATEWAYS = ("paymaxis", "bridgerpay", "ptop", "ovadot_ewallet", "ovadot_crypto", "ovadot_qcard")


def _currency(gw):
    if gw in _OV_KEYMAP:
        return _OV.get("crypto_currency", "USDT").upper() if gw == "ovadot_crypto" else "USD"
    return _cfg(gw).get("currency", "USD")


def list_methods():
    return [{"gateway": gw, "label": LABELS.get(gw, gw), "currency": _currency(gw),
             "kind": KIND.get(gw, "redirect")} for gw in ALL_GATEWAYS if is_enabled(gw)]


def _base(gw):
    c = _cfg(gw)
    return c.get("base_sandbox") if c.get("sandbox") else c.get("base_live")


def _http_post(url, *, json_body=None, headers=None, timeout=25):
    import requests
    r = requests.post(url, json=json_body, headers=headers or {}, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"_text": r.text}
    return r.status_code, data


# ───────────────────────────── create payment ─────────────────────────────
def create_payment(gw, *, amount, currency, order_id, email="", first_name="", last_name="",
                   reference="", description="Deposit"):
    """Create a deposit session at the gateway. Returns a redirect URL (paymaxis/ptop) or a
    cashier token (bridgerpay) for the portal to open."""
    if not is_enabled(gw):
        return {"ok": False, "error": f"{LABELS.get(gw, gw)} is not configured yet."}
    success_url = f"{_PUBLIC}/portal/#/funds?deposit=success&ref={order_id}"
    fail_url    = f"{_PUBLIC}/portal/#/funds?deposit=failed&ref={order_id}"

    # ── Ovadot e-wallet platform (3 types). Amounts in USD CENTS. ──
    if gw in _OV_KEYMAP:
        try:
            base, key = _ov_base(), _ov_apikey(gw)
            cents = int(round(float(amount) * 100))
            if gw == "ovadot_ewallet":
                code, d = _http_post(f"{base}/api/payment/create", json_body={
                    "api_key": key, "amount": cents, "order_id": str(order_id),
                    "description": description, "return_url": success_url})
                if d.get("success") and d.get("checkout_url"):
                    return {"ok": True, "payment_url": d["checkout_url"], "gateway_ref": d.get("payment_id", ""),
                            "kind": "redirect", "raw": d}
                return {"ok": False, "error": d.get("error") or f"Ovadot error ({code})", "raw": d}
            if gw == "ovadot_qcard":
                code, d = _http_post(f"{base}/api/qcard/session", json_body={
                    "api_key": key, "trading_account": str(reference or order_id), "return_url": success_url})
                if d.get("success") and d.get("redirect_url"):
                    return {"ok": True, "payment_url": d["redirect_url"], "gateway_ref": d.get("session_token", ""),
                            "kind": "redirect", "raw": d}
                return {"ok": False, "error": d.get("error") or f"Ovadot Q-Card error ({code})", "raw": d}
            if gw == "ovadot_crypto":
                code, d = _http_post(f"{base}/api/crypto/deposit/create", json_body={
                    "api_key": key, "wallet_id": str(reference or order_id),
                    "currency": _OV.get("crypto_currency", "usdttrc20"), "amount": cents, "reference": str(order_id)})
                if d.get("success"):
                    # crypto returns a pay-to address/amount (NOWPayments) — show it, no redirect
                    return {"ok": True, "crypto": d, "payment_url": d.get("payment_url") or d.get("invoice_url"),
                            "gateway_ref": str(d.get("payment_id") or d.get("id") or ""), "kind": "crypto", "raw": d}
                return {"ok": False, "error": d.get("error") or f"Ovadot Crypto error ({code})", "raw": d}
        except Exception as e:
            return {"ok": False, "error": f"{LABELS.get(gw, gw)} request failed: {str(e)[:140]}"}

    c = _cfg(gw)
    webhook_url = f"{_PUBLIC}/api/payments/webhook/{gw}"
    cur = currency or c.get("currency", "USD")
    try:
        if gw == "ptop":
            code, d = _http_post(_base("ptop"), json_body={
                "website_id": c["website_id"], "secret_key": c["secret_key"],
                "amount": round(float(amount), 2), "currency": cur, "product": description,
                "order_id": str(order_id), "webhook_url": webhook_url,
                "success_url": success_url, "fail_url": fail_url})
            if d.get("success") and d.get("payment_url"):
                return {"ok": True, "payment_url": d["payment_url"],
                        "gateway_ref": d.get("transaction_id", ""), "kind": "redirect", "raw": d}
            return {"ok": False, "error": d.get("message") or f"Ptop error ({code})", "raw": d}

        if gw == "paymaxis":
            hdr = {"Authorization": c["api_key"], "Content-Type": "application/json"}
            body = {"paymentType": "DEPOSIT", "amount": str(round(float(amount), 2)), "currency": cur,
                    "description": description, "paymentMethod": c.get("payment_method", "CRYPTO"),
                    "returnUrl": success_url, "webhookUrl": webhook_url,
                    "customer": {"referenceId": str(reference or order_id), "email": email or "noemail@tnfx.co",
                                 "firstName": first_name or "Client", "lastName": last_name or str(reference or "")}}
            code, d = _http_post(f"{_base('paymaxis')}/api/v1/payments", json_body=body, headers=hdr)
            res = d.get("result") or d
            url = res.get("redirectUrl") or res.get("redirect_url")
            if url:
                return {"ok": True, "payment_url": url, "gateway_ref": res.get("id", ""),
                        "kind": "redirect", "raw": d}
            return {"ok": False, "error": (d.get("errorMessage") or d.get("message") or f"Paymaxis error ({code})"), "raw": d}

        if gw == "bridgerpay":
            # 1) api-login -> access_token
            code, auth = _http_post(f"{c['api_url']}/v2/auth/api-login",
                                    json_body={"user_name": c["user_name"], "password": c["password"]})
            token = (auth.get("access_token") or (auth.get("result") or {}).get("access_token"))
            if not token:
                return {"ok": False, "error": f"BridgerPay auth failed ({code})", "raw": auth}
            # 2) create cashier session
            hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            code, d = _http_post(f"{c['api_url']}/v2/cashier/session/create/{c['api_key']}", headers=hdr,
                                 json_body={"cashier_key": c.get("cashier_key", ""), "order_id": str(order_id),
                                            "currency": cur, "amount": round(float(amount), 2),
                                            "country": "IQ", "first_name": first_name or "Client",
                                            "last_name": last_name or "", "email": email or "noemail@tnfx.co"})
            res = d.get("result") or d
            ctok = res.get("cashier_token")
            if ctok:
                # cashier is an iframe widget; the portal loads the BridgerPay launcher with
                # api_key / cashier_key / cashier_token to render it.
                return {"ok": True, "cashier": {"cashier_token": ctok, "cashier_key": c.get("cashier_key", ""),
                        "api_key": c.get("api_key", ""), "launcher": "https://checkout.bridgerpay.com/v2/launcher"},
                        "gateway_ref": str(res.get("id") or ""), "kind": "cashier", "raw": d}
            return {"ok": False, "error": f"BridgerPay session failed ({code})", "raw": d}
    except Exception as e:
        return {"ok": False, "error": f"{LABELS.get(gw, gw)} request failed: {str(e)[:140]}"}
    return {"ok": False, "error": "Unknown gateway"}


# ───────────────────────────── webhook verify + parse ─────────────────────────────
def verify_webhook(gw, headers, raw_body: bytes) -> bool:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    body = raw_body if isinstance(raw_body, bytes) else (raw_body or "").encode()
    if gw in _OV_KEYMAP:
        # Ovadot: X-Ovadot-Signature: sha256=<HMAC_SHA256(body, webhookSecret || apiKey)>
        sig = (h.get("x-ovadot-signature") or "").split("=", 1)[-1].strip()
        secret = _OV.get("webhook_secret") or _ov_apikey(gw)
        if not secret:
            return False
        calc = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, calc)
    c = _cfg(gw)
    if not c:
        return False
    if gw == "ptop":
        sig = h.get("the_signature") or h.get("x-signature") or ""
        calc = hmac.new(c.get("secret_key", "").encode(), body, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, calc)
    if gw == "paymaxis":
        sig = h.get("signature") or h.get("x-signature") or ""
        key = c.get("signing_key", "")
        if not key:
            return False  # require a signing key to accept paymaxis callbacks
        calc = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, calc)
    if gw == "bridgerpay":
        # BridgerPay postbacks carry a signature; verify against the api_key/secret per their docs.
        sig = h.get("x-signature") or ""
        key = c.get("api_key", "")
        if not key:
            return False
        calc = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, calc)
    return False


def parse_webhook(gw, body: dict) -> dict:
    """Normalize a gateway webhook to {order_id, status, amount, gateway_ref}."""
    b = body or {}
    def _status(s):
        s = str(s or "").lower()
        if s in ("success", "completed", "paid", "approved", "settled", "confirmed", "complete"):
            return "success"
        if s in ("failed", "declined", "rejected", "error", "cancelled", "canceled", "expired"):
            return "failed"
        return "pending"
    if gw in _OV_KEYMAP:
        d = b.get("data") or b.get("payment") or b
        return {"order_id": str(d.get("order_id") or d.get("orderId") or b.get("order_id") or ""),
                "status": _status(d.get("status") or b.get("status") or b.get("event")),
                "amount": float(d.get("amount") or 0) / 100.0,  # Ovadot amounts are cents
                "currency": str(d.get("currency") or d.get("ccy") or b.get("currency") or "").upper(),
                "gateway_ref": str(d.get("payment_id") or d.get("paymentId") or d.get("id") or "")}
    if gw == "ptop":
        return {"order_id": str(b.get("order_id") or ""), "status": _status(b.get("status")),
                "amount": float(b.get("amount") or 0), "gateway_ref": str(b.get("transaction_id") or "")}
    if gw == "paymaxis":
        r = b.get("result") or b
        return {"order_id": str((r.get("customer") or {}).get("referenceId") or r.get("orderId") or r.get("description") or ""),
                "status": _status(r.get("state") or r.get("status")),
                "amount": float(r.get("amount") or 0), "gateway_ref": str(r.get("id") or "")}
    if gw == "bridgerpay":
        r = b.get("data") or b.get("result") or b
        return {"order_id": str(r.get("order_id") or ""), "status": _status(r.get("status") or r.get("state")),
                "amount": float(r.get("amount") or 0), "gateway_ref": str(r.get("id") or "")}
    return {"order_id": "", "status": "pending", "amount": 0, "gateway_ref": ""}
