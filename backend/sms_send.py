"""
sms_send.py — pluggable SMS sender for phone OTP. Config in sms_config.py (gitignored).

Supports a generic templated HTTP gateway (works with most regional/Twilio-style HTTP APIs).
Until configured it logs and returns False, so the OTP flow stays on the dev 0000 code.

To enable, create backend/sms_config.py, e.g.:

    SMS_URL    = "https://gateway.example.com/api/send"
    SMS_METHOD = "GET"            # or "POST"
    SMS_JSON   = False            # POST body as JSON vs form-encoded
    SMS_HEADERS = {}              # e.g. {"Authorization": "Basic <base64>"}
    SMS_PARAMS = {"username": "u", "password": "p", "sender": "TNFX",
                  "to": "{phone}", "text": "{message}"}   # {phone}/{message} substituted per send
"""
import json
import urllib.parse
import urllib.request


def _infobip_cfg():
    """Infobip provider (preferred). Configure in sms_config.py:
        INFOBIP_BASE   = "w4v9lq.api.infobip.com"   # host only, no scheme
        INFOBIP_KEY    = "<api key>"
        INFOBIP_SENDER = "TNFX"                      # alphanumeric sender / number
    """
    try:
        import sms_config as c
        base = getattr(c, "INFOBIP_BASE", "")
        key = getattr(c, "INFOBIP_KEY", "")
        if not base or not key:
            return None
        host = base.replace("https://", "").replace("http://", "").rstrip("/")
        return {"host": host, "key": key, "sender": getattr(c, "INFOBIP_SENDER", "TNFX")}
    except Exception:
        return None


def _cfg():
    try:
        import sms_config as c
        if not getattr(c, "SMS_URL", ""):
            return None
        return {
            "url": c.SMS_URL, "method": getattr(c, "SMS_METHOD", "GET").upper(),
            "json": bool(getattr(c, "SMS_JSON", False)),
            "headers": dict(getattr(c, "SMS_HEADERS", {}) or {}),
            "params": dict(getattr(c, "SMS_PARAMS", {}) or {}),
        }
    except Exception:
        return None


def configured():
    return _infobip_cfg() is not None or _cfg() is not None


def _send_infobip(ic, phone, message):
    to = (phone or "").replace(" ", "").replace("-", "").lstrip("+")
    body = json.dumps({"messages": [{
        "destinations": [{"to": to}],
        "from": ic["sender"],
        "text": message or "",
    }]}).encode()
    req = urllib.request.Request(
        f"https://{ic['host']}/sms/2/text/advanced",
        data=body, method="POST",
        headers={
            "Authorization": f"App {ic['key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.loads(r.read() or b"{}")
    # Inspect the per-message status instead of blindly returning True. Infobip accepts the
    # request (HTTP 200) even when it will REJECT delivery (e.g. unfunded account, sender ID not
    # registered for the destination country) — returning True there masked the real failure and
    # made the OTP flow report false success. Treat the REJECTED status group as a failure; log
    # the messageId + status (no message text / no OTP) so delivery problems are traceable.
    msg = (resp.get("messages") or [{}])[0]
    st = msg.get("status", {}) or {}
    group = (st.get("groupName") or "").upper()
    mid = msg.get("messageId")
    print(f"[sms] infobip to={to} messageId={mid} status={group}/{st.get('name')}", flush=True)
    if group == "REJECTED":
        return False
    return True


def send(phone, message):
    ic = _infobip_cfg()
    if ic:
        try:
            return _send_infobip(ic, phone, message)
        except Exception as e:
            print(f"[sms] infobip send failed to {phone}: {e}", flush=True)
            return False
    c = _cfg()
    if not c:
        print(f"[sms] (not configured) would send to {phone}: {message}", flush=True)
        return False
    try:
        def sub(v):
            return str(v).replace("{phone}", phone or "").replace("{message}", message or "")
        params = {k: sub(v) for k, v in c["params"].items()}
        if c["method"] == "POST":
            if c["json"]:
                data = json.dumps(params).encode()
                headers = {**c["headers"], "Content-Type": "application/json"}
            else:
                data = urllib.parse.urlencode(params).encode()
                headers = {**c["headers"], "Content-Type": "application/x-www-form-urlencoded"}
            req = urllib.request.Request(c["url"], data=data, headers=headers, method="POST")
        else:
            url = c["url"] + ("&" if "?" in c["url"] else "?") + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=c["headers"], method="GET")
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return True
    except Exception as e:
        print(f"[sms] send failed to {phone}: {e}", flush=True)
        return False
