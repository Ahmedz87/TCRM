import portal_router
import admin_payments_router
import agent_assign_router
import markup_router
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import models
from routers import auth_router, clients_router, neg_cover_router, notifications_router
from trading_accounts_router import router as trading_accounts_router
from ib_router import router as ib_router
from agents_router import router as agents_router
from transactions_router import router as transactions_router
from client_email_router import router as client_email_router
from settings_router import router as settings_router
from dashboard_router import router as dashboard_router
from network_router import router as network_router
from abuse_router import router as abuse_router
from retention_router import router as retention_router
from loyalty_router import router as loyalty_router
from commission_router import router as commission_router
from hedge_router import router as hedge_router
from leads_router import router as leads_router, client_router
from users_router import router as users_router
from training_router import router as training_router
from power_dialer_router import router as dialer_router
from ib_profiles_router import router as ib_profiles_router
from meta_capi_router import router as meta_router
from chat_router import router as chat_router
from autochartist_router import router as autochartist_router
from deposit_docs_router import router as deposit_docs_router

Base.metadata.create_all(bind=engine)

# ── ERROR TRACKING (P0, Jul 16) ──────────────────────────────────────────────
# Sentry activates ONLY if SENTRY_DSN is set in the env (add a free Sentry project + DSN to turn
# it on — nothing to change in code). Independent of Sentry, a global exception handler below
# captures every unhandled 500 with the full traceback + who/where, into backend/logs/errors.log,
# and fires an optional Telegram/webhook alert (ALERT_WEBHOOK env) so a broken deposit/withdraw
# pages someone instead of dying silently in a per-instance uvicorn log.
import os as _os_err, traceback as _tb, datetime as _dt_err, json as _json_err, urllib.request as _url_err
_SENTRY_DSN = _os_err.getenv("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_SENTRY_DSN, traces_sample_rate=0.0, environment="prod",
                        send_default_pii=False)
        print("[startup] Sentry error tracking ON", flush=True)
    except Exception as _e:
        print(f"[startup] Sentry init failed: {_e}", flush=True)

app = FastAPI(title="Broker CRM API", version="1.0.0")


@app.exception_handler(Exception)
async def _global_error_handler(request, exc):
    """Never leak a stack trace to the client; always capture it server-side + alert."""
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as _StarletteHTTPExc
    from fastapi.exceptions import RequestValidationError as _ReqValErr
    # let FastAPI's normal handlers own HTTP + validation errors (401/403/404/422 etc.)
    if isinstance(exc, (_StarletteHTTPExc, _ReqValErr)):
        raise exc
    try:
        who = request.headers.get("authorization", "")[:16]
        line = (f"{_dt_err.datetime.utcnow().isoformat()}Z  {request.method} {request.url.path}  "
                f"auth={who}...  {type(exc).__name__}: {exc}\n{_tb.format_exc()}\n{'-'*70}\n")
        _os_err.makedirs(r"C:\broker-crm\backend\logs", exist_ok=True)
        with open(r"C:\broker-crm\backend\logs\errors.log", "a", encoding="utf-8") as _f:
            _f.write(line)
        hook = _os_err.getenv("ALERT_WEBHOOK", "").strip()   # e.g. a Telegram sendMessage URL
        if hook:
            try:
                body = _json_err.dumps({"text": f"🔴 CRM 500 {request.method} {request.url.path}: "
                                                 f"{type(exc).__name__}: {str(exc)[:200]}"}).encode()
                _url_err.urlopen(_url_err.Request(hook, data=body,
                    headers={"Content-Type": "application/json"}), timeout=4)
            except Exception:
                pass
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
async def _tune_concurrency():
    """Raise the worker threadpool. FastAPI runs every sync (`def`) endpoint AND every
    BackgroundTask in this pool; the default is only 40, so a burst of registrations (each doing a
    DB write + a background email/SMS) or a few KYC OCR jobs would starve every other request and
    make the whole CRM feel slow. 160 gives plenty of headroom for ~100 concurrent sign-ups."""
    try:
        from anyio import to_thread
        to_thread.current_default_thread_limiter().total_tokens = 160
    except Exception as e:
        print(f"[startup] could not raise threadpool: {e}", flush=True)
    # durable job queue: make sure the `jobs` table exists so in-transaction enqueues (bonus MT
    # credits, provisioning) never fail on a fresh DB. Idempotent; cheap.
    try:
        import job_queue
        from database import SessionLocal
        _d = SessionLocal()
        try:
            job_queue.ensure_schema(_d)
        finally:
            _d.close()
    except Exception as e:
        print(f"[startup] could not ensure jobs table: {e}", flush=True)

