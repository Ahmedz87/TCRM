"""
whatsapp_ai.py — the brain for AI-handled WhatsApp (Wati) conversations.

Flow per inbound message:
  1) normalise the sender's phone -> resolve IDENTITY (existing client / known lead / brand new)
  2) opt-out / sensitive-topic guardrails (escalate to a human instead of auto-replying)
  3) generate a SALES reply with Claude, reusing the existing bot brain (KB, client context,
     operator notes) + a WhatsApp sales playbook + the current offer
  4) AUTO-ACTIONS back into the CRM: phone_verified, source=whatsapp, AI-ownership, capture the
     qualification profile (beginner/advanced, interest, goal), create the lead if brand new

Everything is gated: nothing is SENT to WhatsApp here (wati_service does that, and only when
LIVE is enabled). `dry_run=True` also skips the CRM writes so the Simulator can preview safely.

Reuses chat_router's brain (build_client_context, kb_articles, ai_config) — not a second bot.
"""
import re
import json
from sqlalchemy import text

# The WhatsApp assistant talks to real prospects/clients and must sound genuinely smart + human,
# so it runs on the BEST model (Opus 4.8) — NOT the cheaper Sonnet the portal chat bot defaults to.
WA_MODEL = "claude-opus-4-8"

OPT_OUT = ("stop", "unsubscribe", "الغاء", "إلغاء", "ايقاف", "إيقاف", "لا اريد", "remove me")
# ONLY genuine human-handoff triggers — complaints, fraud/legal, or an EXPLICIT request for a
# person. Normal deposit/withdrawal/account questions are NOT here (the AI answers those itself;
# it can still set escalate=true on its own when a case truly needs a human).
SENSITIVE = ("complaint", "شكوى", "اشتكي", "اشكي", "احتيال", "نصب", "محتال", "نصاب",
             "fraud", "scam", "محامي", "lawyer", "legal action", "قانوني", "اقاضي", "محكمة",
             "police", "شرطة", "talk to a human", "speak to a human", "speak to someone",
             "real person", "human agent", "اكلم موظف", "اتكلم مع موظف", "اتكلم مع شخص",
             "اريد موظف", "ابي موظف", "بدي حدا", "اريد اتكلم مع")


_SCHEMA_DONE = False


def ensure_schema(db):
    # Run the (idempotent) DDL once per process. ALTER TABLE on the big live `leads`/`clients`
    # tables needs a brief exclusive lock; if a background loop holds the table, a plain ALTER
    # would HANG every status/config/webhook call. So: do it once, and fail-fast on lock (the
    # columns already exist after the first run, so a lock-timeout error is harmless).
    global _SCHEMA_DONE
    if _SCHEMA_DONE:
        return
    # 1) ALWAYS create the small wa_* tables first (cheap, uncontended). Do this in its OWN
    #    committed step so a later contended ALTER on leads/clients can never roll it back.
    try:
        _ensure_tables(db)
    except Exception:
        db.rollback()
    # 2) best-effort ALTERs on the big, contended leads/clients tables (fail-fast on lock;
    #    the columns already exist after the first run, so a lock-timeout is harmless).
    try:
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
        _ensure_alters(db)
    except Exception:
        db.rollback()
    _SCHEMA_DONE = True


def _ensure_alters(db):
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_managed BOOLEAN DEFAULT FALSE"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS experience_level TEXT"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS interest TEXT"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS goal TEXT"))
    db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS wa_opt_out BOOLEAN DEFAULT FALSE"))
    db.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_managed BOOLEAN DEFAULT FALSE"))
    db.commit()


