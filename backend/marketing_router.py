"""
marketing_router.py — Marketing Command Center (READ-ONLY / PREVIEW-ONLY).

Scope right now: it READS the CRM to build smart audiences, shows reachability, proposes
occasions, and DRAFTS message copy with AI. It NEVER sends email/WhatsApp and NEVER spends
ad budget — every outbound action is intentionally disabled until the channels are
credentialed and explicitly turned on (same simulation-first stance as the rest of the app).

Endpoints (prefix /marketing, staff auth):
  GET  /marketing/overview           reachability + funnel KPIs
  GET  /marketing/segments           smart audiences with live counts + reach
  GET  /marketing/segments/{key}/sample   sample recipients (masked) for preview
  GET  /marketing/occasions          curated calendar of campaign moments (region-aware)
  POST /marketing/draft              AI-draft message copy for a segment+occasion (no send)
  GET/POST/DELETE /marketing/campaigns   saved DRAFT campaigns (status stays 'draft')
  GET  /marketing/channels           connection status of each channel (local config only)
"""
import os
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/marketing", tags=["marketing"])


# go-live hardening: campaign create/delete + drafts are for marketing/management.
def _require_marketing(current_user):
    if (getattr(current_user, "role", "") or "").lower() not in (
            "super_admin", "admin", "director", "marketing"):
        from fastapi import HTTPException as _H
        raise _H(status_code=403, detail="Marketing/management only")

# Deposit truth lives in `transactions` (clients.last_deposit_at/total_deposits are unpopulated).
# tx_date is varchar 'YYYY-MM-DD HH:MM:SS' -> safe-cast to a date for recency math.
HAS_DEP = "EXISTS (SELECT 1 FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit')"
# most-recent deposit date for the client's login (NULL if never / unparseable)
LAST_DEP = ("(SELECT MAX(CASE WHEN t.tx_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' "
            "THEN substring(t.tx_date,1,10)::date END) "
            "FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit')")

# ─────────────────── SMART AUDIENCE REGISTRY ───────────────────
# Each segment: a base audience (leads | clients | ibs), a WHERE clause, the recommended
# channel, and WHY it matters. Counts + reachability are computed live.
SEGMENTS = [
    # ── LEADS (prospects) ──
    {"key": "leads_all", "audience": "leads", "label": "All leads", "channel": "both",
     "where": "TRUE", "desc": "Every lead captured (Meta forms + registrations)."},
    {"key": "leads_new", "audience": "leads", "label": "New / uncontacted leads", "channel": "both",
     "where": "(status ILIKE 'new' OR COALESCE(call_attempts,0)=0)",
     "desc": "Fresh leads not yet worked — strike while intent is hot."},
    {"key": "leads_unmatched", "audience": "leads", "label": "Pure prospects (not yet clients)", "channel": "both",
     "where": "matched_login IS NULL",
     "desc": "Never opened an account — top-of-funnel nurture to register."},
    {"key": "leads_no_deposit_registered", "audience": "leads", "label": "Registered, no deposit", "channel": "both",
     "where": "match_badge='registered_no_deposit'",
     "desc": "Opened an account but never funded — the #1 conversion target."},
    {"key": "leads_recapture", "audience": "leads", "label": "Recapture (re-engaged leads)", "channel": "both",
     "where": "match_badge='recapture'",
     "desc": "Old leads that resurfaced — warm, worth a personal nudge."},
    {"key": "leads_verified", "audience": "leads", "label": "Verified leads", "channel": "both",
     "where": "(COALESCE(is_verified,false) OR COALESCE(phone_verified,false) OR COALESCE(email_verified,false))",
     "desc": "Contact verified — highest deliverability, prioritise these."},
    {"key": "leads_facebook", "audience": "leads", "label": "Facebook leads", "channel": "both",
     "where": "source='facebook'", "desc": "Came from Facebook lead forms."},
    {"key": "leads_instagram", "audience": "leads", "label": "Instagram leads", "channel": "both",
     "where": "source='instagram'", "desc": "Came from Instagram lead forms."},

    # ── CLIENTS (account holders) ──
    {"key": "clients_all", "audience": "clients", "label": "All clients", "channel": "both",
     "where": "TRUE", "desc": "Everyone with a trading account."},
    {"key": "clients_never_deposited", "audience": "clients", "label": "Never deposited", "channel": "both",
     "where": f"NOT {HAS_DEP}",
     "desc": "Registered accounts with zero deposits — convert with a first-deposit offer."},
    {"key": "clients_depositors", "audience": "clients", "label": "Depositors", "channel": "both",
     "where": HAS_DEP, "desc": "Clients who have funded at least once."},
    {"key": "clients_lapsed_90", "audience": "clients", "label": "Lapsed depositors (90d+)", "channel": "both",
     "where": f"{LAST_DEP} < (CURRENT_DATE - 90)",
     "desc": "Funded before but quiet 90+ days — reactivation campaign."},
    {"key": "clients_lapsed_180", "audience": "clients", "label": "Dormant depositors (180d+)", "channel": "both",
     "where": f"{LAST_DEP} < (CURRENT_DATE - 180)",
     "desc": "Long-inactive depositors — win-back with a strong incentive."},
    {"key": "clients_funded_idle", "audience": "clients", "label": "Funded but idle (no deposit 90d+)", "channel": "both",
     "where": f"COALESCE(c.balance,0) > 0 AND ({LAST_DEP} IS NULL OR {LAST_DEP} < (CURRENT_DATE - 90))",
     "desc": "Money sitting idle — nudge to trade/top-up before they withdraw."},
    {"key": "clients_active_balance", "audience": "clients", "label": "Funded accounts (balance > 0)", "channel": "both",
     "where": "COALESCE(c.balance,0) > 0", "desc": "Currently funded — upsell / loyalty."},
    {"key": "clients_vip", "audience": "clients", "label": "VIP (balance ≥ $5k)", "channel": "both",
     "where": "COALESCE(c.balance,0) >= 5000", "desc": "High-value clients — white-glove retention."},
    {"key": "clients_kyc_pending", "audience": "clients", "label": "KYC not complete", "channel": "both",
     "where": "COALESCE(c.kyc_status,'') <> 'verified'",
     "desc": "Remind them to finish verification to unlock withdrawals."},

    # ── PARTNERS ──
    {"key": "ibs_all", "audience": "ibs", "label": "IB partners", "channel": "both",
     "where": "TRUE", "desc": "Introducing brokers — partner updates & incentives."},
]

