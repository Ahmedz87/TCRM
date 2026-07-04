"""
registration_router.py — public client self-registration (from tnfx.co "Register").

Multi-step, fast flow:
  1) name + country + city
  2) phone  -> /check-contact (already-registered? -> login or new) -> /send-otp -> /verify-otp
  3) email  -> same exists-check -> OTP
  4) questionnaire (simple)
  5) choose platform (MT4/MT5) + Islamic/Swap + account type + leverage -> /submit (creates a LEAD)
  6) KYC: choose ID type -> upload required sides + selfie + proof of address (or skip to dashboard)
     -> OCR extracts fields, auto-verifies, network cross-check.

PUBLIC endpoints (no auth) under /register. OTP delivery is pluggable: real SMS + noreply@tnfx.co
email are wired via otp_send() once creds are set; until then it runs in DEV mode (code returned/logged).
Account provisioning on the MT server is done separately (tested first) — submit creates the lead +
a pending registration; the trading account is created & credited after KYC verification.
"""
import os
import re
import json
import random
import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, SessionLocal
from auth import get_current_user
import kyc_engine
import rate_limit

router = APIRouter(prefix="/register", tags=["registration"])


def _limit(request, bucket, limit, window, key=None):
    """Raise 429 if the public caller exceeds `limit` hits per `window` seconds (key = IP by default)."""
    k = key or rate_limit.client_ip(request)
    if not rate_limit.allow(bucket, k, limit, window):
        raise HTTPException(status_code=429, detail="Too many requests — please wait a moment and try again.")

KYC_DIR = r"C:\broker-crm\backend\kyc_uploads"
os.makedirs(KYC_DIR, exist_ok=True)

# document types -> which uploads are required (your doc-type-driven KYC)
DOC_TYPES = {
    "national_id":     {"label": "National ID",      "sides": ["front", "back"]},
    "passport":        {"label": "Passport",         "sides": ["main"]},
    "driving_license": {"label": "Driving License",  "sides": ["front", "back"]},
}

