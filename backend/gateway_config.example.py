"""
gateway_config.example.py — TEMPLATE for the online payment gateways (Paymaxis/USDT-Hero,
BridgerPay, Ptop). Copy to `gateway_config.py` (gitignored) and paste the real credentials.

SAFETY: every gateway is DISABLED until both its credentials are present AND `enabled=True`.
While disabled, /portal/deposit/online returns "method unavailable" and no real money can move.
Turn ONE gateway live at a time, test a small real deposit end-to-end (create → pay → webhook
credits), then enable the next. `sandbox=True` uses the gateway's TEST endpoint where available.
"""

GATEWAYS = {
    # ── Paymaxis (USDT-Hero) — crypto USDT deposits ──────────────────────────
    "paymaxis": {
        "enabled":  False,
        "sandbox":  True,
        "api_key":  "",                       # Authorization header value (merchant API key)
        "signing_key": "",                    # callback/webhook signature key (verify postbacks)
        "base_live":    "https://gateway.paymaxis.com",
        "base_sandbox": "https://gateway-sandbox.paymaxis.com",
        "payment_method": "CRYPTO",           # CRYPTO for USDT
        "currency": "USDT",
    },
    # ── BridgerPay — card processing (cashier widget) ────────────────────────
    "bridgerpay": {
        "enabled":   False,
        "sandbox":   True,
        "api_url":   "https://api.bridgerpay.com",
        "user_name": "",                      # api-login user
        "password":  "",                      # api-login password (from the BridgerPay docs)
        "api_key":   "",                      # merchant api key (in the session-create URL)
        "cashier_key": "",                    # cashier key
        "currency": "USD",
    },
    # ── Ptop ─────────────────────────────────────────────────────────────────
    "ptop": {
        "enabled":   False,
        "sandbox":   True,
        "website_id": "",                     # merchant identifier
        "secret_key": "",                     # private key (also the HMAC webhook key)
        "base_live":    "https://ptop.me/api/v3/payment",
        "base_sandbox": "https://ptop.me/api/test/v3/payment",
        "currency": "USD",
    },
}

# Public base of the CRM (for building return/webhook URLs the gateways call back to).
PUBLIC_BASE = "https://my1.tnfx.co"


# ── Ovadot e-wallet platform — TNFX is a registered merchant; 3 payment types ────────────
# Ovadot is the user's own wallet/exchange (Convex). TNFX has merchant apps there, one per type:
#   ewallet  (ew_live_…)  -> POST /api/payment/create  -> hosted checkout (redirect)
#   crypto   (cx_live_…)  -> POST /api/crypto/deposit/create -> USDT deposit (NOWPayments)
#   qcard    (qc_live_…)  -> POST /api/qcard/session    -> P2P Q-card session (redirect)
# Amounts are sent in USD CENTS. Webhooks: Ovadot posts to PUBLIC_BASE/api/payments/webhook/<gw>
# with header `X-Ovadot-Signature: sha256=HMAC_SHA256(body, webhookSecret || apiKey)`.
OVADOT = {
    "enabled":  False,                        # master switch for the Ovadot integration
    # per-method switches — a method shows in the client portal ONLY when its flag is True.
    # Disabled methods stay configured (admin Payment settings) but are hidden from clients.
    "ewallet_enabled": False,
    "crypto_enabled":  False,
    "qcard_enabled":   False,
    "sandbox":  False,                        # False = prod deployment, True = dev
    "base_live":    "https://glad-dolphin-629.convex.site",
    "base_sandbox": "https://cautious-frog-768.convex.site",
    "checkout_host": "https://ovadot.com",    # where /pay/<id> and /p2p?session= are hosted
    "ewallet_key":  "",                       # ew_live_… merchant key (Ovadot "ewallet" app)
    "crypto_key":   "",                       # cx_live_… merchant key (Ovadot "crypto_exchange" app)
    "qcard_key":    "",                       # qc_live_… merchant key (Ovadot "qcard" app)
    "crypto_currency": "usdttrc20",
    "webhook_secret": "",                     # leave "" to verify webhooks against the apiKey (Ovadot default)
}
