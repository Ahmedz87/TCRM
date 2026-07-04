"""
wati_service.py — thin Wati (WhatsApp Business) send client. GATED.

Sending is OFF until wati_config.enabled is TRUE *and* an api_endpoint + api_token are set.
While off, send() returns a dry echo and touches nothing external — so the whole pipeline can
run end to end (identity, AI reply, CRM auto-actions) without a single real WhatsApp going out.
"""
import requests


def send_message(cfg, phone, message):
    """Send a WhatsApp session message via Wati. cfg = dict from whatsapp_ai.get_config(db) PLUS
    the raw api_token (the router passes it). Returns {sent, dry, detail}."""
    if not cfg.get("enabled") or not cfg.get("api_endpoint") or not cfg.get("_api_token"):
        return {"sent": False, "dry": True, "detail": "Wati not enabled/configured — dry echo (no message sent)"}
    try:
        endpoint = cfg["api_endpoint"].rstrip("/")
        # Wati session-message endpoint shape; exact path is validated on first live test.
        url = f"{endpoint}/api/v1/sendSessionMessage/{phone}"
        r = requests.post(url, params={"messageText": message},
                          headers={"Authorization": cfg["_api_token"]}, timeout=20)
        ok = r.status_code < 300
        return {"sent": ok, "dry": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"sent": False, "dry": False, "detail": str(e)[:200]}
