"""
yeastar_service.py — Yeastar P-Series Cloud PBX integration (click-to-call).

Credentials live in yeastar_config.py (GITIGNORED — not in version control), because
database.py Settings (pydantic) FORBIDS extra .env keys so YEASTAR_* in .env would crash the
backend. Same local-secrets-file pattern as meta_config.py / db_config.py. If the PBX app
credentials are rotated, update yeastar_config.py (copy yeastar_config.example.py to start).

The OpenAPI access_token expires every 30 min; this module caches it in-process and refreshes
via the long-lived (24h) refresh_token, falling back to a fresh get_token on any error.
Thread-safe (uvicorn runs requests on a thread pool).
"""
import json
import ssl
import time
import threading
import urllib.request
import urllib.error
from yeastar_config import PBX_HOST, CLIENT_ID, CLIENT_SECRET

DEFAULT_CALLER_EXT = "101"          # used when the agent has no extension configured

BASE_URL = f"https://{PBX_HOST}"

# the RAS cloud cert chain isn't in the local trust store; the API is auth-token gated anyway.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_lock = threading.Lock()
_token = None
_token_exp = 0.0        # epoch seconds when the access_token expires
_refresh = None
_refresh_exp = 0.0


def _http(path, data=None, token=None):
    """POST (if data) or GET a JSON OpenAPI call. Returns parsed dict (or {'error':...})."""
    url = f"{BASE_URL}{path}"
    if token:
        url += f"?access_token={token}"
    headers = {"User-Agent": "OpenAPI"}
    body = None
    method = "GET"
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, context=_CTX, timeout=12)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return {"errcode": e.code, "errmsg": e.read().decode()}
        except Exception:
            return {"errcode": e.code, "errmsg": "HTTPError"}
    except Exception as e:
        return {"errcode": -1, "errmsg": str(e)}


def _fresh_token():
    """Full credential login -> access + refresh tokens."""
    return _http("/openapi/v1.0/get_token", {
        "username": CLIENT_ID,
        "password": CLIENT_SECRET,
    })


def _refresh_token():
    """Exchange the refresh_token for a new access_token (cheaper than a full login)."""
    return _http("/openapi/v1.0/refresh_token", {"refresh_token": _refresh})


def _store(res):
    """Persist tokens + expiries from a get_token / refresh_token response. Returns True on success."""
    global _token, _token_exp, _refresh, _refresh_exp
    if not isinstance(res, dict) or res.get("errcode") != 0 or not res.get("access_token"):
        return False
    now = time.time()
    _token = res["access_token"]
    # renew 60s early to avoid using a just-expired token mid-flight
    _token_exp = now + max(60, int(res.get("access_token_expire_time", 1800))) - 60
    if res.get("refresh_token"):
        _refresh = res["refresh_token"]
        _refresh_exp = now + max(60, int(res.get("refresh_token_expire_time", 86400))) - 60
    return True


def _ensure_token():
    """Return a valid access_token, refreshing/logging-in as needed. None on failure."""
    global _token
    with _lock:
        now = time.time()
        if _token and now < _token_exp:
            return _token
        # try a refresh first if we still have a live refresh_token
        if _refresh and now < _refresh_exp and _store(_refresh_token()):
            return _token
        # otherwise full login
        if _store(_fresh_token()):
            return _token
        return None


def dial(callee, caller=None):
    """
    Place a click-to-call: ring `caller` (agent extension) first, then connect to `callee`.
    Returns the raw PBX response dict; errcode == 0 means accepted.
    Retries once with a fresh token if the PBX reports an auth error.
    """
    # Normalise to what the Yeastar outbound route accepts: it will NOT dial a "+"
    # (E.164) number — it needs the international access prefix "00" instead.
    #   +9647...  ->  009647...     9647... -> 009647...     009647... -> unchanged
    raw = "".join(ch for ch in str(callee or "") if ch.isdigit() or ch == "+")
    digits = raw.lstrip("+")
    if not digits:
        return {"errcode": -1, "errmsg": "no callee number"}
    callee = digits if digits.startswith("00") else ("00" + digits)
    caller = (str(caller).strip() if caller else "") or DEFAULT_CALLER_EXT

    tok = _ensure_token()
    if not tok:
        return {"errcode": -1, "errmsg": "could not obtain PBX token"}
    payload = {"caller": caller, "callee": callee}
    res = _http("/openapi/v1.0/call/dial", payload, token=tok)
    # auth-ish failures -> force a fresh token and retry once
    if isinstance(res, dict) and res.get("errcode") not in (0, None):
        msg = str(res.get("errmsg", "")).lower()
        if res.get("errcode") in (10003, 10005, 401) or "token" in msg:
            with _lock:
                _store(_fresh_token())
                tok2 = _token
            if tok2:
                res = _http("/openapi/v1.0/call/dial", payload, token=tok2)
    return res


def list_extensions():
    """Return [{number, name, id}] for the configured PBX (for an extension picker)."""
    tok = _ensure_token()
    if not tok:
        return []
    res = _http("/openapi/v1.0/extension/list", token=tok)
    out = []
    for e in (res.get("data") or []):
        out.append({
            "number": e.get("number") or e.get("ext_number") or "",
            "name": e.get("caller_id_name") or e.get("name") or "",
            "id": e.get("id"),
        })
    return out