def _ensure_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wa_conversations (
            id SERIAL PRIMARY KEY,
            phone TEXT UNIQUE,
            identity_kind TEXT,          -- client | lead | new
            identity_name TEXT,
            client_login BIGINT, lead_id INT,
            status TEXT DEFAULT 'open',  -- open | escalated | opted_out | closed
            ai_owned BOOLEAN DEFAULT TRUE,
            messages_in INT DEFAULT 0, messages_out INT DEFAULT 0,
            last_message_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wa_messages (
            id SERIAL PRIMARY KEY,
            phone TEXT, direction TEXT,  -- in | out
            body TEXT, is_ai BOOLEAN DEFAULT FALSE, escalated BOOLEAN DEFAULT FALSE,
            dry_run BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_wa_msg_phone ON wa_messages(phone, id)"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wati_config (
            id INT PRIMARY KEY DEFAULT 1,
            enabled BOOLEAN DEFAULT FALSE,        -- master LIVE switch (actually send via Wati)
            auto_reply BOOLEAN DEFAULT TRUE,      -- AI replies automatically (vs suggest-only)
            ai_owns_leads BOOLEAN DEFAULT TRUE,   -- WhatsApp leads are AI-owned (no human dials)
            current_offer TEXT DEFAULT '',
            api_endpoint TEXT, api_token TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("INSERT INTO wati_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
    # staff phones allowed to TEACH the bot (via a '#...' message), + the lessons themselves
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wa_staff_phones (
            id SERIAL PRIMARY KEY, phone TEXT, nine TEXT UNIQUE, label TEXT, added_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wa_teachings (
            id SERIAL PRIMARY KEY, note TEXT, author_phone TEXT, active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )"""))
    # phone aliases: a WhatsApp number that should be treated as a DIFFERENT number on file
    # (e.g. a client who messages from a phone that isn't the one registered on their account).
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS wa_phone_aliases (
            id SERIAL PRIMARY KEY, nine TEXT UNIQUE, target_nine TEXT, note TEXT, added_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.commit()


def add_phone_alias(db, wa_phone, account_phone, note=None):
    ensure_schema(db)
    a, b = last9(wa_phone), last9(account_phone)
    if not a or not b:
        return False
    db.execute(text("INSERT INTO wa_phone_aliases (nine, target_nine, note) VALUES (:a,:b,:n) "
                    "ON CONFLICT (nine) DO UPDATE SET target_nine=:b, note=:n"),
               {"a": a, "b": b, "n": note})
    db.commit()
    return True


# ─────────────────── staff teaching ('#...' from a staff phone) ───────────────────
def is_staff_phone(db, phone):
    nine = last9(phone)
    if not nine:
        return False
    return bool(db.execute(text("SELECT 1 FROM wa_staff_phones WHERE nine=:n"), {"n": nine}).fetchone())


def add_staff_phone(db, phone, label=None):
    ensure_schema(db)
    nine = last9(phone)
    if not nine:
        return False
    db.execute(text("INSERT INTO wa_staff_phones (phone, nine, label) VALUES (:p,:n,:l) ON CONFLICT (nine) DO UPDATE SET phone=:p, label=:l"),
               {"p": phone, "n": nine, "l": label})
    db.commit()
    return True


def remove_staff_phone(db, phone):
    db.execute(text("DELETE FROM wa_staff_phones WHERE nine=:n"), {"n": last9(phone)})
    db.commit()


def list_staff_phones(db):
    ensure_schema(db)
    return [{"phone": r[0], "label": r[1]} for r in db.execute(text(
        "SELECT phone, label FROM wa_staff_phones ORDER BY id")).fetchall()]


def add_teaching(db, note, author_phone=None):
    ensure_schema(db)
    note = (note or "").strip()
    if not note:
        return None
    rid = db.execute(text("INSERT INTO wa_teachings (note, author_phone) VALUES (:n,:a) RETURNING id"),
                     {"n": note, "a": author_phone}).scalar()
    db.commit()
    return rid


def list_teachings(db, only_active=False):
    ensure_schema(db)
    w = "WHERE active=TRUE" if only_active else ""
    return [{"id": r[0], "note": r[1], "author_phone": r[2], "active": bool(r[3]),
             "created_at": str(r[4])[:16] if r[4] else None}
            for r in db.execute(text(f"SELECT id, note, author_phone, active, created_at FROM wa_teachings {w} ORDER BY id DESC")).fetchall()]


def set_teaching_active(db, tid, active):
    db.execute(text("UPDATE wa_teachings SET active=:a WHERE id=:i"), {"a": bool(active), "i": tid})
    db.commit()


def delete_teaching(db, tid):
    db.execute(text("DELETE FROM wa_teachings WHERE id=:i"), {"i": tid})
    db.commit()


def teachings_block(db):
    rows = db.execute(text("SELECT note FROM wa_teachings WHERE active=TRUE ORDER BY id DESC LIMIT 30")).fetchall()
    notes = [r[0].strip() for r in rows if r[0] and r[0].strip()]
    if not notes:
        return ""
    body = "\n".join(f"- {n}" for n in notes)
    return ("\n\n=== TEAM TRAINING (instructions from TNFX staff — HIGHEST PRIORITY) ===\n"
            "TNFX staff have taught you these rules. Follow them above your defaults (but never break "
            "the safety/compliance rules):\n" + body)


def get_config(db):
    ensure_schema(db)
    r = db.execute(text("SELECT enabled, auto_reply, ai_owns_leads, current_offer, api_endpoint, api_token FROM wati_config WHERE id=1")).fetchone()
    return {"enabled": bool(r[0]), "auto_reply": bool(r[1]), "ai_owns_leads": bool(r[2]),
            "current_offer": r[3] or "", "api_endpoint": r[4] or "", "api_token_set": bool(r[5])}


def save_config(db, data):
    ensure_schema(db)
    db.execute(text("""
        UPDATE wati_config SET
          enabled=COALESCE(:en,enabled), auto_reply=COALESCE(:ar,auto_reply),
          ai_owns_leads=COALESCE(:ao,ai_owns_leads), current_offer=COALESCE(:co,current_offer),
          api_endpoint=COALESCE(:ep,api_endpoint), api_token=COALESCE(:tk,api_token), updated_at=NOW()
        WHERE id=1
    """), {"en": data.get("enabled"), "ar": data.get("auto_reply"), "ao": data.get("ai_owns_leads"),
           "co": data.get("current_offer"), "ep": data.get("api_endpoint"), "tk": data.get("api_token")})
    db.commit()
    return get_config(db)


# ─────────────────── identity ───────────────────
def last9(p):
    d = re.sub(r"\D", "", p or "")
    return d[-9:] if len(d) >= 9 else d


def resolve_identity(db, phone):
    """Inbound number -> who is this? Returns kind + name + history hints for a personal opener."""
    nine = last9(phone)
    if not nine:
        return {"kind": "new", "name": None, "phone": phone}
    # phone alias: this WhatsApp number may be mapped to a DIFFERENT number on file (a client who
    # messages from a phone that isn't the one registered on their account).
    try:
        a = db.execute(text("SELECT target_nine FROM wa_phone_aliases WHERE nine=:n"), {"n": nine}).fetchone()
        if a and a[0]:
            nine = a[0]
    except Exception:
        pass
    cl = db.execute(text("""
        SELECT login, name, country, kyc_status, COALESCE(phone_verified,false), COALESCE(balance,0),
               (SELECT COUNT(*) FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit') AS deps,
               (SELECT MAX(CASE WHEN t.tx_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN substring(t.tx_date,1,10)::date END)
                  FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit') AS last_dep,
               email, COALESCE(email_verified,false), client_status, COALESCE(is_flagged,false), ib_id
        FROM clients c WHERE RIGHT(regexp_replace(COALESCE(c.phone,''),'\\D','','g'),9)=:n
        ORDER BY deps DESC LIMIT 1
    """), {"n": nine}).fetchone()
    if cl:
        deps = int(cl[6] or 0)
        seg = "new_client"
        if deps == 0:
            seg = "registered_no_deposit"
        elif cl[7] is not None:
            from datetime import date
            try:
                days = (date.today() - cl[7]).days
                seg = "lapsed_depositor" if days > 90 else "active_depositor"
            except Exception:
                seg = "depositor"
        # ALL of this person's accounts (phone+platform siblings) so the bot sees the full picture
        all_logins = [int(r[0]) for r in db.execute(text(
            "SELECT login FROM clients WHERE RIGHT(regexp_replace(COALESCE(phone,''),'\\D','','g'),9)=:n AND login IS NOT NULL"
        ), {"n": nine}).fetchall()]
        return {"kind": "client", "name": cl[1], "login": int(cl[0]), "logins": all_logins or [int(cl[0])],
                "country": cl[2], "kyc": cl[3], "phone_verified": bool(cl[4]), "balance": float(cl[5]),
                "deposits": deps, "segment": seg, "email": cl[8], "email_verified": bool(cl[9]),
                "status": cl[10], "flagged": bool(cl[11]), "is_ib": bool(cl[12]), "phone": phone}
    ld = db.execute(text("""
        SELECT id, full_name, country, source, status, match_badge, experience_level, interest,
               email, COALESCE(phone_verified,false), COALESCE(email_verified,false), kyc_status
        FROM leads WHERE RIGHT(regexp_replace(COALESCE(phone,''),'\\D','','g'),9)=:n ORDER BY id DESC LIMIT 1
    """), {"n": nine}).fetchone()
    if ld:
        return {"kind": "lead", "name": ld[1], "lead_id": int(ld[0]), "country": ld[2],
                "source": ld[3], "status": ld[4], "badge": ld[5],
                "experience_level": ld[6], "interest": ld[7], "email": ld[8],
                "phone_verified": bool(ld[9]), "email_verified": bool(ld[10]), "kyc": ld[11], "phone": phone}
    return {"kind": "new", "name": None, "phone": phone}


def verification_snapshot(ident):
    """An explicit known-contact block so the bot greets them correctly and is aware of their
    status, verification, and any pending matters before it says a word."""
    if ident.get("kind") == "client":
        return (
            "\n\n=== KNOWN CONTACT — THIS WHATSAPP NUMBER IS AN EXISTING, VERIFIED CLIENT ===\n"
            f"- Name: {ident.get('name') or '—'} | Account login(s): {', '.join('#'+str(x) for x in ident.get('logins', []))}\n"
            f"- Email: {ident.get('email') or '—'}\n"
            f"- This is a REAL EXISTING CLIENT = a VERIFIED ACCOUNT. They are fully verified.\n"
            f"- Account status: {ident.get('status') or 'active'}"
            f"{' | ⚠ FLAGGED — be careful, escalate sensitive requests' if ident.get('flagged') else ''}"
            f"{' | IB/partner' if ident.get('is_ib') else ''}\n"
            "CRITICAL: NEVER tell this person to 'verify your account' or 'complete KYC'. They are an "
            "existing verified client — any 'KYC pending' value you might see below is just an old-system "
            "artifact and is IRRELEVANT; ignore it completely. Do NOT bring up verification/KYC at all "
            "unless THEY ask about it.\n"
            "Their FULL financial history (balance, deposits/withdrawals, pending transactions, trades) is "
            "in the CLIENT ACCOUNT CONTEXT below. Greet them BY NAME as a valued existing client. Be "
            "proactive about their actual situation (a pending withdrawal, low margin, idle funds, a "
            "negative balance) — but never ask for info you already know, and never ask them to verify."
        )
    if ident.get("kind") == "lead":
        return (
            "\n\n=== KNOWN CONTACT — THIS NUMBER IS AN EXISTING LEAD (not a funded client yet) ===\n"
            f"- Name: {ident.get('name') or '—'} | Country: {ident.get('country') or '—'} | Source: {ident.get('source') or '—'}\n"
            f"- Email: {ident.get('email') or '—'} | Lead status: {ident.get('status') or 'new'} | Badge: {ident.get('badge') or '—'}\n"
            f"- KYC: {ident.get('kyc') or '—'} | Experience: {ident.get('experience_level') or 'unknown'} | Interest: {ident.get('interest') or 'unknown'}\n"
            "INSTRUCTIONS: greet by name, recognise they already showed interest in TNFX, pick up where "
            "they left off, and guide them to open & fund an account. Don't treat them as a cold stranger."
        )
    return ""


def greeting_hint(ident):
    """A short instruction telling the AI HOW to open, based on who this is."""
    if ident["kind"] == "client":
        seg = ident.get("segment")
        nm = ident.get("name") or "there"
        if seg == "lapsed_depositor":
            return f"This is RETURNING client {nm} who deposited before but has been quiet 90+ days. Greet them warmly by name ('long time!'), then re-engage with a market update / win-back offer."
        if seg == "registered_no_deposit":
            return f"This is existing client {nm} who registered but NEVER funded. Greet by name, then guide them to make their first deposit (mention the offer)."
        if seg in ("active_depositor", "depositor", "new_client"):
            return f"This is an active client {nm}. Greet by name, be helpful and look for an upsell/top-up opportunity."
        return f"This is existing client {nm}. Greet warmly by name."
    if ident["kind"] == "lead":
        nm = ident.get("name") or "there"
        return f"This is a known lead ({nm}) who has not opened an account yet. Be welcoming, qualify them, and drive them to register."
    return "This is a BRAND-NEW contact. Welcome them, ask what they're looking for, qualify (beginner/advanced), and guide them to open an account."


# ─────────────────── live social/campaign awareness (FB + IG posts) ───────────────────
import os as _os
import time as _time
import meta_config
_POSTS_CACHE = {"at": 0.0, "text": ""}
_META_TOKEN = _os.getenv("META_ACCESS_TOKEN", meta_config.META_ACCESS_TOKEN)
_META_PAGE = _os.getenv("META_PAGE_ID", meta_config.META_PAGE_ID)
_GRAPH = "https://graph.facebook.com/v19.0"


def recent_social_posts():
    """Recent TNFX Facebook/Instagram posts so the bot KNOWS our live campaigns, competitions
    and offers (e.g. the Iraq×France prediction bonus). Cached 30 min so we don't hit Meta per msg."""
    if _POSTS_CACHE["text"] and (_time.time() - _POSTS_CACHE["at"] < 1800):
        return _POSTS_CACHE["text"]
    try:
        import requests
        pt = requests.get(f"{_GRAPH}/{_META_PAGE}", params={"fields": "access_token", "access_token": _META_TOKEN}, timeout=8).json()
        ptoken = pt.get("access_token", _META_TOKEN)
        posts = []
        for edge in ("posts", "feed"):
            r = requests.get(f"{_GRAPH}/{_META_PAGE}/{edge}", params={"fields": "message,created_time", "limit": 10, "access_token": ptoken}, timeout=8).json()
            posts = [(p.get("created_time", "")[:10], p.get("message", "").strip()) for p in r.get("data", []) if p.get("message")]
            if posts:
                break
        if posts:
            block = ("\n\n=== TNFX'S LIVE SOCIAL POSTS & CAMPAIGNS (our actual Facebook/Instagram posts) ===\n"
                     "These are our REAL current posts/promotions/competitions. If a customer mentions one "
                     "(e.g. a match-prediction competition, a bonus, an offer), you ALREADY KNOW it — explain "
                     "it from here, NEVER ask them to send you a link:\n"
                     + "\n".join(f"- ({d}) {m[:280]}" for d, m in posts[:10]))
            _POSTS_CACHE.update(at=_time.time(), text=block)
            return block
    except Exception:
        pass
    return _POSTS_CACHE["text"]


def live_spread_block():
    """Spreads aren't stored in our DB (they live on the MT5 server). Until a live spread feed is
    wired, the bot uses TEAM-TAUGHT spreads and NEVER invents a number."""
    return ("\n\n=== SPREADS ===\n"
            "Spread = ask − bid. If TEAM TRAINING above gives the spread for the symbol they ask "
            "about, use it — quote a small RANGE: the lowest spread you were taught, plus ~2-3 points "
            "for the typical higher end (e.g. 'gold spread is usually 18-21 points'). If you have NOT "
            "been taught the spread for that symbol, say our spreads are tight/competitive and you'll "
            "confirm the exact live spread — NEVER make up a spread number.")


# ─────────────────── reply generation ───────────────────
def _sales_system(db, ident, offer):
    try:
        import chat_router as cr
        import kb_articles
        import ai_config  # noqa
        base = getattr(cr, "PERSONA", "You are the TNFX assistant.") + "\n\n=== COMPANY INFO ===\n" + getattr(cr, "COMPANY_INFO", "")
        base += "\n\n=== KNOWLEDGE BASE INDEX ===\n" + kb_articles.article_index()
        # live market data so it can answer price/spread questions (was missing -> "go check MT4/5")
        try:
            base += "\n\n=== " + cr.build_market_snapshot(db)
            base += cr.live_prices_block(db)
            base += live_spread_block()
        except Exception:
            pass
        base += recent_social_posts()       # live FB/IG campaign awareness
        # explicit known-contact snapshot (read them FIRST, talk to them as known)
        base += verification_snapshot(ident)
        if ident.get("kind") == "client" and ident.get("logins"):
            try:
                # read ALL of the person's accounts, not just one
                ctx = cr.build_client_context(db, ident.get("logins") or [ident["login"]])
                if ctx:
                    base += "\n\n=== CLIENT ACCOUNT CONTEXT (full history) ===\n" + ctx
            except Exception:
                pass
    except Exception:
        base = "You are the TNFX (forex broker) WhatsApp sales assistant." + verification_snapshot(ident)
    # team training (staff '#' lessons) — highest priority, above defaults
    try:
        base += teachings_block(db)
    except Exception:
        pass
    playbook = (
        "\n\n=== HOW YOU TALK (READ THIS CAREFULLY) ===\n"
        "You are a real member of the TNFX team chatting on WhatsApp — NOT a robot, NOT an "
        "automated assistant. Sound like an actual Iraqi/Arab person texting a friend:\n"
        "• Talk in THEIR language and dialect (Iraqi/Gulf/Levantine Arabic, or English — mirror them). "
        "Use natural, casual, spoken words — contractions, slang, the way people really text.\n"
        "• Keep it SHORT and human — usually ONE short line, like a real WhatsApp text. Never a "
        "paragraph, never bullet points, never a formal 'Dear customer' tone.\n"
        "• React naturally to what they actually said. Be warm, a little personality, light humour is "
        "fine. Vary your openings — don't repeat the same scripted greeting every time.\n"
        "• Max ONE emoji, and only when it feels natural. Don't stuff emojis. Don't sound like a brochure.\n"
        "• NEVER say you're a bot/AI/assistant. NEVER list features robotically. Talk, don't pitch-dump.\n"
        "\n=== WHAT YOU ALREADY KNOW (NEVER ASK IT) ===\n"
        "You can SEE the person's full record above (whether they're a client, a lead, or brand new, "
        "their accounts, deposits, KYC, everything). So:\n"
        "• NEVER ask 'do you have an account with us?' — you already know. If they're a client, talk "
        "to them like one and reference their account.\n"
        "• IMPORTANT: people often message from a DIFFERENT number than the one on their trading "
        "account. So if this number isn't matched to a client BUT the person SAYS they have an account "
        "(or asks about 'their' account/deposit/balance/email), DO NOT tell them to open a new account "
        "and DO NOT call them a stranger. Instead believe them, apologise briefly, and ask for their "
        "ACCOUNT NUMBER (login) or registered EMAIL so you can pull it up — say you'll check it for them. "
        "Only push registration on people who are genuinely new and don't claim an account.\n"
        "• Never ask for info that's already in their record (name, country, etc.).\n"
        "• EXISTING CLIENTS ARE VERIFIED — anyone who is a client (and especially anyone with a deposit) "
        "is a fully VERIFIED account. NEVER tell a client to 'verify your account' or 'complete KYC', and "
        "NEVER bring up KYC/verification to them. Ignore any 'KYC pending/unknown' status on an existing "
        "client — it's an old-system artifact, not a real requirement. Only discuss verification if the "
        "client explicitly asks about it.\n"
        "\n=== DON'T BE REPETITIVE OR ROBOTIC ===\n"
        "You can see the WHOLE conversation above. NEVER repeat a question, greeting, or sentence you "
        "already said earlier in this chat — that makes you sound like a broken bot and infuriates "
        "people. If you already greeted them, don't greet again — just continue naturally. Move the "
        "conversation FORWARD every message. If they seem annoyed or repeat themselves, it means you "
        "missed something — acknowledge it and fix it, don't loop. Answer what they actually asked.\n"
        "\n=== YOUR JOB ===\n"
        "Help and (for non-clients) gently move them toward opening + funding an account. Qualify "
        "naturally in conversation (beginner or pro? gold or forex?) — don't interrogate. Send the "
        "registration link only when they're actually ready. COMPLIANCE: never promise guaranteed "
        "profit; mention trading has risk if you make a money claim. If they ask for a human, or raise "
        "a withdrawal/complaint/legal issue, set escalate=true and tell them a specialist will help.\n"
    )
    if offer:
        playbook += f"CURRENT OFFER to mention when it fits naturally: {offer}\n"
    playbook += "CONTEXT FOR THIS CHAT: " + greeting_hint(ident) + "\n"
    playbook += (
        'RETURN ONLY JSON (no prose): {"reply": "<your short, human whatsapp message>", '
        '"experience_level": "beginner|intermediate|advanced|unknown", '
        '"interest": "<forex/gold/indices/crypto/unknown>", "goal": "<short or empty>", '
        '"intent": "<greeting|qualifying|offer|register|fund|support|other>", '
        '"ready_to_register": true/false, "escalate": true/false}'
    )
    return base + playbook


def _is_arabic(s):
    return any('؀' <= ch <= 'ۿ' for ch in (s or ""))


def _extract_reply(raw):
    """ROBUSTLY get {reply, ...} from the model output. The model SOMETIMES prepends the reply
    text before the JSON, or wraps it — we must NEVER send raw JSON to the customer."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # 1) whole thing is clean JSON
    try:
        d = json.loads(raw)
        if isinstance(d, dict) and d.get("reply"):
            return d
    except Exception:
        pass
    # 2) a JSON object is embedded somewhere in the text -> parse the first balanced {...}
    import re as _re
    for m in _re.finditer(r'\{.*?\}', raw, _re.S):
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and d.get("reply"):
                return d
        except Exception:
            continue
    # 3) greedy {...} (reply may contain braces/newlines)
    m = _re.search(r'\{.*\}', raw, _re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and d.get("reply"):
                return d
        except Exception:
            pass
    # 4) no valid JSON -> strip any JSON-looking block and return the human text only
    cleaned = _re.sub(r'\{.*\}', '', raw, flags=_re.S).strip()
    return {"reply": cleaned or "🙏"}


def is_opt_out(msg):
    m = (msg or "").strip().lower()
    return any(k in m for k in OPT_OUT)


def is_sensitive(msg):
    m = (msg or "").strip().lower()
    return any(k in m for k in SENSITIVE)


def generate_reply(db, phone, message, history=None, dry_run=False):
    """Full pipeline for one inbound message. Returns a result dict; persists unless dry_run."""
    ensure_schema(db)
    cfg = get_config(db)
    ident = resolve_identity(db, phone)
    result = {"phone": phone, "identity": ident, "escalate": False, "opted_out": False,
              "reply": "", "qualification": {}, "actions": [], "dry_run": dry_run}

    # 0) TEACHING: a message starting with '#' from a STAFF phone trains the bot (not a customer chat)
    if (message or "").lstrip().startswith("#"):
        if is_staff_phone(db, phone):
            lesson = message.lstrip().lstrip("#").strip()
            if lesson:
                result["taught"] = True
                result["reply"] = "✅ Got it — I've learned that and I'll apply it from now on."
                if not dry_run:
                    add_teaching(db, lesson, author_phone=phone)
                    _log(db, phone, "in", message, is_ai=False)
                    _log(db, phone, "out", result["reply"], is_ai=True)
                result["actions"].append("taught")
                return result
        # non-staff '#' message -> OPEN A SUPPORT TICKET. Per the desk, tickets are created ONLY
        # through the assistant chat or WhatsApp by starting a message with '#' (manual creation
        # in the CRM/portal is disabled).
        else:
            tnote = message.lstrip().lstrip("#").strip()
            if tnote:
                cid = None
                if ident.get("kind") == "client" and ident.get("login"):
                    cid = db.execute(text("SELECT id FROM clients WHERE login=:l LIMIT 1"),
                                     {"l": ident["login"]}).scalar()
                cname = ((ident.get("name") or "WhatsApp contact") + f" ({phone})")[:160]
                ar0 = _is_arabic(tnote)
                result["reply"] = ("✅ تم إنشاء تذكرتك وإرسالها لفريقنا، وسنتابع معك هنا."
                                   if ar0 else
                                   "✅ Your ticket has been created and sent to our team. We'll follow up with you here.")
                if not dry_run:
                    try:
                        db.execute(text("""
                            INSERT INTO tickets (source, creator_type, creator_id, creator_name, section, note,
                                                 critical, route, for_ai, status, admin_unread)
                            VALUES ('whatsapp','client',:cid,:cn,'WhatsApp',:note,'medium','review',FALSE,'under_review',TRUE)
                        """), {"cid": cid, "cn": cname, "note": tnote[:4000]})
                        db.commit()
                    except Exception:
                        db.rollback()
                    _log(db, phone, "in", message, is_ai=False)
                    _log(db, phone, "out", result["reply"], is_ai=True)
                result["actions"].append("ticket_created")
                return result
            # bare '#' with no text -> fall through as a normal message
            message = message.lstrip().lstrip("#").strip() or message

    ar = _is_arabic(message)
    # 1) opt-out
    if is_opt_out(message):
        result["opted_out"] = True
        result["reply"] = ("تم إيقاف الرسائل، ما راح توصلك رسائل بعد. ارسل أي رسالة وقت ما تحب لترجع 👋"
                           if ar else "You've been unsubscribed. Message us anytime to resume. 👋")
        if not dry_run:
            _log(db, phone, "in", message, is_ai=False)
            _log(db, phone, "out", result["reply"], is_ai=True)
            _mark_opt_out(db, ident)
            _upsert_convo(db, phone, ident, status="opted_out")
        result["actions"].append("opt_out")
        return result

    # 2) sensitive -> human handoff (in the customer's language)
    if is_sensitive(message):
        result["escalate"] = True
        result["reply"] = ("تمام، راح أوصل طلبك لأحد المختصين عدنا وراح يتواصل وياك قريب 🙏 "
                           "بهالأثناء، أكدر أساعدك بأي شي ثاني؟"
                           if ar else "Sure — I'll pass this to one of our specialists who'll "
                           "follow up with you shortly 🙏 Anything else I can help with meanwhile?")
        if not dry_run:
            _log(db, phone, "in", message, is_ai=False)
            _log(db, phone, "out", result["reply"], is_ai=True, escalated=True)
            _upsert_convo(db, phone, ident, status="escalated")
        result["actions"].append("escalated_to_human")
        return result

    # 3) AI reply
    try:
        import ai_config
        if not ai_config.is_configured():
            result["reply"] = "(AI not configured — add the Claude key in ai_config.py)"
            result["error"] = "ai_not_configured"
            return result
        import anthropic
        system = _sales_system(db, ident, cfg.get("current_offer"))
        msgs = []
        for h in (history or [])[-10:]:
            role = "assistant" if h.get("role") == "assistant" else "user"
            if h.get("content"):
                msgs.append({"role": role, "content": str(h["content"])[:2000]})
        msgs.append({"role": "user", "content": str(message)[:2000]})
        client = anthropic.Anthropic(api_key=ai_config.ANTHROPIC_API_KEY)
        # Opus 4.8 + ADAPTIVE THINKING — it reasons about who this is, what they actually need,
        # and our campaigns before replying. max_tokens must cover thinking + the answer.
        try:
            resp = client.messages.create(model=WA_MODEL, max_tokens=3000,
                                           thinking={"type": "adaptive"},
                                           system=system, messages=msgs)
        except Exception:
            resp = client.messages.create(model=WA_MODEL, max_tokens=900,
                                           system=system, messages=msgs)
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        data = _extract_reply(raw)
    except Exception as e:
        result["reply"] = "Thanks for your message! One of our team will reply shortly."
        result["error"] = str(e)[:200]
        return result

    reply = (data.get("reply") or "").strip() or "👍"
    # The shared persona makes the model emit an internal [[ESCALATE: ...]] marker when it needs a
    # human. It must NEVER reach the customer — strip it, and ROUTE it to staff as a ticket instead.
    esc_reason = None
    m = re.search(r"\[\[\s*ESCALATE\s*:\s*(.+?)\]\]", reply, re.I | re.S)
    if m:
        esc_reason = m.group(1).strip()
    reply = re.sub(r"\[\[.*?\]\]", "", reply, flags=re.S).strip() or "🙏"  # strip ALL [[...]] markers
    result["reply"] = reply
    result["escalate"] = bool(data.get("escalate")) or bool(esc_reason)
    qual = {"experience_level": data.get("experience_level"), "interest": data.get("interest"),
            "goal": data.get("goal"), "intent": data.get("intent"),
            "ready_to_register": bool(data.get("ready_to_register"))}
    result["qualification"] = qual

    # 4) auto-actions (CRM writeback) — skipped on dry_run
    actions = _auto_actions(db, phone, ident, qual, cfg, dry_run)
    result["actions"] = actions
    if result["escalate"]:
        result["actions"].append("escalated_to_human")
        result["escalation_reason"] = esc_reason or message
    if not dry_run:
        _log(db, phone, "in", message, is_ai=False)
        _log(db, phone, "out", result["reply"], is_ai=True, escalated=result["escalate"])
        _upsert_convo(db, phone, ident, status="escalated" if result["escalate"] else "open")
        if result["escalate"]:
            _open_escalation_ticket(db, phone, ident, esc_reason or message, message)
    return result


def _open_escalation_ticket(db, phone, ident, reason, customer_msg):
    """Route a WhatsApp escalation to the Tickets system so staff SEE it and act (same place the
    portal-chat escalations go). Visible in the Tickets page + picked up by the triage agent."""
    try:
        who = ident.get("name") or f"WhatsApp {phone[-4:]}"
        note = (f"WhatsApp AI escalation — {who} ({phone}).\n"
                f"Reason: {reason}\nCustomer message: {customer_msg}")
        db.execute(text("""
            INSERT INTO tickets (source, creator_type, creator_id, creator_name, section, note,
                                 critical, route, for_ai, status, admin_unread)
            VALUES ('whatsapp','client',:cid,:cname,'WhatsApp AI — escalation',:note,'medium','review',FALSE,'under_review',TRUE)
        """), {"cid": ident.get("login") or ident.get("lead_id"), "cname": who, "note": note[:4000]})
        db.commit()
    except Exception:
        db.rollback()


# ─────────────────── persistence helpers ───────────────────
def _log(db, phone, direction, body, is_ai=False, escalated=False, dry_run=False):
    db.execute(text("""INSERT INTO wa_messages (phone, direction, body, is_ai, escalated, dry_run)
                       VALUES (:p,:d,:b,:ai,:e,:dr)"""),
               {"p": phone, "d": direction, "b": body, "ai": is_ai, "e": escalated, "dr": dry_run})
    db.commit()


def _upsert_convo(db, phone, ident, status="open"):
    db.execute(text("""
        INSERT INTO wa_conversations (phone, identity_kind, identity_name, client_login, lead_id, status, last_message_at)
        VALUES (:p,:k,:nm,:cl,:ld,:st,NOW())
        ON CONFLICT (phone) DO UPDATE SET identity_kind=:k, identity_name=:nm, client_login=:cl,
            lead_id=:ld, status=:st, last_message_at=NOW(),
            messages_in=wa_conversations.messages_in+1
    """), {"p": phone, "k": ident.get("kind"), "nm": ident.get("name"),
           "cl": ident.get("login"), "ld": ident.get("lead_id"), "st": status})
    db.commit()


def _mark_opt_out(db, ident):
    if ident.get("lead_id"):
        db.execute(text("UPDATE leads SET wa_opt_out=TRUE WHERE id=:i"), {"i": ident["lead_id"]})
        db.commit()


def _auto_actions(db, phone, ident, qual, cfg, dry_run):
    """Write the CRM updates the desk asked for. Returns the list of actions taken (or would take)."""
    acts = []
    ai_own = cfg.get("ai_owns_leads", True)
    if ident["kind"] == "client" and ident.get("login"):
        sets = ["phone_verified=TRUE"]
        acts.append("phone_verified")
        if ai_own:
            sets.append("ai_managed=TRUE"); acts.append("ai_owned")
        if not dry_run:
            db.execute(text(f"UPDATE clients SET {', '.join(sets)} WHERE login=:l"), {"l": ident["login"]})
            db.commit()
    elif ident["kind"] == "lead" and ident.get("lead_id"):
        sets = ["source='whatsapp'", "phone_verified=TRUE"]
        acts += ["source_whatsapp", "phone_verified"]
        if ai_own:
            sets.append("ai_managed=TRUE"); acts.append("ai_owned")
        if qual.get("experience_level") and qual["experience_level"] != "unknown":
            sets.append("experience_level=:exp"); acts.append("qualified")
        if qual.get("interest") and qual["interest"] != "unknown":
            sets.append("interest=:intr")
        if qual.get("goal"):
            sets.append("goal=:goal")
        if not dry_run:
            db.execute(text(f"UPDATE leads SET {', '.join(sets)}, updated_at=NOW() WHERE id=:i"),
                       {"i": ident["lead_id"], "exp": qual.get("experience_level"),
                        "intr": qual.get("interest"), "goal": qual.get("goal")})
            db.commit()
    else:  # brand new -> capture a lead
        acts.append("lead_created")
        if not dry_run:
            lid = db.execute(text("""
                INSERT INTO leads (full_name, phone, source, status, ai_managed, phone_verified,
                                   experience_level, interest, goal, score, created_at, updated_at)
                VALUES (:nm,:ph,'whatsapp','new',:ai,TRUE,:exp,:intr,:goal,40,NOW(),NOW())
                RETURNING id
            """), {"nm": ident.get("name") or f"WhatsApp {phone[-4:]}", "ph": phone, "ai": ai_own,
                   "exp": qual.get("experience_level"), "intr": qual.get("interest"), "goal": qual.get("goal")}).scalar()
            db.commit()
            ident["lead_id"] = lid
    return acts


def check_registration(db, phone):
    """Has this WhatsApp number registered / opened an account? (for the AI to confirm)."""
    ident = resolve_identity(db, phone)
    if ident["kind"] == "client":
        return {"registered": True, "login": ident.get("login"), "name": ident.get("name")}
    nine = last9(phone)
    reg = db.execute(text("""
        SELECT id, mt_login FROM registrations
        WHERE RIGHT(regexp_replace(COALESCE(phone,''),'\\D','','g'),9)=:n ORDER BY id DESC LIMIT 1
    """), {"n": nine}).fetchone() if nine else None
    if reg:
        return {"registered": True, "registration_id": reg[0], "mt_login": reg[1]}
    return {"registered": False}