SEG_BY_KEY = {s["key"]: s for s in SEGMENTS}


def _base(audience):
    if audience == "leads":
        return "leads", "leads", "email", "phone"
    if audience == "clients":
        return "clients c", "c", "c.email", "c.phone"
    if audience == "ibs":
        return "ibs", "ibs", "email", "phone"
    raise ValueError(audience)


def _counts(db, seg):
    if seg["audience"] == "clients":
        # person-level (see _segments_compute): clients rows are ACCOUNTS, not people
        wj = (seg["where"].replace(HAS_DEP, "has_dep").replace(LAST_DEP, "last_dep")
                          .replace("COALESCE(c.balance,0)", "COALESCE(balance,0)")
                          .replace("COALESCE(c.kyc_status,'') <> 'verified'", "NOT kyc_ok"))
        r = db.execute(text(f"""
            WITH dep AS (
                SELECT login, MAX(CASE WHEN tx_date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                                       THEN substring(tx_date,1,10)::date END) AS last_dep
                FROM transactions WHERE tx_type='deposit' GROUP BY login
            ),
            p AS (
                SELECT c.customer_no, BOOL_OR(d.login IS NOT NULL) AS has_dep, MAX(d.last_dep) AS last_dep,
                       SUM(COALESCE(c.balance,0)) AS balance,
                       BOOL_OR(COALESCE(c.kyc_status,'')='verified') AS kyc_ok,
                       MAX(lower(NULLIF(c.email,''))) AS email,
                       MAX(NULLIF(regexp_replace(c.phone,'[^0-9]','','g'),'')) AS phone
                FROM clients c LEFT JOIN dep d ON d.login = c.login
                GROUP BY c.customer_no
            )
            SELECT COUNT(*), COUNT(DISTINCT email) FILTER (WHERE email IS NOT NULL),
                   COUNT(DISTINCT phone) FILTER (WHERE phone IS NOT NULL)
            FROM p WHERE {wj}
        """)).fetchone()
        return {"total": int(r[0] or 0), "reach_email": int(r[1] or 0), "reach_whatsapp": int(r[2] or 0)}
    frm, _alias, em, ph = _base(seg["audience"])
    sql = f"""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {em} IS NOT NULL AND {em} <> '') AS with_email,
               COUNT(*) FILTER (WHERE {ph} IS NOT NULL AND {ph} <> '') AS with_phone
        FROM {frm}
        WHERE {seg['where']}
    """
    r = db.execute(text(sql)).fetchone()
    return {"total": int(r[0] or 0), "reach_email": int(r[1] or 0), "reach_whatsapp": int(r[2] or 0)}


# ─────────────────── OCCASIONS (curated, region-aware) ───────────────────
# Approximate 2026 dates for the MENA/forex audience. Static reference data the desk can act on.
OCCASIONS = [
    {"id": "ramadan", "name": "Ramadan", "when": "2026-02-18", "type": "holiday",
     "audience": "clients_all", "channel": "both",
     "angle": "Ramadan greetings + special deposit bonus; lighter trading-hours reminder."},
    {"id": "eid_fitr", "name": "Eid al-Fitr", "when": "2026-03-20", "type": "holiday",
     "audience": "clients_all", "channel": "both",
     "angle": "Eid Mubarak gift — bonus credit or fee-free withdrawals for the week."},
    {"id": "eid_adha", "name": "Eid al-Adha", "when": "2026-05-27", "type": "holiday",
     "audience": "clients_all", "channel": "both", "angle": "Eid greetings + loyalty reward."},
    {"id": "new_year", "name": "New Year", "when": "2026-01-01", "type": "holiday",
     "audience": "leads_all", "channel": "both", "angle": "‘New year, new account’ first-deposit offer."},
    {"id": "first_deposit", "name": "First-deposit offer", "when": "evergreen", "type": "offer",
     "audience": "clients_never_deposited", "channel": "both",
     "angle": "Match-bonus on first deposit to convert registered-no-deposit accounts."},
    {"id": "reactivation", "name": "Win-back offer", "when": "evergreen", "type": "offer",
     "audience": "clients_lapsed_90", "channel": "both",
     "angle": "‘We miss you’ — reload bonus + a market update to re-engage lapsed depositors."},
    {"id": "kyc_reminder", "name": "Complete your KYC", "when": "evergreen", "type": "lifecycle",
     "audience": "clients_kyc_pending", "channel": "both",
     "angle": "Finish verification to enable withdrawals — short, helpful, with a direct link."},
    {"id": "no_deposit_nudge", "name": "Fund & start trading", "when": "evergreen", "type": "lifecycle",
     "audience": "leads_no_deposit_registered", "channel": "both",
     "angle": "Remove friction: how to deposit in 2 minutes + a small starter incentive."},
    {"id": "nfp", "name": "Non-Farm Payrolls (NFP)", "when": "first Friday monthly", "type": "market",
     "audience": "clients_active_balance", "channel": "both",
     "angle": "Trade-the-news: volatility alert + key levels on gold/USD pairs."},
    {"id": "weekly_outlook", "name": "Weekly market outlook", "when": "every Sunday", "type": "content",
     "audience": "clients_active_balance", "channel": "email",
     "angle": "Value content (not salesy) to keep the brand top-of-mind and accounts active."},
]


