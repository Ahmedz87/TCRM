"""
social_ads_router.py — TikTok + Snapchat (+ Meta) ad accounts: Custom Audience sync and
GATED ad-campaign drafting, driven by the CRM's existing Marketing segments.

DESIGN (same simulation-first stance as the rest of the app):
  • CREDENTIALS: stored per-platform in `social_ad_accounts` (NOT in code). OAuth flows mint the
    access/refresh tokens (TikTok + Snap); Meta reuses a long-lived system token.
  • AUDIENCE SYNC = the safe, high-value, NO-SPEND action. We resolve a segment's recipients,
    NORMALISE + SHA-256 hash their email/phone (exactly what the ad platforms require), and upload
    them as a Custom Audience (the seed for lookalikes too). Hashing means raw PII never leaves here.
  • HARD GATE: env `SOCIAL_LIVE_ENABLED=1` AND the platform's creds present. While EITHER is missing,
    every "sync"/"launch" call only WRITES a draft row (dry_run=TRUE) and returns a simulation —
    it never calls the ad platform. So this whole module is inert until the user sends real API
    details and explicitly flips the flag.
  • AD CREATION is draft-only here: campaigns are stored in `social_campaign_drafts` (status='draft').
    Actually pushing a spending campaign live is intentionally a separate, supervised step.

Endpoints (prefix /social, staff auth; OAuth callbacks are public):
  GET  /social/status                      per-platform credential readiness + live flag
  POST /social/{platform}/config           paste creds (tiktok|snap|meta)
  GET  /social/{platform}/oauth/start      consent URL (tiktok|snap)
  GET  /social/{platform}/oauth/callback   PUBLIC — exchange code -> store tokens
  GET  /social/segments                    segments + reachable counts (for the audience picker)
  POST /social/audiences/preview           {platform, segment_key} -> hashed-match counts + sample (NO upload)
  POST /social/audiences/sync              {platform, segment_key, name} -> GATED create (draft unless live)
  GET  /social/audiences                   synced/draft audiences
  POST /social/campaigns/draft             {platform, name, objective, audience_id, daily_budget} -> draft
  GET  /social/campaigns                   campaign drafts
"""
import os
import hashlib
import secrets
import urllib.parse
import json
import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user
# reuse the SAME smart-segment definitions the Marketing section uses
from marketing_router import SEG_BY_KEY, SEGMENTS, _base, _counts

router = APIRouter(prefix="/social", tags=["social-ads"])

PLATFORMS = ("tiktok", "snap", "meta")
BASE_REDIRECT = "https://my1.tnfx.co/api/social"          # + /{platform}/oauth/callback


def _live() -> bool:
    """Master kill-switch. Off by default — nothing is pushed to any ad platform while this is off."""
    return os.getenv("SOCIAL_LIVE_ENABLED", "").strip() in ("1", "true", "True", "yes")