# city dropdowns per country (keys match the frontend COUNTRIES names)
CITIES = {
    "Iraq": ["Baghdad", "Basra", "Mosul", "Erbil", "Najaf", "Karbala", "Kirkuk", "Sulaymaniyah",
             "Nasiriyah", "Amarah", "Diwaniyah", "Kut", "Hillah", "Ramadi", "Fallujah", "Samawah",
             "Baqubah", "Duhok", "Tikrit", "Halabja", "Zakho"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Mecca", "Medina", "Dammam", "Khobar", "Tabuk", "Abha", "Buraydah", "Hail"],
    "United Arab Emirates": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah", "Umm Al Quwain", "Al Ain"],
    "Kuwait": ["Kuwait City", "Hawalli", "Salmiya", "Jahra", "Farwaniya", "Ahmadi", "Fahaheel"],
    "Qatar": ["Doha", "Al Rayyan", "Al Wakrah", "Al Khor", "Umm Salal", "Lusail"],
    "Bahrain": ["Manama", "Riffa", "Muharraq", "Hamad Town", "Isa Town", "Sitra"],
    "Oman": ["Muscat", "Salalah", "Sohar", "Nizwa", "Sur", "Ibri"],
    "Jordan": ["Amman", "Zarqa", "Irbid", "Aqaba", "Salt", "Madaba", "Mafraq"],
    "Lebanon": ["Beirut", "Tripoli", "Sidon", "Tyre", "Jounieh", "Zahle", "Baalbek"],
    "Syria": ["Damascus", "Aleppo", "Homs", "Latakia", "Hama", "Tartus", "Deir ez-Zor"],
    "Palestine": ["Gaza", "Ramallah", "Hebron", "Nablus", "Jenin", "Bethlehem"],
    "Yemen": ["Sana'a", "Aden", "Taiz", "Hodeidah", "Ibb", "Mukalla"],
    "Egypt": ["Cairo", "Alexandria", "Giza", "Port Said", "Suez", "Mansoura", "Tanta", "Asyut", "Luxor", "Aswan"],
    "Turkey": ["Istanbul", "Ankara", "Izmir", "Bursa", "Antalya", "Adana", "Gaziantep", "Konya"],
    "Iran": ["Tehran", "Mashhad", "Isfahan", "Karaj", "Shiraz", "Tabriz", "Ahvaz", "Qom"],
    "United States": ["New York", "Los Angeles", "Chicago", "Houston", "Miami", "Dallas", "Washington", "Detroit"],
    "United Kingdom": ["London", "Birmingham", "Manchester", "Leeds", "Glasgow", "Liverpool", "Bristol"],
    "Canada": ["Toronto", "Montreal", "Vancouver", "Calgary", "Ottawa", "Edmonton", "Windsor"],
    "Germany": ["Berlin", "Munich", "Hamburg", "Cologne", "Frankfurt", "Stuttgart", "Dusseldorf"],
    "France": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Lille", "Bordeaux"],
    "Netherlands": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"],
    "Sweden": ["Stockholm", "Gothenburg", "Malmo", "Uppsala", "Vasteras"],
    "India": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune"],
    "Pakistan": ["Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar"],
    "Bangladesh": ["Dhaka", "Chittagong", "Khulna", "Rajshahi", "Sylhet"],
    "Australia": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"],
    "Malaysia": ["Kuala Lumpur", "George Town", "Ipoh", "Johor Bahru", "Shah Alam"],
    "Indonesia": ["Jakarta", "Surabaya", "Bandung", "Medan", "Semarang"],
    "Nigeria": ["Lagos", "Abuja", "Kano", "Ibadan", "Port Harcourt"],
    "Morocco": ["Casablanca", "Rabat", "Marrakesh", "Fes", "Tangier", "Agadir"],
    "Algeria": ["Algiers", "Oran", "Constantine", "Annaba", "Blida"],
    "Tunisia": ["Tunis", "Sfax", "Sousse", "Kairouan", "Bizerte"],
}

# State/Province -> cities. Iraq has full governorate->city data (each governorate has many cities);
# other countries can be added the same way. When a country has no states here the frontend falls
# back to the flat CITIES list above (City = free choice, no State step).
STATE_CITIES = {
    "Iraq": {
        "Baghdad": ["Baghdad", "Abu Ghraib", "Mahmudiyah", "Taji", "Sadr City", "Kadhimiya", "Tarmiyah"],
        "Basra": ["Basra", "Az Zubayr", "Abu Al-Khaseeb", "Al-Faw", "Al-Qurna", "Shatt Al-Arab", "Safwan"],
        "Nineveh": ["Mosul", "Tal Afar", "Sinjar", "Al-Hamdaniya", "Bashiqa", "Al-Qayyarah"],
        "Erbil": ["Erbil", "Shaqlawa", "Soran", "Koya", "Makhmur", "Choman"],
        "Najaf": ["Najaf", "Kufa", "Al-Mishkhab", "Al-Manathera"],
        "Karbala": ["Karbala", "Ain Al-Tamur", "Al-Hindiya"],
        "Kirkuk": ["Kirkuk", "Hawija", "Daquq", "Dibis"],
        "Sulaymaniyah": ["Sulaymaniyah", "Ranya", "Penjwen", "Chamchamal", "Kalar", "Dukan"],
        "Dhi Qar": ["Nasiriyah", "Suq Al-Shuyukh", "Al-Rifai", "Al-Shatra", "Al-Chibayish"],
        "Maysan": ["Amarah", "Al-Majar Al-Kabir", "Ali Al-Gharbi", "Qal'at Salih", "Al-Kahla"],
        "Al-Qadisiyyah": ["Diwaniyah", "Afak", "Al-Shamiya", "Al-Hamza"],
        "Wasit": ["Kut", "Al-Hayy", "Al-Suwaira", "Al-Numaniyah", "Badra"],
        "Babylon": ["Hillah", "Al-Musayyib", "Al-Mahawil", "Al-Hashimiyah"],
        "Al-Anbar": ["Ramadi", "Fallujah", "Hit", "Haditha", "Al-Qaim", "Rutba", "Anah"],
        "Muthanna": ["Samawah", "Al-Rumaitha", "Al-Khidhir", "Al-Salman"],
        "Diyala": ["Baqubah", "Khanaqin", "Al-Muqdadiyah", "Baladruz", "Khalis"],
        "Dohuk": ["Duhok", "Zakho", "Amadiya", "Semel", "Akre"],
        "Saladin": ["Tikrit", "Samarra", "Balad", "Bayji", "Al-Dujail", "Tuz Khurmatu"],
        "Halabja": ["Halabja", "Khurmal", "Sayid Sadiq"],
    },
}

ACCOUNT_TYPES = ["Standard", "Cent", "Zero", "FIX", "VIP"]
LEVERAGES = ["1:50", "1:100", "1:200", "1:500", "1:1000"]


def _ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            first_name TEXT, last_name TEXT, country TEXT, city TEXT,
            phone TEXT, email TEXT,
            platform TEXT, account_type TEXT, leverage TEXT, islamic BOOLEAN DEFAULT FALSE,
            questionnaire JSONB,
            status TEXT DEFAULT 'pending_kyc',   -- pending_kyc / verified / account_created
            lead_id INT,
            mt_login BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id SERIAL PRIMARY KEY,
            contact TEXT, channel TEXT,           -- phone|email
            code TEXT, expires_at TIMESTAMP,
            verified BOOLEAN DEFAULT FALSE, attempts INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS reg_kyc_documents (
            id SERIAL PRIMARY KEY,
            registration_id INT, lead_id INT,
            doc_type TEXT, side TEXT,             -- front/back/main/selfie/proof_of_address
            file_path TEXT, ocr_json JSONB,
            status TEXT DEFAULT 'uploaded',
            created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS password_hash TEXT"))
    db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS address TEXT"))
    db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS nationality TEXT"))
    db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR"))
    db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS state TEXT"))
    # client login credentials (the client portal authenticates against this)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS client_logins (
            id SERIAL PRIMARY KEY,
            registration_id INT, lead_id INT,
            email TEXT, phone TEXT, password_hash TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.commit()


def _phone9(p):
    d = re.sub(r"[^0-9]", "", p or "")
    return d[-9:] if len(d) >= 9 else d


def otp_send(channel, contact, code):
    """Deliver the OTP. Real SMS / noreply@tnfx.co email plug in here once creds are set.
    Until then: DEV mode — log it and return it so the flow is testable."""
    # TODO: when creds arrive ->
    #   if channel == 'phone': sms_gateway.send(contact, f"Your TNFX code is {code}")
    #   if channel == 'email': smtp_send('noreply@tnfx.co', contact, 'TNFX verification', code)
    print(f"[OTP/{channel}] {contact} -> {code}", flush=True)
    return {"dev_code": code}   # remove dev_code once real delivery is wired


def _deliver_otp(channel, contact, code):
    """Actually send the verification code over email/SMS. Runs in the BACKGROUND (off the request)
    so the 'send code' button returns instantly instead of blocking on the SMTP handshake (~seconds)
    or the SMS gateway. The code is already stored before this runs, so verification works regardless;
    a delivery failure is logged (the user can press resend)."""
    try:
        import email_send, sms_send
        if channel == "email":
            email_send.send(contact, f"Your TNFX verification code: {code}",
                            f"Your TNFX verification code is {code}\n\nIt expires in 10 minutes. "
                            "If you didn't request this, please ignore this email.",
                            body_html=email_send.otp_html(code, "verification", 10))
        else:
            sms_send.send(contact, f"Your TNFX verification code is {code}")
    except Exception as e:
        print(f"[OTP delivery] failed for {channel} {contact}: {e}", flush=True)


# ── lookups ──
@router.get("/states")
def states(country: str = ""):
    """States/Provinces (governorates) for a country, if we have them. Empty => no State step."""
    return {"states": sorted((STATE_CITIES.get(country) or {}).keys())}


@router.get("/cities")
def cities(country: str = "", state: str = ""):
    """Cities for a state (when the country has states), else the country's flat city list."""
    sc = STATE_CITIES.get(country)
    if sc and state:
        return {"cities": sc.get(state, [])}
    if sc:   # country has states but none picked yet -> let the State dropdown drive it
        return {"cities": []}
    return {"cities": CITIES.get(country, [])}


@router.get("/captcha")
def captcha(request: Request, db: Session = Depends(get_db)):
    _limit(request, "captcha", 40, 600)        # 40 / 10 min per IP
    import forex_captcha
    return forex_captcha.generate(db)


@router.get("/options")
def options():
    return {"countries": list(CITIES.keys()), "account_types": ACCOUNT_TYPES,
            "leverages": LEVERAGES, "platforms": ["MT5", "MT4"],
            "doc_types": [{"key": k, **v} for k, v in DOC_TYPES.items()]}


# ── step 2/3: does this phone/email already have an account? ──
@router.post("/check-contact")
def check_contact(data: dict, request: Request, db: Session = Depends(get_db)):
    _limit(request, "check", 60, 60)           # 60 / min per IP (anti-enumeration)
    _ensure_schema(db)
    channel = data.get("channel")            # phone | email
    value = (data.get("value") or "").strip()
    if not value:
        return {"exists": False}
    if channel == "email":
        row = db.execute(text("""
            SELECT 'client' FROM clients WHERE lower(email)=lower(:v)
            UNION SELECT 'lead' FROM leads WHERE lower(email)=lower(:v) LIMIT 1
        """), {"v": value}).fetchone()
    else:
        p9 = _phone9(value)
        row = db.execute(text("""
            SELECT 'client' FROM clients WHERE RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p
            UNION SELECT 'lead' FROM leads WHERE RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p LIMIT 1
        """), {"p": p9}).fetchone()
    return {"exists": bool(row), "found_in": row[0] if row else None}


# ── OTP ──
@router.post("/send-otp")
def send_otp(data: dict, background: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    _ensure_schema(db)
    channel = data.get("channel"); contact = (data.get("value") or "").strip()
    if not contact:
        return {"ok": False, "error": "no contact"}
    _limit(request, "otp_ip", 8, 600)                       # 8 / 10 min per IP
    _limit(request, "otp_to", 5, 3600, key=contact)         # 5 / hour per phone/email (anti-bombing)
    # forex captcha gates the first contact (phone)
    if channel == "phone":
        import forex_captcha
        if not forex_captcha.verify(db, data.get("captcha_id"), data.get("captcha_answer")):
            return {"ok": False, "error": "Captcha incorrect — please try again"}
    import email_send, sms_send
    live = (channel == "email" and email_send.configured()) or (channel == "phone" and sms_send.configured())
    code = f"{random.randint(0, 999999):06d}" if live else "0000"   # real 6-digit when a provider is live
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    db.execute(text("UPDATE otp_codes SET verified=TRUE WHERE contact=:c AND channel=:ch AND verified=FALSE"),
               {"c": contact, "ch": channel})  # invalidate older unused codes
    db.execute(text("INSERT INTO otp_codes (contact, channel, code, expires_at) VALUES (:c,:ch,:code,:e)"),
               {"c": contact, "ch": channel, "code": code, "e": exp})
    db.commit()
    if live:
        # Deliver in the BACKGROUND so the button returns immediately (SMTP/SMS can take seconds).
        # The code is already persisted above, so /verify-otp works the moment the email/SMS lands.
        background.add_task(_deliver_otp, channel, contact, code)
        return {"ok": True}
    # dev mode (no provider configured yet) — fixed 0000, surfaced for testing
    print(f"[OTP/{channel}] {contact} -> {code}", flush=True)
    return {"ok": True, "dev_code": code}


@router.post("/verify-otp")
def verify_otp(data: dict, request: Request, db: Session = Depends(get_db)):
    channel = data.get("channel"); contact = (data.get("value") or "").strip()
    code = (data.get("code") or "").strip()
    _limit(request, "otp_verify", 12, 600, key=contact)     # 12 / 10 min per contact (anti brute-force)
    # 0000 bypass ONLY while no real provider is wired for this channel (dev). Once SMS/SMTP is
    # configured, a real code is required.
    import email_send, sms_send
    dev_mode = not ((channel == "email" and email_send.configured()) or (channel == "phone" and sms_send.configured()))
    if dev_mode and code in ("0000", "000000"):
        db.execute(text("UPDATE otp_codes SET verified=TRUE WHERE contact=:c AND channel=:ch AND verified=FALSE"),
                   {"c": contact, "ch": channel})
        db.commit()
        return {"ok": True}
    row = db.execute(text("""
        SELECT id, code, expires_at FROM otp_codes
        WHERE contact=:c AND channel=:ch AND verified=FALSE ORDER BY id DESC LIMIT 1
    """), {"c": contact, "ch": channel}).fetchone()
    if not row:
        return {"ok": False, "error": "no code, request a new one"}
    rid, real, exp = row
    if exp and datetime.datetime.utcnow() > exp:
        return {"ok": False, "error": "code expired"}
    db.execute(text("UPDATE otp_codes SET attempts=attempts+1 WHERE id=:i"), {"i": rid})
    if code != real:
        db.commit()
        return {"ok": False, "error": "incorrect code"}
    db.execute(text("UPDATE otp_codes SET verified=TRUE WHERE id=:i"), {"i": rid})
    db.commit()
    return {"ok": True}


# ── step 5: submit registration -> create a LEAD + registration record ──
@router.post("/submit")
def submit(data: dict, request: Request, db: Session = Depends(get_db)):
    _ensure_schema(db)
    fn = (data.get("first_name") or "").strip()
    ln = (data.get("last_name") or "").strip()
    full = (fn + " " + ln).strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    _limit(request, "submit_ip", 6, 3600)                          # 6 / hour per IP
    if phone:
        _limit(request, "submit_to", 3, 86400, key=phone)          # 3 / day per phone (anti mass-signup)
    pw = data.get("password") or ""
    from auth import get_password_hash
    pwh = get_password_hash(pw) if pw else None
    rid = db.execute(text("""
        INSERT INTO registrations (first_name,last_name,country,state,city,phone,email,
            platform,account_type,leverage,islamic,questionnaire,status,password_hash,address,nationality,date_of_birth)
        VALUES (:fn,:ln,:co,:st,:ci,:ph,:em,:pl,:at,:lv,:is,:q,'pending_kyc',:pwh,:addr,:nat,:dob) RETURNING id
    """), {"fn": fn, "ln": ln, "co": data.get("country"), "st": (data.get("state") or "").strip() or None,
           "ci": data.get("city"),
           "ph": phone, "em": email, "pl": data.get("platform", "MT5"),
           "at": data.get("account_type", "Standard"), "lv": data.get("leverage", "1:500"),
           "is": bool(data.get("islamic")), "q": json.dumps(data.get("questionnaire") or {}),
           "pwh": pwh, "addr": (data.get("address") or "").strip(),
           "nat": (data.get("nationality") or "").strip(),
           "dob": (data.get("date_of_birth") or "").strip() or None}).scalar()
    # derive the marketing SOURCE from the UTM/gclid the landing page passed through (Google
    # Search ads land on the site with ?utm_source=google&gclid=...; Meta with fbclid). This is
    # how a search-engine campaign's signups get attributed — there are no Google "lead forms".
    _us = (data.get("utm_source") or "").strip().lower()
    _gclid = (data.get("gclid") or "").strip()
    _fbclid = (data.get("fbclid") or "").strip()
    # substring match — real utm_source tags look like 'IQ-Google-LandingPage', 'fb_iq_campaign', etc.
    if _gclid or "google" in _us or "adwords" in _us:
        src = "google"
    elif "instagram" in _us or _us == "ig":
        src = "instagram"
    elif _fbclid or "facebook" in _us or _us in ("fb", "meta"):
        src = "facebook"
    elif _us:
        src = _us
    else:
        src = "registration"
    _camp = (data.get("utm_campaign") or "").strip() or "Website Register"
    lead_id = db.execute(text("""
        INSERT INTO leads (full_name, phone, email, country, city, source, campaign_name, status,
            phone_verified, email_verified, kyc_status, utm_source, utm_medium, utm_campaign, gclid, created_at)
        VALUES (:n,:p,:e,:co,:ci,:src,:camp,'new',TRUE,TRUE,'pending',:us,:um,:uc,:gclid,NOW()) RETURNING id
    """), {"n": full, "p": phone, "e": email, "co": data.get("country"), "ci": data.get("city"),
           "src": src, "camp": _camp, "us": _us or None, "um": (data.get("utm_medium") or "").strip() or None,
           "uc": (data.get("utm_campaign") or "").strip() or None, "gclid": _gclid or None}).scalar()
    db.execute(text("UPDATE registrations SET lead_id=:l WHERE id=:r"), {"l": lead_id, "r": rid})
    client_token = None
    client_login = None
    portal_token = None
    if pwh:
        db.execute(text("""INSERT INTO client_logins (registration_id, lead_id, email, phone, password_hash)
                           VALUES (:r,:l,:e,:p,:h)"""),
                   {"r": rid, "l": lead_id, "e": email, "p": phone, "h": pwh})
        # create a CLIENT row (negative temp login = portal registrant, no MT account yet).
        # The portal authenticates against clients.password_hash by email; its token keys on clients.id.
        client_login = -(1000000 + rid)
        client_pk = db.execute(text("""INSERT INTO clients (login, name, email, phone, country, city, platform,
                               source, password_hash, is_flagged)
                           VALUES (:lg,:nm,:em,:ph,:co,:ci,:pl,:src,:h,FALSE) RETURNING id"""),
                   {"lg": client_login, "nm": full or email, "em": email, "ph": phone,
                    "co": data.get("country"), "ci": data.get("city"),
                    "pl": data.get("platform", "MT5"), "src": src, "h": pwh}).scalar()
        from auth import create_access_token
        client_token = create_access_token({"sub": email or f"client{client_login}",
                                            "role": "client", "user_type": "client", "login": client_login})
        # portal token (the /portal/ app reads this) — log the new client straight into the portal
        try:
            from portal_router import _make_portal_token
            portal_token = _make_portal_token(int(client_pk))
        except Exception:
            portal_token = None
    db.execute(text("UPDATE registrations SET mt_login=:lg WHERE id=:r"), {"lg": client_login, "r": rid})
    db.commit()
    return {"ok": True, "registration_id": rid, "lead_id": lead_id,
            "client_token": client_token, "client_login": client_login, "portal_token": portal_token}


# ── step 6: KYC upload (per document type) ──
@router.post("/kyc-upload")
async def kyc_upload(
    request: Request, registration_id: int = Form(...), doc_type: str = Form(...), side: str = Form(...),
    file: UploadFile = File(...), db: Session = Depends(get_db),
):
    _limit(request, "kyc_ip", 120, 3600)         # 120 uploads / hour per IP
    _ensure_schema(db)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    safe = f"reg{registration_id}_{doc_type}_{side}{ext}"
    path = os.path.join(KYC_DIR, safe)
    with open(path, "wb") as f:
        f.write(await file.read())
    lead_id = db.execute(text("SELECT lead_id FROM registrations WHERE id=:r"), {"r": registration_id}).scalar()
    did = db.execute(text("""
        INSERT INTO reg_kyc_documents (registration_id, lead_id, doc_type, side, file_path, status)
        VALUES (:r,:l,:dt,:s,:p,'uploaded') RETURNING id
    """), {"r": registration_id, "l": lead_id, "dt": doc_type, "s": side, "p": path}).scalar()
    # Reflect "under review" the moment a document is uploaded — even if the client uploads from the
    # phone (QR hand-off) and never taps Submit, the dashboard banner now matches the uploaded docs
    # instead of staying on "upload your documents". (Lazy AI processing runs on next portal load.)
    try:
        lg = db.execute(text("SELECT mt_login FROM registrations WHERE id=:r"), {"r": registration_id}).scalar()
        db.execute(text("UPDATE registrations SET status='under_review' WHERE id=:r AND status='pending_kyc'"),
                   {"r": registration_id})
        if lg is not None:
            db.execute(text("UPDATE clients SET kyc_status='pending_review' WHERE login=:lg AND kyc_status IS DISTINCT FROM 'verified'"),
                       {"lg": lg})
        if lead_id:
            db.execute(text("UPDATE leads SET kyc_status='pending_review' WHERE id=:l AND COALESCE(kyc_status,'') NOT IN ('verified')"),
                       {"l": lead_id})
            # reflect per-document upload on the Leads page KYC column right away
            if side in ("front", "main", "back"):
                db.execute(text("UPDATE leads SET kyc_id_uploaded=TRUE WHERE id=:l"), {"l": lead_id})
            if side.startswith("proof_of_address"):
                db.execute(text("UPDATE leads SET kyc_address_uploaded=TRUE WHERE id=:l"), {"l": lead_id})
    except Exception:
        db.rollback()
    db.commit()
    return {"ok": True, "document_id": did, "stored": safe}


# ── KYC processing: OCR (Claude) + face-match (local) + auto-verify + network cross-check ──
def _process_kyc_bg(registration_id: int):
    db = SessionLocal()
    try:
        kyc_engine.process(db, registration_id)
    except Exception as e:
        print(f"[kyc] process failed for reg {registration_id}: {e}", flush=True)
    finally:
        db.close()


def set_immediate_docs_status(db, registration_id):
    """If the registrant uploaded their ID but is MISSING a required document (a proof of address,
    or the back of a national ID), reflect that in the KPI IMMEDIATELY as 'docs_needed' — so the
    client is asked for the missing document straight away instead of sitting in a generic
    'under review' while the AI reads the ID. The AI engine still runs right after and refines the
    verdict (approves/rejects the ID; keeps docs_needed until the address proof arrives).
    Returns True if it set 'docs_needed' (i.e. the submission is incomplete)."""
    try:
        reg = db.execute(text("SELECT lead_id, mt_login FROM registrations WHERE id=:r"),
                         {"r": registration_id}).fetchone()
        if not reg:
            return False
        rows = db.execute(text("SELECT doc_type, side FROM reg_kyc_documents WHERE registration_id=:r"),
                          {"r": registration_id}).fetchall()
        sides = {x.side for x in rows}
        dtypes = {x.doc_type for x in rows}
        if not any(s in ("front", "main") for s in sides):
            return False   # no ID uploaded yet — nothing to ask for
        need_back = bool({"national_id", "driving_license", "drivers_license"} & dtypes)
        missing = []
        if need_back and "back" not in sides:
            missing.append("the back side of your ID")
        if not any(s.startswith("proof_of_address") for s in sides):
            missing.append("a proof of address (utility bill / bank statement)")
        if not missing:
            return False   # complete submission — run the normal review
        reason = ("Thanks — we've received your ID and our team is reviewing it now. To finish, "
                  "please also upload " + " and ".join(missing) + ".")
        db.execute(text("UPDATE registrations SET verify_reason=:rs WHERE id=:r"),
                   {"rs": reason, "r": registration_id})
        if reg.mt_login is not None:
            db.execute(text("UPDATE clients SET kyc_status='docs_needed' WHERE login=:lg AND kyc_status IS DISTINCT FROM 'verified'"),
                       {"lg": reg.mt_login})
        if reg.lead_id:
            db.execute(text("UPDATE leads SET kyc_status='docs_needed' WHERE id=:l"), {"l": reg.lead_id})
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"[kyc] immediate docs-needed check failed for reg {registration_id}: {e}", flush=True)
        return False


@router.post("/kyc/process/{registration_id}")
def kyc_process(registration_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Called when the registrant has uploaded documents. Immediately marks the client/lead as
    'under review' (so the portal shows the under-review banner the moment they land), then runs
    the KYC pipeline (Claude OCR + face-match + verify) in the background so they aren't blocked."""
    # If the ID is here but a required document (proof of address / ID back) is missing, ask for it
    # in the KPI IMMEDIATELY instead of showing a generic "under review". Otherwise show under-review
    # while the AI checks the full set. Either way the AI engine runs next and finalises the verdict.
    incomplete = set_immediate_docs_status(db, registration_id)
    if not incomplete:
        try:
            reg = db.execute(text("SELECT lead_id, mt_login FROM registrations WHERE id=:r"),
                             {"r": registration_id}).fetchone()
            if reg:
                lead_id, mt_login = reg[0], reg[1]
                db.execute(text("UPDATE registrations SET status='under_review' WHERE id=:r"), {"r": registration_id})
                if lead_id:
                    db.execute(text("UPDATE leads SET kyc_status='review' WHERE id=:l"), {"l": lead_id})
                if mt_login is not None:
                    db.execute(text("UPDATE clients SET kyc_status='pending_review' WHERE login=:lg"), {"lg": mt_login})
                db.commit()
        except Exception as e:
            db.rollback()
            print(f"[kyc] could not mark under_review for reg {registration_id}: {e}", flush=True)
    background.add_task(_process_kyc_bg, registration_id)
    return {"ok": True, "queued": True}


def _kyc_payload(db, registration_id):
    kyc_engine.ensure_kyc_columns(db)
    r = db.execute(text("""
        SELECT id, first_name, last_name, phone, email, country, city, lead_id,
               ocr_fields, face_score, face_verdict, name_match, doc_expired, id_number,
               verify_status, network_json, processed_at, status, mt_login,
               platform, account_type, leverage, islamic
        FROM registrations WHERE id=:r
    """), {"r": registration_id}).fetchone()
    if not r:
        return {"ok": False, "found": False}
    docs = db.execute(text("SELECT doc_type, side, status FROM reg_kyc_documents WHERE registration_id=:r"),
                      {"r": registration_id}).fetchall()
    jl = lambda v: (v if isinstance(v, (dict, list)) or v is None else __import__("json").loads(v))
    return {
        "ok": True, "found": True, "registration_id": r.id, "lead_id": r.lead_id,
        "entered_name": ((r.first_name or "") + " " + (r.last_name or "")).strip(),
        "phone": r.phone, "email": r.email, "country": r.country, "city": r.city,
        "fields": jl(r.ocr_fields), "face_score": r.face_score, "face_verdict": r.face_verdict,
        "name_match": r.name_match, "doc_expired": r.doc_expired, "id_number": r.id_number,
        "verify_status": r.verify_status, "network": jl(r.network_json),
        "processed_at": str(r.processed_at) if r.processed_at else None,
        "reg_status": r.status, "mt_login": r.mt_login,
        "activated": bool(r.mt_login is not None and r.mt_login > 0),
        "account": {"platform": r.platform, "type": r.account_type, "leverage": r.leverage, "islamic": r.islamic},
        "documents": [{"doc_type": d.doc_type, "side": d.side, "status": d.status} for d in docs],
    }


@router.get("/kyc/{registration_id}")
def kyc_result(registration_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return _kyc_payload(db, registration_id)


@router.get("/kyc/by-lead/{lead_id}")
def kyc_by_lead(lead_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    kyc_engine.ensure_kyc_columns(db)
    rid = db.execute(text("SELECT id FROM registrations WHERE lead_id=:l ORDER BY id DESC LIMIT 1"),
                     {"l": lead_id}).scalar()
    if not rid:
        return {"ok": True, "found": False}
    return _kyc_payload(db, rid)


# ── Phase 4: create the REAL MT5 account on verification (deliberate desk action) ──
@router.post("/activate/{registration_id}")
def activate(registration_id: int, data: dict = None, db: Session = Depends(get_db),
             _user=Depends(get_current_user)):
    import mt_provision
    r = db.execute(text("""
        SELECT id, first_name, last_name, email, phone, country, city, platform,
               account_type, leverage, islamic, lead_id, mt_login, verify_status, status
        FROM registrations WHERE id=:r
    """), {"r": registration_id}).fetchone()
    if not r:
        return {"ok": False, "error": "registration not found"}
    if r.status == "account_created" and r.mt_login and r.mt_login > 0:
        return {"ok": False, "error": f"already activated (login {r.mt_login})"}
    if (r.platform or "MT5").upper() != "MT5":
        return {"ok": False, "error": "only MT5 provisioning is wired so far (MT4 next)"}

    group = mt_provision.real_group(r.account_type, r.islamic)
    try:
        lev = int(str(r.leverage or "1:500").split(":")[-1])
    except Exception:
        lev = 500
    res = mt_provision.create_account(group, r.first_name, r.last_name, leverage=lev,
                                      email=r.email, phone=r.phone, country=r.country, city=r.city)
    if not res.get("ok"):
        return {"ok": False, "error": f"account creation failed: {res.get('error')}"}
    real_login = int(res["login"])

    # optional welcome credit
    credit_amt = float((data or {}).get("credit") or 0)
    credit_res = mt_provision.credit_account(real_login, credit_amt, "Welcome credit") if credit_amt > 0 else None

    # remap the portal client (negative temp login -> real MT login) + close the loop
    old_login = r.mt_login
    if old_login is not None:
        db.execute(text("UPDATE clients SET login=:new, group_name=:g WHERE login=:old"),
                   {"new": real_login, "g": group, "old": old_login})
    db.execute(text("UPDATE registrations SET mt_login=:new, status='account_created' WHERE id=:r"),
               {"new": real_login, "r": registration_id})
    if r.lead_id:
        db.execute(text("UPDATE leads SET status='converted', kyc_status='verified' WHERE id=:l"),
                   {"l": r.lead_id})
    db.commit()
    # welcome email with the new MT credentials (sends only once SMTP is configured; logs otherwise)
    emailed = False
    try:
        import email_send
        if r.email:
            body = (
                f"Hello {r.first_name or ''},\n\n"
                f"Your TNFX {r.platform or 'MT5'} trading account is ready.\n\n"
                f"  Login: {real_login}\n"
                f"  Password: {res.get('master')}\n"
                f"  Investor (read-only) password: {res.get('investor')}\n"
                f"  Server: TNFX-Live\n\n"
                + (f"A welcome credit of ${credit_amt:.2f} has been added to your account.\n\n" if credit_amt > 0 else "")
                + "Log in to your client dashboard at https://my1.tnfx.co\n\n"
                "Please keep these credentials safe and change your password after first login.\n\nTNFX"
            )
            emailed = email_send.send(r.email, "Your TNFX trading account is ready", body)
    except Exception:
        pass
    return {"ok": True, "login": real_login, "group": group,
            "master_password": res.get("master"), "investor_password": res.get("investor"),
            "credit": credit_res, "emailed": emailed}