# ─────────────────── caching (these endpoints run heavy deposit-subquery counts; they don't
# need to be real-time). TTL cache + single-flight lock so concurrent page loads don't stack
# dozens of slow COUNT(*) queries and saturate the DB. ──────────────────────────────────────
import time as _time
import threading as _threading
_CACHE = {}
_CACHE_LOCK = _threading.Lock()
_CACHE_TTL = 600  # 10 min — segment counts change slowly


def _cached(key, compute):
    now = _time.time()
    e = _CACHE.get(key)
    if e and now - e[0] < _CACHE_TTL:
        return e[1]
    with _CACHE_LOCK:                       # single-flight: only ONE recompute at a time
        e = _CACHE.get(key)
        if e and now - e[0] < _CACHE_TTL:   # someone else just computed it while we waited
            return e[1]
        val = compute()
        _CACHE[key] = (_time.time(), val)
        return val


# ─────────────────── ENDPOINTS ───────────────────
@router.get("/overview")
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _cached("overview", lambda: _overview_compute(db))


def _overview_compute(db):
    def scalar(q):
        return int(db.execute(text(q)).scalar() or 0)
    leads_total = scalar("SELECT COUNT(*) FROM leads")
    leads_email = scalar("SELECT COUNT(*) FROM leads WHERE email IS NOT NULL AND email<>''")
    leads_phone = scalar("SELECT COUNT(*) FROM leads WHERE phone IS NOT NULL AND phone<>''")
    # PERSON-level (clients has one row per ACCOUNT incl. archived; a person = customer_no).
    # One pass: persons, distinct emails/phones, depositor persons, lapsed persons.
    drow = db.execute(text("""
        WITH dep AS (
            SELECT login, MAX(CASE WHEN tx_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                                   THEN substring(tx_date,1,10)::date END) AS last_dep
            FROM transactions WHERE tx_type='deposit' GROUP BY login
        ),
        p AS (
            SELECT c.customer_no, BOOL_OR(d.login IS NOT NULL) AS has_dep, MAX(d.last_dep) AS last_dep,
                   MAX(lower(NULLIF(c.email,''))) AS email,
                   MAX(NULLIF(regexp_replace(c.phone,'[^0-9]','','g'),'')) AS phone
            FROM clients c LEFT JOIN dep d ON d.login = c.login
            GROUP BY c.customer_no
        )
        SELECT COUNT(*), COUNT(DISTINCT email), COUNT(DISTINCT phone),
               COUNT(*) FILTER (WHERE has_dep),
               COUNT(*) FILTER (WHERE last_dep < (CURRENT_DATE-90))
        FROM p
    """)).fetchone()
    cl_total, cl_email, cl_phone = int(drow[0] or 0), int(drow[1] or 0), int(drow[2] or 0)
    depositors = int(drow[3] or 0)
    never_dep = cl_total - depositors
    lapsed90 = int(drow[4] or 0)
    return {
        "reach": {
            "leads": leads_total, "leads_email": leads_email, "leads_whatsapp": leads_phone,
            "clients": cl_total, "clients_email": cl_email, "clients_whatsapp": cl_phone,
            "total_email": leads_email + cl_email, "total_whatsapp": leads_phone + cl_phone,
        },
        "funnel": {
            "leads": leads_total, "clients": cl_total,
            "depositors": depositors, "never_deposited": never_dep, "lapsed_90": lapsed90,
        },
    }


@router.get("/segments")
def segments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _cached("segments", lambda: _segments_compute(db))


def _segments_compute(db):
    counts = {}
    # CLIENT segments — compute ALL of them in ONE pass with a single deposit CTE (instead of a
    # slow correlated deposit subquery per segment). HAS_DEP/LAST_DEP get rewritten to reference
    # the joined CTE so each segment's WHERE is a cheap expression over clients ⋈ dep.
    client_segs = [s for s in SEGMENTS if s["audience"] == "clients"]
    try:
        # PERSON-level, not account-level: the clients table has one row per ACCOUNT/login
        # (~179k rows incl. ~159k archived TradeSoft historicals) but only ~65k unique PERSONS
        # (customer_no). Marketing counts must be people/inboxes, or "All clients" shows 174k
        # while the desk knows there are ~26k real (funded) clients. Aggregate to one row per
        # customer_no first (deposit truth = ANY of the person's logins), then count persons
        # and DISTINCT emails/phones.
        sel = []
        for i, s in enumerate(client_segs):
            wj = (s["where"].replace(HAS_DEP, "has_dep").replace(LAST_DEP, "last_dep")
                            .replace("COALESCE(c.balance,0)", "COALESCE(balance,0)")
                            .replace("COALESCE(c.kyc_status,'') <> 'verified'", "NOT kyc_ok"))
            sel.append(f"COUNT(*) FILTER (WHERE {wj}) AS t{i}")
            sel.append(f"COUNT(DISTINCT email) FILTER (WHERE ({wj}) AND email IS NOT NULL) AS e{i}")
            sel.append(f"COUNT(DISTINCT phone) FILTER (WHERE ({wj}) AND phone IS NOT NULL) AS p{i}")
        q = f"""
            WITH dep AS (
                SELECT login, MAX(CASE WHEN tx_date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                                       THEN substring(tx_date,1,10)::date END) AS last_dep
                FROM transactions WHERE tx_type='deposit' GROUP BY login
            ),
            p AS (
                SELECT c.customer_no,
                       BOOL_OR(d.login IS NOT NULL)                          AS has_dep,
                       MAX(d.last_dep)                                       AS last_dep,
                       SUM(COALESCE(c.balance,0))                            AS balance,
                       BOOL_OR(COALESCE(c.kyc_status,'')='verified')         AS kyc_ok,
                       MAX(lower(NULLIF(c.email,'')))                        AS email,
                       MAX(NULLIF(regexp_replace(c.phone,'[^0-9]','','g'),'')) AS phone
                FROM clients c LEFT JOIN dep d ON d.login = c.login
                GROUP BY c.customer_no
            )
            SELECT {', '.join(sel)} FROM p
        """
        row = db.execute(text(q)).fetchone()
        for i, s in enumerate(client_segs):
            counts[s["key"]] = {"total": int(row[i*3] or 0), "reach_email": int(row[i*3+1] or 0),
                                "reach_whatsapp": int(row[i*3+2] or 0)}
    except Exception:
        db.rollback()
    # LEADS + IB segments — cheap individual counts (no deposit subquery)
    for s in SEGMENTS:
        if s["key"] in counts:
            continue
        try:
            counts[s["key"]] = _counts(db, s)
        except Exception:
            db.rollback(); counts[s["key"]] = {"total": 0, "reach_email": 0, "reach_whatsapp": 0}
    out = [{"key": s["key"], "label": s["label"], "audience": s["audience"],
            "channel": s["channel"], "desc": s["desc"], **counts[s["key"]]} for s in SEGMENTS]
    countries = []
    try:
        rows = db.execute(text("""
            SELECT country, COUNT(*) FROM leads
            WHERE country IS NOT NULL AND country<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 12
        """)).fetchall()
        countries = [{"country": r[0], "leads": int(r[1])} for r in rows]
    except Exception:
        db.rollback()
    return {"segments": out, "countries": countries}