# NOTE: GZipMiddleware was tried here but it is INCOMPATIBLE with the existing cache_util
# BaseHTTPMiddleware (Starlette issue) — it blanked out responses app-wide (admin showed zeros,
# portal couldn't load documents). Reverted. nginx already gzips responses to the browser anyway.
# CORS: pin to the real site origin. A wildcard "*" combined with allow_credentials=True let
# ANY website make credentialed cross-origin calls to this API on a logged-in user's behalf.
# The frontend, portal and API are all served from https://my1.tnfx.co (same origin via nginx),
# so browser requests are same-origin anyway; these entries cover dev + any direct-origin call.
ALLOWED_ORIGINS = [
    "https://my1.tnfx.co",
    "http://localhost:3000",   # CRA dev server (frontend)
    "http://localhost:3001",   # CRA dev server (portal)
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app-wide response cache: pages load instantly, auto-refresh on TTL, flush on writes
from cache_util import install_cache
install_cache(app, ttl=45)

# staff "View as" impersonation is READ-ONLY: block writes made with an impersonation token
from impersonation_guard import ReadOnlyImpersonationMiddleware
app.add_middleware(ReadOnlyImpersonationMiddleware)


# Lightweight client-side error sink: the frontend ChunkErrorBoundary POSTs uncaught render
# errors here so we can see the REAL exception (message + page + role) server-side instead of
# guessing from a screenshot. Appends one JSON line to backend/client_errors.log.
@app.post("/client-error")
async def _client_error(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        import json as _json, time as _time, os as _os
        rec = {
            "ts": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "page": str(body.get("page", ""))[:80],
            "role": str(body.get("role", ""))[:40],
            "msg": str(body.get("message", ""))[:500],
            "stack": str(body.get("stack", ""))[:1500],
            "ua": request.headers.get("user-agent", "")[:200],
        }
        with open(_os.path.join(_os.path.dirname(__file__), "client_errors.log"), "a", encoding="utf-8") as fh:
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[client-error] could not log: {e}", flush=True)
    return {"ok": True}

app.include_router(auth_router.router)
app.include_router(clients_router.router)
app.include_router(neg_cover_router.router)
app.include_router(notifications_router.router)
app.include_router(trading_accounts_router)
app.include_router(ib_router)
import ib_portal_auth
app.include_router(ib_portal_auth.router)   # partner1.tnfx.co IB portal auth
import ib_referral
app.include_router(ib_referral.router)      # /r/<code> referral hop (30-day cookie + click log)
import ib_portal_extras
app.include_router(ib_portal_extras.router)   # notifications, statement, sub-IB, profile
app.include_router(ib_portal_extras.padmin)   # admin IB-requests queue
app.include_router(ib_portal_extras.pub)      # /ib-agreement (no prefix)
# serve uploaded IB profile photos (nginx strips /api → /ib-photos)
import os as _os
from fastapi.staticfiles import StaticFiles as _SF
_os.makedirs(ib_portal_extras.UPLOAD_DIR, exist_ok=True)
app.mount("/ib-photos", _SF(directory=ib_portal_extras.UPLOAD_DIR), name="ib_photos")
app.include_router(agents_router)
app.include_router(training_router)
app.include_router(transactions_router)
app.include_router(client_email_router)
app.include_router(settings_router)
app.include_router(dashboard_router)
app.include_router(network_router)
app.include_router(abuse_router)
app.include_router(retention_router)
app.include_router(loyalty_router)
app.include_router(commission_router)
app.include_router(deposit_docs_router)
app.include_router(portal_router.router)
import payment_cards_router  # company manual-payment cards + AI deposit-proof fraud checks
app.include_router(payment_cards_router.admin)
app.include_router(payment_cards_router.portal)
import payment_gateway_router  # online gateways: Paymaxis(USDT)/BridgerPay/Ptop (gated by gateway_config.py)
app.include_router(payment_gateway_router.portal)
app.include_router(payment_gateway_router.public)
app.include_router(admin_payments_router.router)
app.include_router(agent_assign_router.router)
app.include_router(markup_router.router)
app.include_router(hedge_router)
app.include_router(leads_router)
app.include_router(client_router)
app.include_router(users_router)
app.include_router(dialer_router)
app.include_router(ib_profiles_router)
app.include_router(meta_router)
app.include_router(chat_router)
app.include_router(autochartist_router)
from registration_router import router as registration_router
app.include_router(registration_router)
from copy_router import portal_copy, admin_copy
app.include_router(portal_copy)
app.include_router(admin_copy)
from bonus_router import portal_bonus, admin_bonus
app.include_router(portal_bonus)
app.include_router(admin_bonus)
from tickets_router import tickets_admin, tickets_portal
app.include_router(tickets_admin)
app.include_router(tickets_portal)
from password_reset_router import router as password_reset_router
app.include_router(password_reset_router)
from reports_router import router as reports_router
app.include_router(reports_router)
from finance_router import router as finance_router
app.include_router(finance_router)
from lead_rules_router import router as lead_rules_router
app.include_router(lead_rules_router)
from marketing_router import router as marketing_router
app.include_router(marketing_router)
from kyc_admin_router import router as kyc_admin_router
app.include_router(kyc_admin_router)
from wati_router import router as wati_router
app.include_router(wati_router)
from wati_broadcast import router as wati_broadcast_router
app.include_router(wati_broadcast_router)
from drip_router import router as drip_router
app.include_router(drip_router)
from google_leads_router import router as google_leads_router
app.include_router(google_leads_router)
from google_oauth_router import router as google_oauth_router
app.include_router(google_oauth_router)
from transfer_router import router as transfer_router
app.include_router(transfer_router)
from search_router import router as search_router
app.include_router(search_router)
from score_rules_router import router as score_rules_router
app.include_router(score_rules_router)
from social_ads_router import router as social_ads_router
app.include_router(social_ads_router)
from monthly_report_router import router as monthly_report_router
app.include_router(monthly_report_router)
from admin_ai_chat import router as admin_ai_chat_router
app.include_router(admin_ai_chat_router)
from call_qa_router import router as call_qa_router
app.include_router(call_qa_router)

from aml_router import router as aml_router
app.include_router(aml_router)

@app.get("/")
def root():
    return {"message": "Broker CRM API is running!"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/health/full")
def health_full():
    """Deep check used by the watchdog: confirms the DB is reachable, not just that the
    process is listening (catches a hung/poisoned backend)."""
    from database import SessionLocal
    from sqlalchemy import text as _text
    db = SessionLocal()
    try:
        db.execute(_text("SELECT 1"))
        ok = True
    except Exception:
        ok = False
    finally:
        db.close()
    return {"status": "ok" if ok else "degraded", "db": ok, "version": "1.0.0"}
