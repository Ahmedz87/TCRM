"""
google_oauth_router.py — one-time Google OAuth2 flow to mint a REFRESH TOKEN for the Google Ads
API (historical leads + spend/ROAS reporting).

Flow:
  1) You create an OAuth client (Web application) in Google Cloud and register the redirect URI:
        https://my1.tnfx.co/api/oauth/google/callback
  2) Paste the Client ID + Client Secret via POST /oauth/google/config (or the Marketing UI).
  3) Open GET /oauth/google/start -> redirects to Google consent -> Google redirects back to
     /oauth/google/callback?code=... -> we exchange it for tokens and STORE the refresh_token.
Once the refresh token is stored, the Google Ads API client can run unattended.

Stores everything in google_ads_oauth (1 row). Seeded with the developer token + account IDs
already provided. NOTHING here calls the Ads API yet — it only obtains the credentials.
"""
import secrets
import urllib.parse
import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/oauth/google", tags=["google-oauth"])

REDIRECT_URI = "https://my1.tnfx.co/api/oauth/google/callback"
SCOPE = "https://www.googleapis.com/auth/adwords"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _ensure(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS google_ads_oauth (
            id INT PRIMARY KEY DEFAULT 1,
            client_id TEXT, client_secret TEXT, refresh_token TEXT,
            developer_token TEXT, customer_id TEXT, login_customer_id TEXT,
            oauth_state TEXT, updated_at TIMESTAMP DEFAULT NOW()
        )"""))
    # seed with the values already provided (dev token + account/MCC ids)
    db.execute(text("""
        INSERT INTO google_ads_oauth (id, developer_token, customer_id, login_customer_id)
        VALUES (1, '2kNY_Ci4g6NSTZYUiMmHGg', '7525926739', '4488076607')
        ON CONFLICT (id) DO NOTHING
    """))
    db.commit()


def _cfg(db):
    _ensure(db)
    r = db.execute(text("""SELECT client_id, client_secret, refresh_token, developer_token,
                                  customer_id, login_customer_id FROM google_ads_oauth WHERE id=1""")).fetchone()
    return {"client_id": r[0], "client_secret": r[1], "refresh_token": r[2], "developer_token": r[3],
            "customer_id": r[4], "login_customer_id": r[5]}


@router.get("/status")
def status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    c = _cfg(db)
    return {"redirect_uri": REDIRECT_URI,
            "client_id_set": bool(c["client_id"]), "client_secret_set": bool(c["client_secret"]),
            "refresh_token_set": bool(c["refresh_token"]),
            "developer_token_set": bool(c["developer_token"]),
            "customer_id": c["customer_id"], "login_customer_id": c["login_customer_id"],
            "ready": bool(c["client_id"] and c["client_secret"] and c["refresh_token"] and c["developer_token"])}


@router.post("/config")
def set_config(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Paste Client ID + Client Secret (and optionally override IDs/dev token)."""
    _ensure(db)
    fields = {k: payload.get(k) for k in ("client_id", "client_secret", "developer_token",
                                          "customer_id", "login_customer_id") if payload.get(k)}
    if fields:
        sets = ", ".join(f"{k}=:{k}" for k in fields)
        db.execute(text(f"UPDATE google_ads_oauth SET {sets}, updated_at=NOW() WHERE id=1"), fields)
        db.commit()
    return status(db, user)


@router.get("/start")
def start(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Returns the Google consent URL to open (offline access -> refresh token)."""
    c = _cfg(db)
    if not c["client_id"]:
        return {"error": "Set the OAuth Client ID + Secret first (POST /oauth/google/config)."}
    state = secrets.token_urlsafe(16)
    db.execute(text("UPDATE google_ads_oauth SET oauth_state=:s WHERE id=1"), {"s": state})
    db.commit()
    params = {"client_id": c["client_id"], "redirect_uri": REDIRECT_URI, "response_type": "code",
              "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state}
    return {"auth_url": f"{AUTH_URL}?{urllib.parse.urlencode(params)}"}


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """PUBLIC — Google redirects here with ?code=... We exchange it for a refresh token."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    err = request.query_params.get("error")
    if err:
        return HTMLResponse(f"<h3>Google authorization failed: {err}</h3>", status_code=400)
    c = _cfg(db)
    saved_state = db.execute(text("SELECT oauth_state FROM google_ads_oauth WHERE id=1")).scalar()
    if not code or (saved_state and state != saved_state):
        return HTMLResponse("<h3>Invalid OAuth callback (state mismatch or no code).</h3>", status_code=400)
    try:
        r = requests.post(TOKEN_URL, data={
            "code": code, "client_id": c["client_id"], "client_secret": c["client_secret"],
            "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"}, timeout=20)
        tok = r.json()
        rt = tok.get("refresh_token")
        if not rt:
            return HTMLResponse(f"<h3>No refresh token returned.</h3><pre>{tok}</pre>"
                                "<p>Tip: remove the app from your Google Account's third-party access "
                                "and try again so Google re-issues a refresh token.</p>", status_code=400)
        db.execute(text("UPDATE google_ads_oauth SET refresh_token=:rt, oauth_state=NULL, updated_at=NOW() WHERE id=1"),
                   {"rt": rt})
        db.commit()
        return HTMLResponse("<h2>✅ Google Ads connected.</h2><p>Refresh token stored. You can close "
                            "this tab — the CRM can now pull Google leads & ad data.</p>")
    except Exception as e:
        return HTMLResponse(f"<h3>Token exchange error: {str(e)[:200]}</h3>", status_code=500)