def _mask(s, kind):
    s = s or ""
    if kind == "email" and "@" in s:
        u, d = s.split("@", 1)
        return (u[:2] + "***@" + d) if len(u) > 2 else ("***@" + d)
    if kind == "phone" and len(s) > 4:
        return s[:4] + "****" + s[-2:]
    return s


@router.get("/segments/{key}/sample")
def segment_sample(key: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    seg = SEG_BY_KEY.get(key)
    if not seg:
        raise HTTPException(status_code=404, detail="Unknown segment")
    frm, alias, em, ph = _base(seg["audience"])
    name_col = "name" if seg["audience"] != "leads" else "full_name"
    country_col = f"{alias}.country" if seg["audience"] == "clients" else "country"
    rows = db.execute(text(f"""
        SELECT {name_col} AS nm, {em} AS em, {ph} AS ph, {country_col} AS country
        FROM {frm} WHERE {seg['where']} LIMIT 20
    """)).fetchall()
    return {"key": key, "label": seg["label"], "sample": [
        {"name": r[0] or "—", "email": _mask(r[1], "email"), "phone": _mask(r[2], "phone"),
         "country": r[3] or "—"} for r in rows]}


@router.get("/occasions")
def occasions(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _cached("occasions", lambda: _occasions_compute(db))


def _occasions_compute(db):
    # attach the live audience size to each occasion's suggested segment (reuse cached segment
    # totals so we don't re-run the heavy counts)
    seg_totals = {s["key"]: s["total"] for s in _cached("segments", lambda: _segments_compute(db))["segments"]}
    out = []
    for o in OCCASIONS:
        oo = dict(o)
        oo["_size"] = seg_totals.get(o["audience"])
        out.append(oo)
    return {"occasions": out}


@router.post("/draft")
def draft(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_marketing(user)
    """AI-draft message copy. Generates text only — does NOT send anything."""
    seg = SEG_BY_KEY.get(payload.get("segment", ""))
    channel = (payload.get("channel") or "email").lower()
    occasion = (payload.get("occasion") or "").strip()
    offer = (payload.get("offer") or "").strip()
    language = (payload.get("language") or "English")
    tone = (payload.get("tone") or "friendly, professional")
    audience_label = seg["label"] if seg else (payload.get("segment") or "our audience")

    try:
        import kyc_ai  # reuses the shared ai_key.txt loader + anthropic client pattern
        key = kyc_ai._api_key()
    except Exception:
        key = None
    if not key:
        return {"ok": False, "reason": "no_ai_key",
                "message": "AI key not configured (backend/ai_key.txt). Add it to enable AI drafting."}

    brand = "TNFX (forex broker)"
    want = ("a punchy WhatsApp message (max ~60 words, 1-2 emojis, a clear single call to action, "
            "no subject line)") if channel == "whatsapp" else \
           ("a marketing email with a SUBJECT line and a short body (~120 words), a clear call to action")
    prompt = (
        f"You are the marketing copywriter for {brand}. Write {want}.\n"
        f"Audience: {audience_label}. {seg['desc'] if seg else ''}\n"
        f"Occasion/theme: {occasion or 'general engagement'}.\n"
        f"Offer to feature: {offer or '(no specific offer — focus on value/engagement)'}.\n"
        f"Language: {language}. Tone: {tone}.\n"
        "Rules: compliant for a financial brand (no guaranteed-profit claims, include that trading "
        "involves risk if making a financial promise), concise, mobile-first, personal.\n"
        'Return ONLY JSON: {"subject": "...", "body": "..."} (subject empty for WhatsApp).'
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=getattr(kyc_ai, "KYC_MODEL", "claude-opus-4-8"),
                                      max_tokens=700,
                                      messages=[{"role": "user", "content": prompt}])
        raw = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "{}").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(raw)
    except Exception as e:
        return {"ok": False, "reason": "ai_error", "message": str(e)[:200]}
    return {"ok": True, "channel": channel, "subject": data.get("subject", ""),
            "body": data.get("body", ""), "audience": audience_label,
            "recipients": (_counts(db, seg)["reach_email" if channel == "email" else "reach_whatsapp"] if seg else 0)}


def _ensure_campaigns(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketing_campaigns (
            id SERIAL PRIMARY KEY,
            name TEXT, channel TEXT, segment_key TEXT, occasion TEXT,
            subject TEXT, body TEXT, language TEXT,
            recipient_count INT DEFAULT 0,
            status TEXT DEFAULT 'draft',          -- DRAFT only; sending not enabled
            created_by INT, created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.commit()


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ensure_campaigns(db)
    rows = db.execute(text("""
        SELECT id, name, channel, segment_key, occasion, subject, language, recipient_count, status, created_at
        FROM marketing_campaigns ORDER BY id DESC LIMIT 200
    """)).fetchall()
    return {"campaigns": [{
        "id": r[0], "name": r[1], "channel": r[2], "segment_key": r[3], "occasion": r[4],
        "subject": r[5], "language": r[6], "recipient_count": r[7], "status": r[8],
        "created_at": str(r[9])[:16] if r[9] else None} for r in rows]}


@router.post("/campaigns")
def save_campaign(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_marketing(user)
    _ensure_campaigns(db)
    seg = SEG_BY_KEY.get(payload.get("segment_key", ""))
    channel = (payload.get("channel") or "email").lower()
    recips = 0
    if seg:
        try:
            c = _counts(db, seg); recips = c["reach_email" if channel == "email" else "reach_whatsapp"]
        except Exception:
            db.rollback()
    rid = db.execute(text("""
        INSERT INTO marketing_campaigns (name, channel, segment_key, occasion, subject, body, language,
                                         recipient_count, status, created_by)
        VALUES (:n,:ch,:sk,:oc,:su,:bo,:la,:rc,'draft',:cb) RETURNING id
    """), {"n": (payload.get("name") or "Untitled campaign").strip(), "ch": channel,
           "sk": payload.get("segment_key"), "oc": payload.get("occasion"),
           "su": payload.get("subject"), "bo": payload.get("body"),
           "la": payload.get("language"), "rc": recips, "cb": user.id}).scalar()
    db.commit()
    return {"ok": True, "id": rid, "status": "draft",
            "note": "Saved as DRAFT. Sending is disabled until the channel is connected & enabled."}


@router.delete("/campaigns/{cid}")
def delete_campaign(cid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_marketing(user)
    db.execute(text("DELETE FROM marketing_campaigns WHERE id=:i"), {"i": cid})
    db.commit()
    return {"ok": True}


@router.get("/performance")
def performance(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Closed-loop campaign ROI: leads -> registered -> depositors -> revenue, by
    campaign / channel / country. Deposit revenue is attributed through the matched client."""
    # per-lead deposit rollup only for matched leads (cheap: ~hundreds matched)
    base = """
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS deps, COALESCE(SUM(t.amount),0) AS amt
            FROM transactions t WHERE t.login = l.matched_login AND t.tx_type='deposit'
        ) d ON l.matched_login IS NOT NULL
    """
    def rollup(dim_sql, label_expr):
        rows = db.execute(text(f"""
            SELECT {label_expr} AS dim,
                   COUNT(*) AS leads,
                   COUNT(*) FILTER (WHERE l.matched_login IS NOT NULL) AS registered,
                   COUNT(*) FILTER (WHERE COALESCE(d.deps,0) > 0) AS depositors,
                   COALESCE(SUM(d.amt),0) AS revenue
            {base}
            GROUP BY 1 ORDER BY revenue DESC, leads DESC LIMIT 100
        """)).fetchall()
        out = []
        for r in rows:
            leads, reg, dep, rev = int(r[1]), int(r[2]), int(r[3]), float(r[4] or 0)
            out.append({
                "name": r[0] or "(unknown)", "leads": leads, "registered": reg,
                "depositors": dep, "revenue": round(rev, 2),
                "reg_rate": round(100 * reg / leads, 1) if leads else 0,
                "dep_rate": round(100 * dep / reg, 1) if reg else 0,
                "rev_per_lead": round(rev / leads, 2) if leads else 0,
            })
        return out
    return {
        "by_campaign": rollup("campaign", "COALESCE(NULLIF(l.campaign_name,''),'(unknown)')"),
        "by_channel": rollup("source", "COALESCE(NULLIF(l.source,''),'(unknown)')"),
        "by_country": rollup("country", "COALESCE(NULLIF(l.country,''),'(unknown)')"),
        "note": "Revenue = deposits of the client each lead matched to. Ad spend (for true ROAS) "
                "needs ads_read tokens per platform.",
    }


@router.get("/client-sources")
def client_sources(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Acquisition channels by CLIENT source (now real — backfilled from TradeSoft lead_source:
    google/facebook/instagram/affiliate/direct/…). Shows clients, depositors, revenue per source."""
    return _cached("client_sources", lambda: _client_sources_compute(db))


def _client_sources_compute(db):
    rows = db.execute(text("""
        WITH dep AS (
            SELECT login, COALESCE(SUM(amount),0) AS amt, COUNT(*) AS n
            FROM transactions WHERE tx_type='deposit' GROUP BY login
        )
        SELECT COALESCE(NULLIF(c.source,''), '(unknown)') AS src,
               COUNT(*) AS clients,
               COUNT(*) FILTER (WHERE d.login IS NOT NULL) AS depositors,
               COALESCE(SUM(d.amt),0) AS revenue
        FROM clients c LEFT JOIN dep d ON d.login = c.login
        GROUP BY 1 ORDER BY revenue DESC, clients DESC
    """)).fetchall()
    # Only these are REAL acquisition channels. Everything else (the legacy import marker
    # 'tradesoft', 'none', 'registration', '(unknown)', stray tags) is a customer whose source
    # was never captured → roll them all into one "Unattributed" row so the real channels stand out.
    CHANNELS = {"google", "tiktok", "snapchat", "facebook", "instagram", "affiliate", "direct"}
    out, unattr = [], {"source": "Unattributed", "clients": 0, "depositors": 0, "revenue": 0.0}
    for r in rows:
        s = (r[0] or "").lower()
        rec = {"source": r[0], "clients": int(r[1]), "depositors": int(r[2]), "revenue": round(float(r[3] or 0), 2)}
        if s in CHANNELS:
            out.append(rec)
        else:
            unattr["clients"] += rec["clients"]; unattr["depositors"] += rec["depositors"]; unattr["revenue"] += rec["revenue"]
    out.sort(key=lambda x: (-x["revenue"], -x["clients"]))
    if unattr["clients"]:
        unattr["revenue"] = round(unattr["revenue"], 2); out.append(unattr)  # always last
    return {"sources": out}


@router.get("/channels")
def channels(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Connection status per channel — checks LOCAL config only (no external calls)."""
    def has_attr(mod, fn):
        try:
            m = __import__(mod)
            return bool(getattr(m, fn)())
        except Exception:
            return False
    ai_key = os.path.exists(os.path.join(os.path.dirname(__file__), "ai_key.txt")) and \
        bool(open(os.path.join(os.path.dirname(__file__), "ai_key.txt")).read().strip())
    email_ok = has_attr("email_send", "configured")
    # wati / ad platforms: not yet integrated -> not connected
    return {"channels": [
        {"key": "email", "name": "Email (SMTP)", "connected": email_ok,
         "needs": "Office365 authenticated-SMTP password for noreply@tnfx.co", "can_send": False},
        {"key": "wati", "name": "WhatsApp (Wati)", "connected": False,
         "needs": "Wati API endpoint + access token + approved message templates", "can_send": False},
        {"key": "meta", "name": "Meta Ads (FB/IG)", "connected": False,
         "needs": "Token with ads_management + ads_read and your Ad Account ID", "can_send": False},
        {"key": "google", "name": "Google Ads", "connected": False,
         "needs": "Approved developer token + OAuth client + customer ID", "can_send": False},
        {"key": "tiktok", "name": "TikTok Ads", "connected": False,
         "needs": "Marketing API app + advertiser ID + access token", "can_send": False},
        {"key": "snap", "name": "Snapchat Ads", "connected": False,
         "needs": "Snap Marketing API app + ad account ID + token", "can_send": False},
    ], "ai_drafting": bool(ai_key)}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — Marketing↔Sales analytics (ticket #102). Built ONLY from data we already
# have (Meta leads + auto_match + transactions + dialer). NO external ad-API spend/CPL/
# CPC/CTR/UTM/CAC here — that's Stage 2 (needs ads_read tokens per platform).
#
# Period note: leads.created_at is the IMPORT date (Jun 15-16); the REAL lead-capture
# date is meta_created, so we period-filter leads on meta_created. transactions.tx_date
# is a varchar 'YYYY-MM-DD HH:MM:SS' — compared with STRING ranges (no ::date cast, per
# the CLAUDE.md perf note). Revenue is attributed lead→matched client→deposits.
# ══════════════════════════════════════════════════════════════════════════════
from datetime import datetime, timezone, date as _date, timedelta as _td


def _period_range(period: str, date_from: str = "", date_to: str = ""):
    """(start_date, end_date) ISO strings. Mirrors ib_router.period_dates.
    'today' is IRAQ's today (UTC+3) — see crm_tz."""
    from crm_tz import today_local
    today = today_local()
    p = (period or "all_time").lower()
    if p == "today":            s = e = today
    elif p == "yesterday":      s = e = today - _td(days=1)
    elif p == "last_7_days":    s, e = today - _td(days=6), today
    elif p == "last_30_days":   s, e = today - _td(days=29), today
    elif p == "this_month":     s, e = today.replace(day=1), today
    elif p == "last_month":
        first = today.replace(day=1); e = first - _td(days=1); s = e.replace(day=1)
    elif p == "this_year":      s, e = today.replace(month=1, day=1), today
    elif p == "last_year":
        s = today.replace(year=today.year - 1, month=1, day=1)
        e = today.replace(year=today.year - 1, month=12, day=31)
    elif p == "custom" and date_from and date_to:
        s, e = _date.fromisoformat(date_from), _date.fromisoformat(date_to)
    else:                       s, e = _date(2000, 1, 1), today   # all_time
    return s.isoformat(), e.isoformat()


@router.get("/campaign-performance")
def campaign_performance(period: str = "all_time", date_from: str = "", date_to: str = "",
                         dimension: str = "campaign", sort: str = "leads",
                         db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Per-campaign (or per-source / per-country) funnel built from data we already have:
       leads → matched(registered) → funded(deposited) → deposits/revenue, with conversion
       %s and revenue-per-lead. Period filters leads on meta_created (real capture date)."""
    s_date, e_date = _period_range(period, date_from, date_to)
    e_end = e_date + " 23:59:59"
    dim = (dimension or "campaign").lower()
    label = {
        "campaign": "COALESCE(NULLIF(l.campaign_name,''),'(no campaign)')",
        "source":   "COALESCE(NULLIF(l.source,''),'(no source)')",
        "country":  "COALESCE(NULLIF(l.country,''),'(unknown)')",
    }.get(dim, "COALESCE(NULLIF(l.campaign_name,''),'(no campaign)')")

    # Period filter on the real capture date (meta_created); fall back to created_at if null.
    lead_period = ("(COALESCE(l.meta_created, l.created_at) >= CAST(:s AS date) "
                   "AND COALESCE(l.meta_created, l.created_at) < (CAST(:e AS date) + 1))")
    params = {"s": s_date, "e": e_date}

    sql = f"""
        SELECT {label} AS dim,
               COUNT(*) AS leads,
               COUNT(*) FILTER (WHERE l.matched_login IS NOT NULL) AS matched,
               COUNT(*) FILTER (WHERE COALESCE(d.deps,0) > 0) AS funded,
               COALESCE(SUM(d.amt),0) AS deposits,
               COALESCE(SUM(d.deps),0) AS deposit_count
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS deps, COALESCE(SUM(t.amount),0) AS amt
            FROM transactions t
            WHERE t.login = l.matched_login AND t.tx_type='deposit'
        ) d ON l.matched_login IS NOT NULL
        WHERE {lead_period}
        GROUP BY 1
    """
    try:
        db.execute(text("SET LOCAL idle_in_transaction_session_timeout=0"))
        rows = db.execute(text(sql), params).fetchall()
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"campaign-performance query failed: {str(ex)[:200]}")

    out = []
    for r in rows:
        leads, matched, funded = int(r[1]), int(r[2]), int(r[3])
        deposits, dep_cnt = float(r[4] or 0), int(r[5] or 0)
        out.append({
            "name": r[0] or "(unknown)", "leads": leads, "matched": matched, "funded": funded,
            "deposits": round(deposits, 2), "deposit_count": dep_cnt,
            "match_rate": round(100 * matched / leads, 1) if leads else 0.0,
            "fund_rate": round(100 * funded / leads, 1) if leads else 0.0,        # funded / leads
            "fund_of_matched": round(100 * funded / matched, 1) if matched else 0.0,
            "rev_per_lead": round(deposits / leads, 2) if leads else 0.0,
            "avg_deposit": round(deposits / dep_cnt, 2) if dep_cnt else 0.0,
        })
    keymap = {"leads": "leads", "matched": "matched", "funded": "funded",
              "deposits": "deposits", "conv": "fund_rate", "rev_per_lead": "rev_per_lead",
              "name": "name"}
    sk = keymap.get((sort or "leads").lower(), "leads")
    out.sort(key=lambda x: x[sk], reverse=(sk != "name"))

    totals = {
        "leads": sum(r["leads"] for r in out),
        "matched": sum(r["matched"] for r in out),
        "funded": sum(r["funded"] for r in out),
        "deposits": round(sum(r["deposits"] for r in out), 2),
    }
    totals["fund_rate"] = round(100 * totals["funded"] / totals["leads"], 1) if totals["leads"] else 0.0
    totals["rev_per_lead"] = round(totals["deposits"] / totals["leads"], 2) if totals["leads"] else 0.0
    return {"dimension": dim, "period": period, "from": s_date, "to": e_date,
            "rows": out, "totals": totals,
            "note": "Conversion = lead→matched client→deposit. Revenue = those clients' "
                    "deposits. CPL/CPC/CTR/ROAS need ad-spend (Stage 2)."}


@router.get("/customer-value")
def customer_value(period: str = "all_time", date_from: str = "", date_to: str = "",
                   limit: int = 100,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Customer value / retention per campaign: for clients acquired via a campaign's
       matched lead — funded clients, total deposits (simple CLV = Σ deposits), repeat
       depositors, first/last deposit dates, and avg CLV per funded client."""
    s_date, e_date = _period_range(period, date_from, date_to)
    lead_period = ("(COALESCE(l.meta_created, l.created_at) >= CAST(:s AS date) "
                   "AND COALESCE(l.meta_created, l.created_at) < (CAST(:e AS date) + 1))")
    sql = f"""
        WITH funded_leads AS (
            SELECT l.id AS lead_id,
                   COALESCE(NULLIF(l.campaign_name,''),'(no campaign)') AS campaign,
                   l.matched_login AS login
            FROM leads l
            WHERE l.matched_login IS NOT NULL AND {lead_period}
        ),
        per_client AS (
            SELECT fl.campaign, fl.login,
                   COUNT(*) AS dep_count,
                   COALESCE(SUM(t.amount),0) AS total_dep,
                   MIN(substring(t.tx_date,1,10)) AS first_dep,
                   MAX(substring(t.tx_date,1,10)) AS last_dep
            FROM funded_leads fl
            JOIN transactions t ON t.login = fl.login AND t.tx_type='deposit'
            GROUP BY fl.campaign, fl.login
        )
        SELECT campaign,
               COUNT(*) AS funded_clients,
               SUM(total_dep) AS clv,
               SUM(dep_count) AS deposits,
               COUNT(*) FILTER (WHERE dep_count > 1) AS repeat_depositors,
               MIN(first_dep) AS first_dep,
               MAX(last_dep) AS last_dep
        FROM per_client
        GROUP BY campaign
        ORDER BY clv DESC
        LIMIT :lim
    """
    try:
        db.execute(text("SET LOCAL idle_in_transaction_session_timeout=0"))
        rows = db.execute(text(sql), {"s": s_date, "e": e_date, "lim": max(1, min(limit, 500))}).fetchall()
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"customer-value query failed: {str(ex)[:200]}")
    out = []
    for r in rows:
        funded, clv, deps, repeat = int(r[1]), float(r[2] or 0), int(r[3]), int(r[4])
        out.append({
            "campaign": r[0], "funded_clients": funded, "clv": round(clv, 2),
            "deposits": deps, "repeat_depositors": repeat,
            "repeat_rate": round(100 * repeat / funded, 1) if funded else 0.0,
            "avg_clv": round(clv / funded, 2) if funded else 0.0,
            "deposits_per_client": round(deps / funded, 1) if funded else 0.0,
            "first_deposit": r[5], "last_deposit": r[6],
        })
    return {"period": period, "from": s_date, "to": e_date, "rows": out,
            "note": "CLV = Σ deposits of clients acquired through this campaign's matched "
                    "leads (deposit truth = transactions.deposit). Withdrawals/lifetime "
                    "profit not netted out — simple gross CLV."}


@router.get("/sales-activity")
def sales_activity(period: str = "all_time", date_from: str = "", date_to: str = "",
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Sales-team activity from the Power Dialer: calls / connected calls / outcomes.
       Degrades gracefully to zeros if the dialer tables are empty/missing."""
    s_date, e_date = _period_range(period, date_from, date_to)
    e_end = e_date + " 23:59:59"
    out = {"calls": 0, "connected": 0, "no_answer": 0, "connect_rate": 0.0,
           "by_outcome": [], "by_agent": [], "source": "dialer_call_logs"}
    try:
        rows = db.execute(text("""
            SELECT outcome, COUNT(*) FROM dialer_call_logs
            WHERE called_at >= CAST(:s AS date) AND called_at < (CAST(:e AS date) + 1)
            GROUP BY outcome ORDER BY 2 DESC
        """), {"s": s_date, "e": e_date}).fetchall()
        connected_words = ("connected", "connected_done", "answered", "interested", "callback", "call_later")
        for oc, cnt in rows:
            cnt = int(cnt)
            out["calls"] += cnt
            out["by_outcome"].append({"outcome": oc or "(none)", "count": cnt})
            if (oc or "").lower() in connected_words:
                out["connected"] += cnt
            if (oc or "").lower() in ("no_answer", "noanswer", "off"):
                out["no_answer"] += cnt
        out["connect_rate"] = round(100 * out["connected"] / out["calls"], 1) if out["calls"] else 0.0
    except Exception:
        db.rollback()
    # per-agent (best-effort)
    try:
        arows = db.execute(text("""
            SELECT COALESCE(u.full_name, u.email, 'Agent #'||d.agent_id::text) AS agent,
                   COUNT(*) AS calls
            FROM dialer_call_logs d
            LEFT JOIN users u ON u.id = d.agent_id
            WHERE d.called_at >= CAST(:s AS date) AND d.called_at < (CAST(:e AS date) + 1)
            GROUP BY 1 ORDER BY 2 DESC LIMIT 50
        """), {"s": s_date, "e": e_date}).fetchall()
        out["by_agent"] = [{"agent": a, "calls": int(c)} for a, c in arows]
    except Exception:
        db.rollback()
    out["period"] = period; out["from"] = s_date; out["to"] = e_date
    return out


@router.get("/data-quality")
def data_quality(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Lead data-quality report: duplicate leads (phone/email), invalid phone numbers,
       and leads missing campaign_name / source. Counts + small sample lists."""
    def scalar(q):
        try:
            return int(db.execute(text(q)).scalar() or 0)
        except Exception:
            db.rollback(); return 0

    total = scalar("SELECT COUNT(*) FROM leads")
    dup_phone_groups = scalar("""
        SELECT COUNT(*) FROM (SELECT phone FROM leads
        WHERE phone IS NOT NULL AND phone<>'' GROUP BY phone HAVING COUNT(*)>1) x""")
    dup_phone_leads = scalar("""
        SELECT COALESCE(SUM(n),0) FROM (SELECT COUNT(*) n FROM leads
        WHERE phone IS NOT NULL AND phone<>'' GROUP BY phone HAVING COUNT(*)>1) x""")
    dup_email_groups = scalar("""
        SELECT COUNT(*) FROM (SELECT LOWER(email) e FROM leads
        WHERE email IS NOT NULL AND email<>'' GROUP BY 1 HAVING COUNT(*)>1) x""")
    dup_email_leads = scalar("""
        SELECT COALESCE(SUM(n),0) FROM (SELECT COUNT(*) n FROM leads
        WHERE email IS NOT NULL AND email<>'' GROUP BY LOWER(email) HAVING COUNT(*)>1) x""")
    invalid_phone = scalar("""
        SELECT COUNT(*) FROM leads
        WHERE phone IS NOT NULL AND phone<>''
          AND length(regexp_replace(phone,'[^0-9]','','g')) < 8""")
    missing_campaign = scalar("SELECT COUNT(*) FROM leads WHERE campaign_name IS NULL OR campaign_name=''")
    missing_source = scalar("SELECT COUNT(*) FROM leads WHERE source IS NULL OR source=''")
    no_contact = scalar("""
        SELECT COUNT(*) FROM leads
        WHERE (phone IS NULL OR phone='') AND (email IS NULL OR email='')""")

    def sample(q):
        try:
            return [dict(r._mapping) for r in db.execute(text(q)).fetchall()]
        except Exception:
            db.rollback(); return []

    dup_phone_sample = sample("""
        SELECT phone, COUNT(*) AS n, MIN(full_name) AS example
        FROM leads WHERE phone IS NOT NULL AND phone<>''
        GROUP BY phone HAVING COUNT(*)>1 ORDER BY 2 DESC LIMIT 10""")
    dup_email_sample = sample("""
        SELECT LOWER(email) AS email, COUNT(*) AS n, MIN(full_name) AS example
        FROM leads WHERE email IS NOT NULL AND email<>''
        GROUP BY 1 HAVING COUNT(*)>1 ORDER BY 2 DESC LIMIT 10""")
    invalid_phone_sample = sample("""
        SELECT id, full_name, phone FROM leads
        WHERE phone IS NOT NULL AND phone<>''
          AND length(regexp_replace(phone,'[^0-9]','','g')) < 8
        ORDER BY id DESC LIMIT 10""")

    issues = dup_phone_leads + dup_email_leads + invalid_phone + missing_campaign + missing_source
    return {
        "total_leads": total,
        "metrics": [
            {"key": "dup_phone", "label": "Duplicate phone (leads in dup groups)",
             "groups": dup_phone_groups, "count": dup_phone_leads,
             "pct": round(100 * dup_phone_leads / total, 1) if total else 0.0},
            {"key": "dup_email", "label": "Duplicate email (leads in dup groups)",
             "groups": dup_email_groups, "count": dup_email_leads,
             "pct": round(100 * dup_email_leads / total, 1) if total else 0.0},
            {"key": "invalid_phone", "label": "Invalid phone (<8 digits)",
             "count": invalid_phone, "pct": round(100 * invalid_phone / total, 1) if total else 0.0},
            {"key": "missing_campaign", "label": "Missing campaign name",
             "count": missing_campaign, "pct": round(100 * missing_campaign / total, 1) if total else 0.0},
            {"key": "missing_source", "label": "Missing source/channel",
             "count": missing_source, "pct": round(100 * missing_source / total, 1) if total else 0.0},
            {"key": "no_contact", "label": "No phone AND no email",
             "count": no_contact, "pct": round(100 * no_contact / total, 1) if total else 0.0},
        ],
        "quality_score": round(100 * (1 - issues / total), 1) if total else 100.0,
        "samples": {
            "dup_phone": dup_phone_sample,
            "dup_email": dup_email_sample,
            "invalid_phone": invalid_phone_sample,
        },
    }
