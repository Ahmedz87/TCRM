"""
facebook_webhook_router.py  —  Real-time Meta Lead Ads -> broker_crm leads.

Register in main.py:
    from facebook_webhook_router import router as fb_router
    app.include_router(fb_router)

Meta App Dashboard -> Webhooks -> Page -> subscribe to the `leadgen` field, and
point the callback URL at:  https://YOUR_PUBLIC_HOST/leads/facebook-webhook
(the Verify Token you type into Meta must equal META_VERIFY_TOKEN below.)

Flow: Meta POSTs only a leadgen_id -> we call the Graph API to fetch the actual
field data -> map -> insert (de-duped on meta_lead_id, same as the puller).
"""

import os
import db_config
import json
import hmac
import hashlib
import requests
import psycopg2
from psycopg2.extras import execute_values
from fastapi import APIRouter, Request, Response, HTTPException

router = APIRouter()

GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v19.0")
ACCESS_TOKEN  = os.getenv("META_ACCESS_TOKEN", "PASTE_TOKEN_HERE")
APP_SECRET    = os.getenv("META_APP_SECRET",   "PASTE_APP_SECRET_HERE")
VERIFY_TOKEN  = os.getenv("META_VERIFY_TOKEN", "choose_any_string_and_paste_same_in_meta")
LEAD_SOURCE   = "meta_syria"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

DB = dict(
    host=os.getenv("PGHOST", db_config.DB_HOST), port=os.getenv("PGPORT", db_config.DB_PORT),
    dbname=os.getenv("PGDATABASE", db_config.DB_NAME), user=os.getenv("PGUSER", db_config.DB_USER),
    password=os.getenv("PGPASSWORD", db_config.DB_PASSWORD),
)


@router.get("/leads/facebook-webhook")
async def verify(request: Request):
    """Meta's one-time subscription handshake."""
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="verify token mismatch")


@router.post("/leads/facebook-webhook")
async def receive(request: Request):
    raw = await request.body()

    # Verify the payload really came from Meta (signed with your App Secret).
    sig = request.headers.get("X-Hub-Signature-256", "")
    if APP_SECRET and APP_SECRET != "PASTE_APP_SECRET_HERE":
        expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="bad signature")

    body = json.loads(raw or b"{}")
    rows = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            leadgen_id = change.get("value", {}).get("leadgen_id")
            if leadgen_id:
                parsed = _fetch_lead(leadgen_id)
                if parsed:
                    rows.append(parsed)

    if rows:
        _insert(rows)
    # Always 200 quickly, or Meta retries and eventually disables the webhook.
    return {"received": len(rows)}


def _fetch_lead(leadgen_id):
    r = requests.get(f"{GRAPH}/{leadgen_id}",
                     params={"fields": "id,created_time,field_data", "access_token": ACCESS_TOKEN},
                     timeout=15)
    lead = r.json()
    if "error" in lead:
        print("Graph fetch error:", lead["error"])
        return None
    fields = {}
    for f in lead.get("field_data", []):
        fields[f["name"].lower()] = (f.get("values") or [""])[0]

    def fm(*kw):
        return next((v for k, v in fields.items() if any(x in k for x in kw)), "")

    email = fm("email")
    phone = fm("phone", "mobile", "number", "whatsapp")
    name  = fields.get("full_name") or fields.get("name") \
            or f"{fm('first_name')} {fm('last_name')}".strip()
    return (name.strip(), email.strip(), phone.strip(), LEAD_SOURCE,
            lead["id"], lead.get("created_time"), json.dumps(fields))


def _insert(rows):
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO leads (full_name, email, phone, status, source,
                                   meta_lead_id, meta_created, meta_raw)
                VALUES %s
                ON CONFLICT (meta_lead_id) WHERE meta_lead_id IS NOT NULL DO NOTHING
            """, rows, template="(%s,%s,%s,'new',%s,%s,%s,%s)")
        conn.commit()
    finally:
        conn.close()