# ─────────────────────────── schema ───────────────────────────
def _ensure(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS social_ad_accounts (
            platform        TEXT PRIMARY KEY,
            client_id       TEXT, client_secret TEXT,
            access_token    TEXT, refresh_token TEXT,
            advertiser_id   TEXT, ad_account_id TEXT, org_id TEXT,
            developer_token TEXT,
            extra           JSONB DEFAULT '{}'::jsonb,
            oauth_state     TEXT,
            token_expires_at TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS social_audiences (
            id           SERIAL PRIMARY KEY,
            platform     TEXT NOT NULL,
            name         TEXT NOT NULL,
            segment_key  TEXT,
            external_id  TEXT,                 -- audience id returned by the platform
            size         INT DEFAULT 0,        -- recipients in the segment
            hashed_count INT DEFAULT 0,        -- rows actually hashed+uploaded
            status       TEXT DEFAULT 'draft', -- draft | synced | failed
            dry_run      BOOLEAN DEFAULT TRUE,
            message      TEXT,
            created_at   TIMESTAMP DEFAULT NOW(),
            last_synced_at TIMESTAMP
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS social_campaign_drafts (
            id           SERIAL PRIMARY KEY,
            platform     TEXT NOT NULL,
            name         TEXT NOT NULL,
            objective    TEXT,
            audience_id  INT,
            daily_budget NUMERIC,
            status       TEXT DEFAULT 'draft',  -- always 'draft' here; going live is supervised
            config       JSONB DEFAULT '{}'::jsonb,
            created_at   TIMESTAMP DEFAULT NOW()
        )"""))
    # seed empty rows so config UPSERTs are simple
    for p in PLATFORMS:
        db.execute(text("INSERT INTO social_ad_accounts (platform) VALUES (:p) ON CONFLICT (platform) DO NOTHING"), {"p": p})
    db.commit()


def _acct(db, platform):
    _ensure(db)
    r = db.execute(text("""SELECT platform, client_id, client_secret, access_token, refresh_token,
                                  advertiser_id, ad_account_id, org_id, developer_token, oauth_state
                           FROM social_ad_accounts WHERE platform=:p"""), {"p": platform}).fetchone()
    if not r:
        return None
    keys = ["platform", "client_id", "client_secret", "access_token", "refresh_token",
            "advertiser_id", "ad_account_id", "org_id", "developer_token", "oauth_state"]
    return dict(zip(keys, r))


# which creds make a platform "ready" to actually push an audience
def _ready(a) -> bool:
    if not a:
        return False
    if a["platform"] == "tiktok":
        return bool(a["access_token"] and a["advertiser_id"])
    if a["platform"] == "snap":
        return bool(a["access_token"] and a["ad_account_id"])
    if a["platform"] == "meta":
        return bool(a["access_token"] and a["ad_account_id"])
    return False


# ─────────────────────────── hashing ───────────────────────────
def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _norm_email(e):
    e = (e or "").strip().lower()
    return e if e and "@" in e else None


def _norm_phone(p):
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    # strip a leading international 00 prefix; keep country code (platforms want E.164 digits, no +)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits if len(digits) >= 8 else None


def _resolve_recipients(db, seg, limit=None):
    """Return [{email_hash, phone_hash}, ...] for a segment, plus totals. Raw PII never leaves here."""
    frm, _alias, em, ph = _base(seg["audience"])
    cap = f"LIMIT {int(limit)}" if limit else ""
    rows = db.execute(text(f"""
        SELECT {em} AS email, {ph} AS phone
        FROM {frm}
        WHERE {seg['where']}
          AND ( ({em} IS NOT NULL AND {em} <> '') OR ({ph} IS NOT NULL AND {ph} <> '') )
        {cap}
    """)).fetchall()
    recs, n_email, n_phone = [], 0, 0
    for email, phone in rows:
        ne, npn = _norm_email(email), _norm_phone(phone)
        if not ne and not npn:
            continue
        rec = {}
        if ne:
            rec["email"] = _sha256(ne); n_email += 1
        if npn:
            rec["phone"] = _sha256(npn); n_phone += 1
        recs.append(rec)
    return recs, {"matched": len(recs), "with_email": n_email, "with_phone": n_phone}


# ─────────────────── platform push (REAL calls, but only reached when live+ready) ───────────────────
def _push_audience(a, name, recs):
    """Dispatch to the platform's Custom Audience upload. Returns (external_id, message).
    These are the real API shapes; they only execute once creds exist AND SOCIAL_LIVE_ENABLED=1,
    so the exact field names get validated on the first supervised live run."""
    p = a["platform"]
    try:
        if p == "tiktok":
            return _tiktok_audience(a, name, recs)
        if p == "snap":
            return _snap_audience(a, name, recs)
        if p == "meta":
            return _meta_audience(a, name, recs)
    except Exception as e:
        return None, f"push error: {str(e)[:180]}"
    return None, "unsupported platform"


def _tiktok_audience(a, name, recs):
    # TikTok Marketing API v1.3 — create a file-based custom audience of hashed emails/phones.
    H = {"Access-Token": a["access_token"], "Content-Type": "application/json"}
    base = "https://business-api.tiktok.com/open_api/v1.3"
    # 1) create the audience shell
    r = requests.post(f"{base}/dmp/custom_audience/create/", headers=H, json={
        "advertiser_id": a["advertiser_id"], "custom_audience_name": name[:55],
        "audience_sub_type": "NORMAL"}, timeout=30).json()
    aid = (r.get("data") or {}).get("custom_audience_id")
    if not aid:
        return None, f"tiktok create failed: {r.get('message')}"
    # 2) push the hashed list (TikTok accepts EMAIL_SHA256 / PHONE_SHA256 calc types)
    emails = [x["email"] for x in recs if "email" in x]
    phones = [x["phone"] for x in recs if "phone" in x]
    for calc, data in (("EMAIL_SHA256", emails), ("PHONE_SHA256", phones)):
        for i in range(0, len(data), 10000):
            requests.post(f"{base}/dmp/custom_audience/update/", headers=H, json={
                "advertiser_id": a["advertiser_id"], "custom_audience_id": aid,
                "action": "APPEND", "calculate_type": calc, "data": data[i:i + 10000]}, timeout=60)
    return str(aid), "tiktok audience created"


def _snap_audience(a, name, recs):
    # Snapchat Marketing API — create a SAM segment then add hashed users.
    H = {"Authorization": f"Bearer {a['access_token']}", "Content-Type": "application/json"}
    base = "https://adsapi.snapchat.com/v1"
    r = requests.post(f"{base}/adaccounts/{a['ad_account_id']}/segments", headers=H, json={
        "segments": [{"name": name[:120], "source_type": "FIRST_PARTY", "retention_in_days": 180}]}, timeout=30).json()
    seg = (((r.get("segments") or [{}])[0]).get("segment") or {})
    sid = seg.get("id")
    if not sid:
        return None, f"snap create failed: {r.get('request_status') or r}"
    ids = [x.get("email") or x.get("phone") for x in recs]
    for i in range(0, len(ids), 100000):
        requests.post(f"{base}/segments/{sid}/users", headers=H, json={
            "users": [{"schema": ["EMAIL_SHA256"], "data": [[v] for v in ids[i:i + 100000]]}]}, timeout=90)
    return str(sid), "snap segment created"


def _meta_audience(a, name, recs):
    # Meta Marketing API — customaudiences + users (SHA256 EMAIL/PHONE).
    base = f"https://graph.facebook.com/v19.0/{a['ad_account_id']}/customaudiences"
    r = requests.post(base, params={"access_token": a["access_token"]}, data={
        "name": name[:80], "subtype": "CUSTOM", "customer_file_source": "USER_PROVIDED_ONLY",
        "description": "CRM segment sync"}, timeout=30).json()
    aid = r.get("id")
    if not aid:
        return None, f"meta create failed: {r.get('error', {}).get('message')}"
    emails = [x["email"] for x in recs if "email" in x]
    for i in range(0, len(emails), 10000):
        requests.post(f"https://graph.facebook.com/v19.0/{aid}/users",
                      params={"access_token": a["access_token"]},
                      json={"schema": "EMAIL_SHA256", "data": [[e] for e in emails[i:i + 10000]]}, timeout=60)
    return str(aid), "meta audience created"


# ─────────────────────────── status / config ───────────────────────────
@router.get("/status")
def status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    out = {}
    for p in PLATFORMS:
        a = _acct(db, p)
        out[p] = {
            "client_id_set": bool(a and a["client_id"]),
            "secret_set": bool(a and a["client_secret"]),
            "token_set": bool(a and a["access_token"]),
            "advertiser_id": a["advertiser_id"] if a else None,
            "ad_account_id": a["ad_account_id"] if a else None,
            "ready": _ready(a),
            "redirect_uri": f"{BASE_REDIRECT}/{p}/oauth/callback",
        }
    return {"live_enabled": _live(), "platforms": out,
            "note": "Audience sync & ad launch are GATED: nothing is pushed to any platform until "
                    "the platform shows ready=true AND live_enabled=true. Preview is always safe."}


@router.post("/{platform}/config")
def set_config(platform: str, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if platform not in PLATFORMS:
        return {"error": "unknown platform"}
    _ensure(db)
    allowed = ("client_id", "client_secret", "access_token", "refresh_token",
               "advertiser_id", "ad_account_id", "org_id", "developer_token")
    fields = {k: payload.get(k) for k in allowed if payload.get(k) is not None}
    if fields:
        sets = ", ".join(f"{k}=:{k}" for k in fields)
        fields["p"] = platform
        db.execute(text(f"UPDATE social_ad_accounts SET {sets}, updated_at=NOW() WHERE platform=:p"), fields)
        db.commit()
    return status(db, user)


# ─────────────────────────── OAuth (tiktok + snap) ───────────────────────────
@router.get("/{platform}/oauth/start")
def oauth_start(platform: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    a = _acct(db, platform)
    if platform not in ("tiktok", "snap"):
        return {"error": "OAuth applies to tiktok/snap; Meta uses a long-lived token via /config."}
    if not a or not a["client_id"]:
        return {"error": "Set client_id + client_secret via /social/{platform}/config first."}
    state = secrets.token_urlsafe(16)
    db.execute(text("UPDATE social_ad_accounts SET oauth_state=:s WHERE platform=:p"),
               {"s": state, "p": platform}); db.commit()
    redirect = f"{BASE_REDIRECT}/{platform}/oauth/callback"
    if platform == "tiktok":
        params = {"app_id": a["client_id"], "redirect_uri": redirect, "state": state}
        return {"auth_url": "https://business-api.tiktok.com/portal/auth?" + urllib.parse.urlencode(params)}
    # snap
    params = {"client_id": a["client_id"], "redirect_uri": redirect, "response_type": "code",
              "scope": "snapchat-marketing-api", "state": state}
    return {"auth_url": "https://accounts.snapchat.com/login/oauth2/authorize?" + urllib.parse.urlencode(params)}


@router.get("/{platform}/oauth/callback")
async def oauth_callback(platform: str, request: Request, db: Session = Depends(get_db)):
    if platform not in ("tiktok", "snap"):
        return HTMLResponse("<h3>Unsupported platform.</h3>", status_code=400)
    code = request.query_params.get("code") or request.query_params.get("auth_code")
    state = request.query_params.get("state")
    a = _acct(db, platform)
    saved = a["oauth_state"] if a else None
    if not code or (saved and state != saved):
        return HTMLResponse("<h3>Invalid OAuth callback (state mismatch or no code).</h3>", status_code=400)
    redirect = f"{BASE_REDIRECT}/{platform}/oauth/callback"
    try:
        if platform == "tiktok":
            r = requests.post("https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/",
                              json={"app_id": a["client_id"], "secret": a["client_secret"],
                                    "auth_code": code, "grant_type": "authorization_code"}, timeout=30).json()
            data = r.get("data") or {}
            tok = data.get("access_token")
            adv = (data.get("advertiser_ids") or [None])[0]
            if not tok:
                return HTMLResponse(f"<h3>TikTok token exchange failed.</h3><pre>{r.get('message')}</pre>", status_code=400)
            db.execute(text("""UPDATE social_ad_accounts SET access_token=:t,
                               advertiser_id=COALESCE(advertiser_id,:adv), oauth_state=NULL, updated_at=NOW()
                               WHERE platform='tiktok'"""), {"t": tok, "adv": str(adv) if adv else None})
        else:  # snap
            r = requests.post("https://accounts.snapchat.com/login/oauth2/access_token", data={
                "client_id": a["client_id"], "client_secret": a["client_secret"],
                "code": code, "grant_type": "authorization_code", "redirect_uri": redirect}, timeout=30).json()
            tok, rt = r.get("access_token"), r.get("refresh_token")
            if not tok:
                return HTMLResponse(f"<h3>Snap token exchange failed.</h3><pre>{r}</pre>", status_code=400)
            db.execute(text("""UPDATE social_ad_accounts SET access_token=:t, refresh_token=COALESCE(:rt,refresh_token),
                               oauth_state=NULL, updated_at=NOW() WHERE platform='snap'"""), {"t": tok, "rt": rt})
        db.commit()
        return HTMLResponse(f"<h2>✅ {platform.title()} connected.</h2><p>Token stored. You can close this tab.</p>")
    except Exception as e:
        return HTMLResponse(f"<h3>Token exchange error: {str(e)[:200]}</h3>", status_code=500)


# ─────────────────────────── segments (audience picker) ───────────────────────────
@router.get("/segments")
def segments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    out = []
    for s in SEGMENTS:
        try:
            c = _counts(db, s)
        except Exception:
            db.rollback(); c = {"total": 0, "reach_email": 0, "reach_whatsapp": 0}
        out.append({"key": s["key"], "label": s["label"], "audience": s["audience"], "desc": s["desc"],
                    "total": c["total"], "reach_email": c["reach_email"], "reach_phone": c["reach_whatsapp"]})
    return {"segments": out}


# ─────────────────────────── audiences ───────────────────────────
@router.post("/audiences/preview")
def audience_preview(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    seg = SEG_BY_KEY.get(payload.get("segment_key"))
    if not seg:
        return {"error": "unknown segment_key"}
    recs, stats = _resolve_recipients(db, seg)
    sample = [{k: v[:12] + "…" for k, v in r.items()} for r in recs[:3]]   # truncated hashes, never raw PII
    return {"segment": seg["label"], **stats, "sample_hashes": sample,
            "note": "Emails/phones are SHA-256 hashed before they ever leave the CRM. Preview uploads nothing."}


@router.post("/audiences/sync")
def audience_sync(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    platform = payload.get("platform")
    seg = SEG_BY_KEY.get(payload.get("segment_key"))
    if platform not in PLATFORMS:
        return {"error": "unknown platform"}
    if not seg:
        return {"error": "unknown segment_key"}
    name = (payload.get("name") or f"TNFX · {seg['label']}").strip()[:120]
    a = _acct(db, platform)
    recs, stats = _resolve_recipients(db, seg)

    gated = (not _live()) or (not _ready(a))
    if gated:
        reason = "live flag off" if not _live() else "platform not connected (missing credentials)"
        db.execute(text("""INSERT INTO social_audiences
            (platform,name,segment_key,size,hashed_count,status,dry_run,message)
            VALUES (:p,:n,:k,:sz,:hc,'draft',TRUE,:m)"""),
            {"p": platform, "n": name, "k": seg["key"], "sz": stats["matched"],
             "hc": stats["matched"], "m": f"DRY-RUN ({reason}) — nothing uploaded"})
        db.commit()
        return {"ok": True, "dry_run": True, "platform": platform, "audience": name,
                "would_upload": stats["matched"], **stats,
                "message": f"Simulated — {reason}. {stats['matched']:,} hashed contacts ready to upload "
                           f"the moment {platform} is connected and the live flag is on."}

    # LIVE path — creds present and flag on
    ext, msg = _push_audience(a, name, recs)
    ok = ext is not None
    db.execute(text("""INSERT INTO social_audiences
        (platform,name,segment_key,external_id,size,hashed_count,status,dry_run,message,last_synced_at)
        VALUES (:p,:n,:k,:e,:sz,:hc,:st,FALSE,:m,NOW())"""),
        {"p": platform, "n": name, "k": seg["key"], "e": ext, "sz": stats["matched"],
         "hc": stats["matched"], "st": "synced" if ok else "failed", "m": msg})
    db.commit()
    return {"ok": ok, "dry_run": False, "platform": platform, "audience": name,
            "external_id": ext, "uploaded": stats["matched"], "message": msg}


@router.get("/audiences")
def list_audiences(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    rows = db.execute(text("""SELECT id,platform,name,segment_key,external_id,size,status,dry_run,
                                     message,created_at,last_synced_at
                              FROM social_audiences ORDER BY id DESC LIMIT 200""")).fetchall()
    return {"audiences": [dict(zip(
        ["id", "platform", "name", "segment_key", "external_id", "size", "status", "dry_run",
         "message", "created_at", "last_synced_at"], r)) for r in rows]}


# ─────────────────────────── campaign drafts (draft-only; going live is supervised) ───────────────────────────
@router.post("/campaigns/draft")
def campaign_draft(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    platform = payload.get("platform")
    if platform not in PLATFORMS:
        return {"error": "unknown platform"}
    _ensure(db)
    db.execute(text("""INSERT INTO social_campaign_drafts
        (platform,name,objective,audience_id,daily_budget,status,config)
        VALUES (:p,:n,:o,:aud,:b,'draft',CAST(:c AS jsonb))"""),
        {"p": platform, "n": (payload.get("name") or "Untitled campaign")[:120],
         "o": payload.get("objective") or "CONVERSIONS", "aud": payload.get("audience_id"),
         "b": payload.get("daily_budget"), "c": json.dumps(payload.get("config") or {})})
    db.commit()
    return {"ok": True, "status": "draft",
            "note": "Saved as a DRAFT. Launching a live (spending) campaign is a separate supervised step."}


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    rows = db.execute(text("""SELECT id,platform,name,objective,audience_id,daily_budget,status,created_at
                              FROM social_campaign_drafts ORDER BY id DESC LIMIT 200""")).fetchall()
    return {"campaigns": [dict(zip(
        ["id", "platform", "name", "objective", "audience_id", "daily_budget", "status", "created_at"], r))
        for r in rows]}
