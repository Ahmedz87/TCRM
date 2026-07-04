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


def delete_account(login):
    return _post(f"/provision/delete/{int(login)}")


def set_password(login, password, kind="master"):
    """kind = 'master' | 'investor'."""
    return _post(f"/provision/password/{int(login)}", {"password": password, "kind": kind})


def set_leverage(login, leverage):
    return _post(f"/provision/leverage/{int(login)}", {"leverage": int(leverage)})
