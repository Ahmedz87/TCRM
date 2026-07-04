"""
captcha.py — Cloudflare Turnstile verification for the registration bot-check.

The secret is read from turnstile_secret.txt (NOT .env — database.py forbids extra keys).
Defaults to Cloudflare's TEST secret (which always passes) so the flow works out of the box;
drop your real secret in turnstile_secret.txt to activate real bot-blocking.
Create a free widget at dash.cloudflare.com → Turnstile (site key -> frontend, secret -> here).
"""
import os
import json
import urllib.parse
import urllib.request

# Cloudflare test keys (always pass) — replace for production
TEST_SECRET = "1x0000000000000000000000000000000AA"
_SECRET_FILE = os.path.join(os.path.dirname(__file__), "turnstile_secret.txt")
_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _secret():
    try:
        with open(_SECRET_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or TEST_SECRET
    except Exception:
        return TEST_SECRET


def using_test_keys():
    return _secret() == TEST_SECRET


def verify(token, ip=None):
    """Return True if the Turnstile token is valid. Fail-open only on a network error."""
    if not token:
        return False
    try:
        body = {"secret": _secret(), "response": token}
        if ip:
            body["remoteip"] = ip
        data = urllib.parse.urlencode(body).encode()
        req = urllib.request.Request(_VERIFY_URL, data=data)
        res = json.loads(urllib.request.urlopen(req, timeout=8).read())
        return bool(res.get("success"))
    except Exception as e:
        print(f"[captcha] verify network error (allowing): {e}", flush=True)
        return True
