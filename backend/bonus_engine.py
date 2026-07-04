"""
TNFX Bonus Engine — welcome bonus, tiered deposit bonus, special offers,
withdrawal margin guard + proportional bonus clawback.

Design notes (read before changing):
- Bonus credit is stored on clients.credit (the account credit column). Deposits
  and withdrawals are still SIMULATION (portal_money_requests), so bonus crediting
  here is also simulated — it writes to clients.credit + a bonus_grants ledger, it
  does NOT push credit to the live MT server. Wire that into the bridge only after
  the deposit/withdraw gateway is real (see SAFETY RULES in CLAUDE.md).
- Welcome eligibility uses account_identifiers (CID/IP/MQID) — the SAME live
  abuse-detection data the bridge writes. A client is eligible only after they have
  LOGGED IN to MT (identifiers exist for their login), their device/IP is NOT shared
  with any other account (no network), and their CID is new to our system.
- All config lives in bonus_config (singleton row id=1) so the desk can tune it and
  the AI bot can read it. DEFAULTS below are the fallback if the row is missing.
"""
from __future__ import annotations
import json
import re
import time
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import SessionLocal

# ───────────────────────── DEFAULT CONFIG ─────────────────────────
DEFAULTS = {
    "bonuses_enabled":            True,
    "welcome_amount":             50.0,
    "welcome_withdraw_min_nodep": 100.0,   # min withdrawal if the client never deposited
    "welcome_withdraw_min_dep":   50.0,    # min withdrawal once the client has deposited
    "dep_tier1_pct":              50.0,    # 50% on the first $1,000 of deposits
    "dep_tier1_cap":              1000.0,  # deposit amount the 50% tier applies to
    "dep_tier2_pct":              20.0,    # 20% on every dollar above tier-1
    "dep_total_cap":              5000.0,  # max TOTAL deposit-bonus a client can ever earn
    "margin_floor_pct":           150.0,   # withdrawal blocked if margin level would drop below this
    "blocked_countries":          ["India", "Pakistan", "Egypt"],
    # ── birthday bonus (see birthday_engine.py) ──
    "birthday_enabled":              True,
    "birthday_amount":               100.0,  # the gift
    "birthday_before_days":          5,       # claim opens N days before the birthday
    "birthday_after_days":           2,       # claim closes N days after
    "birthday_deposit_window_days":  365,     # must have deposited within this many days to be eligible
}

# ISO-2 / common aliases so a blocked "India" also catches "IN", etc.
_COUNTRY_ALIASES = {
    "india": {"india", "in", "ind"},
    "pakistan": {"pakistan", "pk", "pak"},
    "egypt": {"egypt", "eg", "egy", "arab republic of egypt"},
    "bangladesh": {"bangladesh", "bd"},
    "nigeria": {"nigeria", "ng"},
}

GRANT_DEPOSIT_KINDS = ("deposit_50", "deposit_20", "special")


# ───────────────────────── CONFIG ACCESS ─────────────────────────
def get_config(db: Session) -> dict:
    cfg = dict(DEFAULTS)
    try:
        row = db.execute(text("SELECT data FROM bonus_config WHERE id=1")).fetchone()
        if row and row[0]:
            stored = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            cfg.update({k: v for k, v in stored.items() if v is not None})
    except Exception:
        db.rollback()
    # normalise types
    cfg["bonuses_enabled"] = bool(cfg.get("bonuses_enabled", True))
    if not isinstance(cfg.get("blocked_countries"), list):
        cfg["blocked_countries"] = list(DEFAULTS["blocked_countries"])
    return cfg


def save_config(db: Session, patch: dict) -> dict:
    cfg = get_config(db)
    for k, v in (patch or {}).items():
        if k in DEFAULTS:
            cfg[k] = v
    db.execute(text("""
        INSERT INTO bonus_config (id, data, updated_at) VALUES (1, CAST(:d AS JSONB), NOW())
        ON CONFLICT (id) DO UPDATE SET data=CAST(:d AS JSONB), updated_at=NOW()
    """), {"d": json.dumps(cfg)})
    db.commit()
    return cfg


# ───────────────────────── COUNTRY RULES ─────────────────────────
def _norm(s) -> str:
    return (s or "").strip().lower()


def country_blocked(cfg: dict, country: str) -> bool:
    c = _norm(country)
    if not c:
        return False
    for blocked in cfg.get("blocked_countries", []):
        b = _norm(blocked)
        if not b:
            continue
        if c == b:
            return True
        aliases = _COUNTRY_ALIASES.get(b)
        if aliases and c in aliases:
            return True
        # also catch "Egypt" inside "Arab Republic of Egypt"
        if len(b) > 3 and (b in c or c in b):
            return True
    return False


def country_offer_eligible(offer_countries, country: str) -> bool:
    """offer_countries is the offer's allow-list. Empty/None => all countries allowed."""
    if not offer_countries:
        return True
    c = _norm(country)
    return any(_norm(x) == c for x in offer_countries)


# ───────────────────────── LOGIN RESOLUTION ─────────────────────────
def client_logins(db: Session, client_id: int) -> list:
    """Same phone+platform aggregation the Clients list / portal uses."""
    base = db.execute(text(
        "SELECT login, phone, COALESCE(platform,'') FROM clients WHERE id=:id"
    ), {"id": client_id}).fetchone()
    if not base:
        return []
    logins = {base[0]} if base[0] is not None else set()
    if base[1]:
        for r in db.execute(text(
            "SELECT login FROM clients WHERE phone=:p AND COALESCE(platform,'')=:pl AND login IS NOT NULL"
        ), {"p": base[1], "pl": base[2]}).fetchall():
            logins.add(r[0])
    return sorted(l for l in logins if l is not None)


# ───────────────────────── NETWORK / DEVICE ELIGIBILITY ─────────────────────────
def has_logged_in(db: Session, logins: list) -> bool:
    """True once the client has logged into MT (the bridge captured a CID/IP for them)."""
    if not logins:
        return False
    n = db.execute(text("""
        SELECT COUNT(*) FROM account_identifiers
        WHERE login = ANY(:logins) AND identifier_type IN ('cid','ip','mqid')
          AND identifier_value NOT IN ('0','')
    """), {"logins": logins}).scalar()
    return bool(n)


def network_state(db: Session, logins: list) -> dict:
    """
    Returns whether ANY device/IP/MQID of these logins is shared with an OUTSIDE
    account (=> has network), and whether the client's CID is new (not shared).
    """
    out = {"logged_in": False, "has_network": False, "new_cid": False,
           "has_cid": False, "shared": []}
    if not logins:
        return out
    ids = db.execute(text("""
        SELECT DISTINCT identifier_type, identifier_value
        FROM account_identifiers
        WHERE login = ANY(:logins) AND identifier_type IN ('cid','ip','mqid')
          AND identifier_value NOT IN ('0','')
    """), {"logins": logins}).fetchall()
    if not ids:
        return out
    out["logged_in"] = True
    own = set(logins)
    cid_shared = False
    has_cid = False
    for itype, ival in ids:
        if itype == "cid":
            has_cid = True
        ext = db.execute(text("""
            SELECT DISTINCT login FROM account_identifiers
            WHERE identifier_type=:t AND identifier_value=:v
              AND identifier_value NOT IN ('0','')
        """), {"t": itype, "v": ival}).fetchall()
        ext_logins = {r[0] for r in ext} - own
        if ext_logins:
            out["has_network"] = True
            out["shared"].append({"type": itype, "value": ival,
                                   "other_logins": sorted(ext_logins)[:10]})
            if itype == "cid":
                cid_shared = True
    out["has_cid"] = has_cid
    # CID is "new to our system" if the client has a CID and none of them are shared
    out["new_cid"] = has_cid and not cid_shared
    return out


# ───────────────────────── DEPOSIT BONUS MATH ─────────────────────────
def total_deposits(db: Session, client_id: int) -> float:
    try:
        v = db.execute(text("""
            SELECT COALESCE(SUM(amount),0) FROM portal_money_requests
            WHERE client_id=:id AND kind='deposit'
        """), {"id": client_id}).scalar()
        return float(v or 0)
    except Exception:
        db.rollback()
        return 0.0


def deposit_bonus_given(db: Session, client_id: int) -> float:
    """Total deposit-style bonus already credited (50%/20%/special), net of clawback."""
    try:
        v = db.execute(text("""
            SELECT COALESCE(SUM(amount - COALESCE(clawed_back,0)),0) FROM bonus_grants
            WHERE client_id=:id AND kind = ANY(:kinds) AND status <> 'cancelled'
        """), {"id": client_id, "kinds": list(GRANT_DEPOSIT_KINDS)}).scalar()
        return float(v or 0)
    except Exception:
        db.rollback()
        return 0.0


def tier_breakdown(cfg: dict, prior_deposits: float, amount: float) -> dict:
    """How a deposit of `amount` splits across the 50% / 20% tiers, given prior_deposits."""
    t1cap = float(cfg["dep_tier1_cap"]); t1pct = float(cfg["dep_tier1_pct"]) / 100.0
    t2pct = float(cfg["dep_tier2_pct"]) / 100.0
    t1_before = min(prior_deposits, t1cap)
    t1_after = min(prior_deposits + amount, t1cap)
    t1_portion = max(0.0, t1_after - t1_before)
    t2_portion = max(0.0, amount - t1_portion)
    return {
        "tier1_portion": t1_portion, "tier1_bonus": round(t1_portion * t1pct, 2),
        "tier2_portion": t2_portion, "tier2_bonus": round(t2_portion * t2pct, 2),
    }


def active_offers(db: Session, country: str | None = None, now: float | None = None) -> list:
    """Active special offers within their deadline, optionally country-filtered."""
    cfg = get_config(db)
    try:
        rows = db.execute(text("""
            SELECT id, name, percent, cap, min_deposit, countries, starts_at, ends_at
            FROM bonus_offers
            WHERE active=TRUE
              AND (starts_at IS NULL OR starts_at <= NOW())
              AND (ends_at   IS NULL OR ends_at   >= NOW())
            ORDER BY ends_at NULLS LAST, id
        """)).fetchall()
    except Exception:
        db.rollback()
        return []
    out = []
    for r in rows:
        cc = r[5] or []
        if country is not None:
            if country_blocked(cfg, country):
                continue
            if not country_offer_eligible(cc, country):
                continue
        out.append({
            "id": r[0], "name": r[1], "percent": float(r[2] or 0),
            "cap": float(r[3] or 0), "min_deposit": float(r[4] or 0),
            "countries": cc, "starts_at": str(r[6]) if r[6] else None,
            "ends_at": str(r[7]) if r[7] else None,
        })
    return out


def offer_claimed(db: Session, offer_id: int, client_id: int) -> bool:
    try:
        n = db.execute(text("SELECT COUNT(*) FROM bonus_offer_claims WHERE offer_id=:o AND client_id=:c"),
                       {"o": offer_id, "c": client_id}).scalar()
        return bool(n)
    except Exception:
        db.rollback()
        return False


def login_is_standard(db: Session, login) -> bool:
    """Deposit/welcome bonus applies to STANDARD accounts only. Type is derived from
    the MT GROUP (any STD* group = Standard) — NOT from trading_accounts.account_type,
    which is unreliable ('live'/NULL/raw group). Unknown login -> allow (can't tell)."""
    if not login:
        return True
    try:
        import account_types
        g = db.execute(text("SELECT group_name FROM trading_accounts WHERE login=:l"),
                       {"l": int(login)}).scalar()
        if g is None:
            return True
        return account_types.is_standard_group(g)
    except Exception:
        return True


def preview_deposit_bonus(db: Session, client_id: int, amount: float, login=None) -> dict:
    """What bonus a deposit of `amount` would earn RIGHT NOW (for the deposit screen)."""
    cfg = get_config(db)
    crow = db.execute(text("SELECT country FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    country = (crow[0] if crow else "") or ""
    if not cfg["bonuses_enabled"] or country_blocked(cfg, country):
        return {"bonus": 0.0, "lines": [], "blocked": country_blocked(cfg, country),
                "enabled": cfg["bonuses_enabled"]}
    if not login_is_standard(db, login):
        return {"bonus": 0.0, "lines": [], "blocked": False, "enabled": True,
                "not_standard": True}
    amount = max(0.0, float(amount or 0))
    prior = total_deposits(db, client_id)
    given = deposit_bonus_given(db, client_id)
    cap_left = max(0.0, float(cfg["dep_total_cap"]) - given)

    # a special offer the client is eligible for & hasn't used takes precedence
    offers = active_offers(db, country=country)
    chosen = None
    for o in offers:
        if amount >= o["min_deposit"] and not offer_claimed(db, o["id"], client_id):
            chosen = o
            break
    lines = []
    if chosen:
        raw = amount * chosen["percent"] / 100.0
        bonus = min(raw, chosen["cap"]) if chosen["cap"] else raw
        bonus = min(bonus, cap_left)
        lines.append({"label": f"{chosen['name']} — {chosen['percent']:.0f}% up to ${chosen['cap']:,.0f}",
                      "bonus": round(bonus, 2), "special": True, "offer_id": chosen["id"]})
        return {"bonus": round(bonus, 2), "lines": lines, "blocked": False, "enabled": True,
                "special": chosen}
    tb = tier_breakdown(cfg, prior, amount)
    bonus = tb["tier1_bonus"] + tb["tier2_bonus"]
    bonus = min(bonus, cap_left)
    if tb["tier1_bonus"] > 0:
        lines.append({"label": f"{cfg['dep_tier1_pct']:.0f}% on ${tb['tier1_portion']:,.0f}",
                      "bonus": round(tb["tier1_bonus"], 2), "special": False})
    if tb["tier2_bonus"] > 0:
        lines.append({"label": f"{cfg['dep_tier2_pct']:.0f}% on ${tb['tier2_portion']:,.0f}",
                      "bonus": round(tb["tier2_bonus"], 2), "special": False})
    return {"bonus": round(bonus, 2), "lines": lines, "blocked": False, "enabled": True,
            "cap_left": round(cap_left, 2)}


def credit_deposit_bonus(db: Session, client_id: int, login, amount: float,
                         deposit_request_id=None) -> dict:
    """Auto-credit the deposit bonus for a recorded deposit. Idempotent per deposit_request_id."""
    cfg = get_config(db)
    if not cfg["bonuses_enabled"]:
        return {"bonus": 0.0, "skipped": "disabled"}
    crow = db.execute(text("SELECT country FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    country = (crow[0] if crow else "") or ""
    if country_blocked(cfg, country):
        return {"bonus": 0.0, "skipped": "country_blocked"}
    if not login_is_standard(db, login):
        return {"bonus": 0.0, "skipped": "not_standard"}

    # idempotency: don't double-credit the same deposit request
    if deposit_request_id is not None:
        dup = db.execute(text("SELECT COUNT(*) FROM bonus_grants WHERE deposit_request_id=:d"),
                         {"d": deposit_request_id}).scalar()
        if dup:
            return {"bonus": 0.0, "skipped": "already_credited"}

    amount = max(0.0, float(amount or 0))
    # prior deposits = everything BEFORE this one
    prior = max(0.0, total_deposits(db, client_id) - amount)
    given = deposit_bonus_given(db, client_id)
    cap_left = max(0.0, float(cfg["dep_total_cap"]) - given)
    if cap_left <= 0:
        return {"bonus": 0.0, "skipped": "total_cap_reached"}

    offers = active_offers(db, country=country)
    chosen = None
    for o in offers:
        if amount >= o["min_deposit"] and not offer_claimed(db, o["id"], client_id):
            chosen = o
            break

    grants = []  # (kind, bonus, offer_id)
    if chosen:
        raw = amount * chosen["percent"] / 100.0
        bonus = min(raw, chosen["cap"]) if chosen["cap"] else raw
        bonus = round(min(bonus, cap_left), 2)
        grants.append(("special", bonus, chosen["id"]))
    else:
        tb = tier_breakdown(cfg, prior, amount)
        b1 = round(min(tb["tier1_bonus"], cap_left), 2)
        if b1 > 0:
            grants.append(("deposit_50", b1, None))
        cap_left2 = cap_left - b1
        b2 = round(min(tb["tier2_bonus"], max(0.0, cap_left2)), 2)
        if b2 > 0:
            grants.append(("deposit_20", b2, None))

    total_bonus = round(sum(g[1] for g in grants), 2)
    if total_bonus <= 0:
        return {"bonus": 0.0, "skipped": "no_bonus"}

    for kind, bonus, offer_id in grants:
        db.execute(text("""
            INSERT INTO bonus_grants (client_id, login, kind, offer_id, deposit_request_id,
                                      deposit_amount, amount, status)
            VALUES (:c,:l,:k,:o,:d,:da,:a,'credited')
        """), {"c": client_id, "l": login, "k": kind, "o": offer_id,
               "d": deposit_request_id, "da": amount, "a": bonus})
    if chosen:
        db.execute(text("""
            INSERT INTO bonus_offer_claims (offer_id, client_id, deposit_request_id, amount)
            VALUES (:o,:c,:d,:a) ON CONFLICT (offer_id, client_id) DO NOTHING
        """), {"o": chosen["id"], "c": client_id, "d": deposit_request_id, "a": total_bonus})
    db.execute(text("UPDATE clients SET credit = COALESCE(credit,0) + :b WHERE id=:id"),
               {"b": total_bonus, "id": client_id})
    db.commit()
    return {"bonus": total_bonus, "special": bool(chosen),
            "offer": chosen["name"] if chosen else None}


# ───────────────────────── WELCOME BONUS STATE MACHINE ─────────────────────────
def welcome_already(db: Session, client_id: int) -> bool:
    try:
        n = db.execute(text("""
            SELECT COUNT(*) FROM bonus_grants WHERE client_id=:id AND kind='welcome' AND status<>'cancelled'
        """), {"id": client_id}).scalar()
        if n:
            return True
        w = db.execute(text("SELECT status FROM bonus_welcome WHERE client_id=:id"),
                       {"id": client_id}).fetchone()
        return bool(w and w[0] == "claimed")
    except Exception:
        db.rollback()
        return False


def family_welcome_claimed(db: Session, client_id: int) -> bool:
    """One welcome bonus per household: True if a family member at the SAME home address has
    already claimed the welcome bonus. Address comes from the client's registration."""
    try:
        login = db.execute(text("SELECT login FROM clients WHERE id=:id"), {"id": client_id}).scalar()
        if login is None:
            return False
        addr = db.execute(text("""
            SELECT lower(regexp_replace(COALESCE(address,''),'\\s+',' ','g'))
            FROM registrations WHERE mt_login=:lg ORDER BY id DESC LIMIT 1
        """), {"lg": login}).scalar()
        if not addr or len(addr) < 6:
            return False
        fam = db.execute(text("""
            SELECT DISTINCT c.id FROM registrations r JOIN clients c ON c.login = r.mt_login
            WHERE c.id <> :id AND lower(regexp_replace(COALESCE(r.address,''),'\\s+',' ','g')) = :a
        """), {"id": client_id, "a": addr}).fetchall()
        fam_ids = [x[0] for x in fam]
        if not fam_ids:
            return False
        n = db.execute(text("""
            SELECT COUNT(*) FROM bonus_grants WHERE client_id = ANY(:ids) AND kind='welcome' AND status<>'cancelled'
        """), {"ids": fam_ids}).scalar() or 0
        return n > 0
    except Exception:
        db.rollback()
        return False


def _norm_txt(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _family_key(db: Session, logins: list) -> str:
    """A household key for a set of logins: the registration's family_group if set, else the home
    address. Used to tell whether two accounts belong to the same family."""
    if not logins:
        return ""
    try:
        row = db.execute(text("""
            SELECT family_group, address FROM registrations
            WHERE mt_login = ANY(:lg) AND (COALESCE(family_group,'')<>'' OR COALESCE(address,'')<>'')
            ORDER BY id DESC LIMIT 1
        """), {"lg": logins}).fetchone()
    except Exception:
        db.rollback(); return ""
    if not row:
        return ""
    fg = (row[0] or "").strip()
    if fg:
        return "fg:" + fg.lower()
    addr = _norm_txt(row[1])
    return ("ad:" + addr) if len(addr) >= 6 else ""


def _ensure_review_table(db: Session):
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS bonus_welcome_reviews (
                id SERIAL PRIMARY KEY, client_id INT UNIQUE, login BIGINT,
                matched VARCHAR(200), status VARCHAR(16) DEFAULT 'pending',
                reviewed_by VARCHAR(160), created_at TIMESTAMP DEFAULT NOW(), reviewed_at TIMESTAMP
            )
        """)); db.commit()
    except Exception:
        db.rollback()


def _family_connected_logins(db: Session, logins: list) -> set:
    """Logins this client is connected to by a FAMILY / household link, per the LIVE connection engine
    (the network connection page) — same phone, same name, shared email. The desk asked the bonus
    family check to rely on the network page. Falls back to nothing if the engine errors."""
    out = set()
    try:
        import connection_engine as CE
        primary = next((l for l in sorted(logins) if l), None) if logins else None
        if primary:
            sc = CE.score_connections(db, login=primary, limit=100)
            for c in sc.get("connections", []):
                reasons = {r.get("type") for r in c.get("reasons", [])}
                if reasons & {"family", "phone", "email", "similar_email"}:
                    out.add(c.get("id"))
    except Exception:
        db.rollback()
    return out


def _has_deposited(db: Session, client_id: int) -> bool:
    """Has this client EVER made a real deposit? Deposit truth = the transactions ledger
    (built from MT5 deals + the MT4 journal)."""
    try:
        logins = client_logins(db, client_id)
        if not logins:
            return False
        n = db.execute(text("""
            SELECT COUNT(*) FROM transactions
            WHERE login = ANY(:l) AND tx_type='deposit' AND COALESCE(amount,0) > 0
        """), {"l": logins}).scalar() or 0
        return n > 0
    except Exception:
        db.rollback()
        return False


def _client_family_signals(db: Session, client_id: int, logins: list) -> dict:
    """The 5 welcome-bonus family parameters for a client: SURNAME + GRANDFATHER (from the KYC OCR on
    their registration), CITY + IB (clients row), and the set of login IPs (account_identifiers)."""
    sig = {"surname": "", "gf": "", "city": "", "ib": 0, "ips": set()}
    try:
        c = db.execute(text("SELECT lower(COALESCE(city,'')), COALESCE(agent,0) FROM clients WHERE id=:id"),
                       {"id": client_id}).fetchone()
        if c:
            sig["city"] = c[0] or ""
            sig["ib"] = int(c[1] or 0)
        if logins:
            reg = db.execute(text("""
                SELECT ocr_fields FROM registrations
                WHERE mt_login = ANY(:l) AND ocr_fields IS NOT NULL ORDER BY id DESC LIMIT 1
            """), {"l": logins}).fetchone()
            of = reg[0] if reg and isinstance(reg[0], dict) else {}
            nm = (of.get("full_name_latin") or of.get("full_name") or "")
            sig["surname"] = _norm(of.get("surname") or (nm.split(" ")[-1] if nm else ""))
            sig["gf"] = _norm(of.get("grandfather_name"))
            rows = db.execute(text("""
                SELECT DISTINCT identifier_value FROM account_identifiers
                WHERE login = ANY(:l) AND identifier_type='ip' AND identifier_value NOT IN ('0','')
            """), {"l": logins}).fetchall()
            sig["ips"] = {r[0] for r in rows}
    except Exception:
        db.rollback()
    return sig


def welcome_eligibility(db: Session, client_id: int, logins: list) -> dict:
    """Multi-level welcome-bonus eligibility (desk policy Jun 2025):
      L1  same DEVICE (cid/mqid) as ANY other account -> BLOCK (device already used it).
      L2  device is new -> score {IB, City, Family, IP} against accounts that ALREADY received the
          welcome bonus (Family link comes from the connection engine / network page). The
          best-matching single other account decides:
            >=3 factors -> BLOCK (a family member / linked account already got it)
            ==2 factors -> REVIEW (queued for the team to approve/reject)
            <=1 factor  -> ELIGIBLE (claim).
    A team APPROVE overrides to eligible; a REJECT overrides to blocked."""
    own = set(l for l in (logins or []) if l is not None)

    # team-review override (admin already decided this case)
    _ensure_review_table(db)
    rv = db.execute(text("SELECT status, matched FROM bonus_welcome_reviews WHERE client_id=:id"),
                    {"id": client_id}).fetchone()
    if rv and rv[0] == "approved":
        return {"state": "eligible", "reason": "Approved by our team — claim your welcome bonus!"}
    if rv and rv[0] == "rejected":
        return {"state": "blocked", "block_reason": "family",
                "reason": "Your welcome bonus was reviewed and isn't eligible for this account.",
                "note": rv[1] or ""}

    rows = db.execute(text("""
        SELECT DISTINCT identifier_type, identifier_value FROM account_identifiers
        WHERE login = ANY(:lg) AND identifier_type IN ('cid','mqid','ip') AND identifier_value NOT IN ('0','')
    """), {"lg": list(own)}).fetchall() if own else []
    if not rows:
        return {"state": "awaiting_login",
                "reason": "Log in to your trading account to activate your bonus."}
    my_dev = [(t, v) for t, v in rows if t in ("cid", "mqid")]
    my_ips = [v for t, v in rows if t == "ip"]

    # L1 — same physical device/terminal as another account
    for t, v in my_dev:
        ext = db.execute(text("""
            SELECT DISTINCT login FROM account_identifiers
            WHERE identifier_type=:t AND identifier_value=:v AND identifier_value NOT IN ('0','')
        """), {"t": t, "v": v}).fetchall()
        if {r[0] for r in ext} - own:
            return {"state": "blocked", "block_reason": "device",
                    "reason": "You're not eligible for the welcome bonus — this device has already been used to claim it.",
                    "note": "The welcome bonus can be claimed once per device."}

    # ── L2: FAMILY / CONNECTION SCORING vs accounts that ALREADY CLAIMED the welcome bonus ──
    # FIVE parameters: SURNAME, GRANDFATHER, CITY, IP, IB. We ONLY gate against accounts that actually
    # CLAIMED the welcome bonus — so if NO family member claimed, auto-proceed (eligible). DEPOSIT rule:
    #   • a matched family claimer that HAS deposited  -> family can claim (real referral) -> ELIGIBLE
    #   • a matched family claimer that has NOT deposited (grab-and-go):
    #         >=3 params match -> BLOCK (auto-reject, NO admin review)
    #         ==2 params match -> REVIEW (team approves/rejects)
    claimers = db.execute(text("""
        SELECT DISTINCT c.id, c.login FROM bonus_grants g JOIN clients c ON c.id=g.client_id
        WHERE g.kind='welcome' AND g.status<>'cancelled' AND c.login IS NOT NULL
    """)).fetchall()
    if not claimers:
        return {"state": "eligible", "reason": "You're eligible — claim your bonus!"}

    me_sig = _client_family_signals(db, client_id, list(own))
    worst = None   # the strictest matched-list among NON-DEPOSITING family claimers
    for (cl_id, cl_login) in claimers:
        if cl_login in own:
            continue
        cl_sig = _client_family_signals(db, cl_id, [cl_login])
        matched = []
        if me_sig["surname"] and me_sig["surname"] == cl_sig["surname"]: matched.append("Surname")
        if me_sig["gf"] and me_sig["gf"] == cl_sig["gf"]: matched.append("Grandfather")
        if me_sig["city"] and me_sig["city"] == cl_sig["city"]: matched.append("City")
        if me_sig["ib"] and me_sig["ib"] == cl_sig["ib"]: matched.append("IB")
        if me_sig["ips"] & cl_sig["ips"]: matched.append("IP")
        if len(matched) < 2:
            continue                       # not a family/connection match
        if _has_deposited(db, cl_id):
            continue                       # a depositing family member -> referral allowed, this one is fine
        if worst is None or len(matched) > len(worst):
            worst = matched

    if not worst:
        # no family-connected claimer, OR every connected claimer has deposited -> allow
        return {"state": "eligible", "reason": "You're eligible — claim your bonus!"}
    if len(worst) >= 3:
        return {"state": "blocked", "block_reason": "family", "matched": worst,
                "reason": "You're not eligible for the welcome bonus — a family member already claimed it "
                          "and hasn't deposited yet.",
                "note": "Matched: " + ", ".join(worst) + ". One welcome bonus per family until the first member deposits."}
    # exactly 2 params -> team review
    try:
        db.execute(text("""
            INSERT INTO bonus_welcome_reviews (client_id, login, matched, status)
            VALUES (:c,:l,:m,'pending') ON CONFLICT (client_id) DO NOTHING
        """), {"c": client_id, "l": (sorted(own)[0] if own else None), "m": ", ".join(worst)})
        db.commit()
    except Exception:
        db.rollback()
    return {"state": "review", "matched": worst,
            "reason": "Your welcome bonus is under review by our team — we'll confirm your eligibility shortly.",
            "note": "Matched: " + ", ".join(worst) + "."}


def list_welcome_reviews(db: Session, status: str = "pending") -> list:
    """Admin queue: welcome-bonus cases sitting in team review (2 matched signals)."""
    _ensure_review_table(db)
    rows = db.execute(text("""
        SELECT r.id, r.client_id, r.login, r.matched, r.status, r.created_at, r.reviewed_by, r.reviewed_at,
               c.name, c.email, c.phone, c.country, c.city
        FROM bonus_welcome_reviews r LEFT JOIN clients c ON c.id = r.client_id
        WHERE (:st = '' OR r.status = :st)
        ORDER BY (r.status='pending') DESC, r.created_at DESC LIMIT 300
    """), {"st": status or ""}).fetchall()
    return [{"id": x[0], "client_id": x[1], "login": x[2], "matched": x[3], "status": x[4],
             "created_at": str(x[5]) if x[5] else None, "reviewed_by": x[6],
             "reviewed_at": str(x[7]) if x[7] else None, "name": x[8], "email": x[9],
             "phone": x[10], "country": x[11], "city": x[12]} for x in rows]


def decide_welcome_review(db: Session, review_id: int, decision: str, by: str = "") -> dict:
    """Approve (-> grant the welcome bonus now) or reject (-> blocked) a queued review case."""
    _ensure_review_table(db)
    r = db.execute(text("SELECT client_id, status FROM bonus_welcome_reviews WHERE id=:i"),
                   {"i": review_id}).fetchone()
    if not r:
        return {"ok": False, "error": "not found"}
    status = "approved" if decision == "approve" else "rejected"
    db.execute(text("""UPDATE bonus_welcome_reviews SET status=:s, reviewed_by=:b, reviewed_at=NOW() WHERE id=:i"""),
               {"s": status, "b": (by or "")[:150], "i": review_id})
    db.commit()
    granted = None
    if decision == "approve" and not welcome_already(db, r[0]):
        res = claim_welcome(db, r[0])          # now sees review=approved -> eligible -> records the grant
        granted = res.get("amount") if res.get("ok") else None
        if res.get("ok"):
            push_welcome_credit(r[0])          # push to the real MT account + email (admin path, inline)
    return {"ok": True, "status": status, "granted": granted}


def welcome_state(db: Session, client_id: int) -> dict:
    """
    States: disabled | blocked | kyc_upload | kyc_review | awaiting_login |
            eligible | not_eligible | claimed
    """
    cfg = get_config(db)
    amount = float(cfg["welcome_amount"])
    crow = db.execute(text("SELECT country, kyc_status FROM clients WHERE id=:id"),
                      {"id": client_id}).fetchone()
    country = (crow[0] if crow else "") or ""
    kyc = (crow[1] if crow else "") or "not_submitted"

    base = {"amount": amount, "country": country, "kyc": kyc}
    if not cfg["bonuses_enabled"]:
        return {**base, "state": "disabled", "reason": "Bonuses are currently unavailable."}
    if welcome_already(db, client_id):
        return {**base, "state": "claimed", "reason": "Welcome bonus claimed."}
    if country_blocked(cfg, country):
        return {**base, "state": "blocked",
                "reason": f"Welcome bonus is not available in {country}."}
    if kyc == "verified":
        pass
    elif kyc in ("pending_review", "review"):
        return {**base, "state": "kyc_review", "reason": "Your KYC is under review."}
    else:
        return {**base, "state": "kyc_upload", "reason": "Upload your KYC to unlock your bonus."}

    logins = client_logins(db, client_id)
    return {**base, **welcome_eligibility(db, client_id, logins)}


def claim_welcome(db: Session, client_id: int) -> dict:
    st = welcome_state(db, client_id)
    if st["state"] != "eligible":
        return {"ok": False, "state": st["state"], "message": st.get("reason", "Not eligible.")}
    amount = float(st["amount"])
    logins = client_logins(db, client_id)
    login = logins[0] if logins else None
    db.execute(text("""
        INSERT INTO bonus_grants (client_id, login, kind, deposit_amount, amount, status)
        VALUES (:c,:l,'welcome',0,:a,'credited')
    """), {"c": client_id, "l": login, "a": amount})
    db.execute(text("""
        INSERT INTO bonus_welcome (client_id, login, status, amount, claimed_at, updated_at)
        VALUES (:c,:l,'claimed',:a,NOW(),NOW())
        ON CONFLICT (client_id) DO UPDATE SET status='claimed', amount=:a, claimed_at=NOW(), updated_at=NOW()
    """), {"c": client_id, "l": login, "a": amount})
    db.execute(text("UPDATE clients SET credit = COALESCE(credit,0) + :a WHERE id=:id"),
               {"a": amount, "id": client_id})
    db.commit()
    # The real MT credit + email run in the BACKGROUND (see push_welcome_credit) so the Claim button
    # returns INSTANTLY and the KPI rolls straight to the next bonus (50% deposit) — no waiting on the bridge.
    return {"ok": True, "state": "claimed", "amount": amount, "login": login,
            "message": f"${amount:,.0f} welcome bonus credited to your trading account!"}


def push_welcome_credit(client_id: int):
    """Background step after claim_welcome: push the $50 to the REAL MT account as CREDIT (type 3) so it
    shows on the terminal + survives the bridge sync, and email the client. Opens its own DB session;
    never raises. Idempotent enough for one retry (the DB grant is the source of truth)."""
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT g.login, g.amount, c.name, c.email FROM bonus_grants g JOIN clients c ON c.id=g.client_id
            WHERE g.client_id=:id AND g.kind='welcome' AND g.status<>'cancelled' ORDER BY g.id DESC LIMIT 1
        """), {"id": client_id}).fetchone()
        if not row:
            return
        login, amount = row[0], float(row[1] or 0)
        if login and int(login) > 0:
            try:
                import mt_provision
                res = mt_provision.credit_account(int(login), amount, "TNFX Welcome Bonus", credit_type=3)
                if not res.get("ok"):
                    print(f"[bonus] MT credit failed for login {login}: {res.get('error')}", flush=True)
            except Exception as e:
                print(f"[bonus] MT credit exception for login {login}: {e}", flush=True)
        try:
            import email_send
            if row[3] and email_send.configured():
                nm = (row[2] or "").split(" ")[0]
                body = (f"Dear {nm},\n\nWe are pleased to inform you that your ${amount:,.0f} welcome bonus has been "
                        f"credited to your TNFX trading account{(' #' + str(login)) if login else ''}. It appears as "
                        "Credit on your terminal and increases your available trading margin.\n\nKind regards,\nTNFX")
                email_send.send(row[3], f"Your ${amount:,.0f} TNFX welcome bonus has been credited", body)
        except Exception as e:
            print(f"[bonus] welcome email failed for client {client_id}: {e}", flush=True)
    finally:
        db.close()


# ───────────────────────── WITHDRAW: MARGIN GUARD + CLAWBACK ─────────────────────────
def account_money_state(db: Session, client_id: int):
    """(balance, credit, equity, margin, margin_level) — best effort.
    No live open-positions feed is wired, so equity≈balance and margin=0 (no open trades
    known). The guard math below is correct the moment a positions feed populates margin."""
    logins = client_logins(db, client_id)
    bal = db.execute(text("""
        SELECT COALESCE(SUM(balance),0) FROM trading_accounts WHERE login = ANY(:logins)
    """), {"logins": logins or [0]}).scalar()
    balance = float(bal or 0)
    if balance <= 0:
        # fall back to the clients row (portal registrants have no trading_accounts row)
        cb = db.execute(text("SELECT COALESCE(balance,0) FROM clients WHERE id=:id"),
                        {"id": client_id}).scalar()
        balance = float(cb or 0)
    credit = float(db.execute(text("SELECT COALESCE(credit,0) FROM clients WHERE id=:id"),
                              {"id": client_id}).scalar() or 0)
    floating = 0.0   # no live open-position P/L feed yet
    margin = 0.0     # no live used-margin feed yet
    equity = balance + credit + floating
    margin_level = (equity / margin * 100.0) if margin > 0 else None
    return balance, credit, equity, margin, margin_level


def withdraw_check(db: Session, client_id: int, amount: float) -> dict:
    """Validate a withdrawal: min-amount rule, margin-level guard, and the bonus that
    would be clawed back. Returns {ok, reason, max_withdraw, min_withdraw, clawback}."""
    cfg = get_config(db)
    amount = float(amount or 0)
    balance, credit, equity, margin, margin_level = account_money_state(db, client_id)
    deposited = total_deposits(db, client_id) > 0
    min_w = float(cfg["welcome_withdraw_min_dep"] if deposited else cfg["welcome_withdraw_min_nodep"])

    # proportional bonus clawback: withdrawing X% of balance claws back X% of bonus credit
    frac = (amount / balance) if balance > 0 else 0.0
    frac = min(1.0, max(0.0, frac))
    clawback = round(credit * frac, 2)

    res = {"ok": True, "min_withdraw": min_w, "balance": round(balance, 2),
           "credit": round(credit, 2), "equity": round(equity, 2),
           "margin_level": round(margin_level, 1) if margin_level is not None else None,
           "clawback": clawback, "deposited": deposited, "reason": None, "max_withdraw": None}

    if amount < min_w:
        res["ok"] = False
        res["reason"] = (f"Minimum withdrawal is ${min_w:,.0f} "
                         f"({'with' if deposited else 'without'} a prior deposit).")
        return res

    if amount > balance:
        res["ok"] = False
        res["max_withdraw"] = round(balance, 2)
        res["reason"] = f"You can withdraw at most ${balance:,.2f}."
        return res

    # margin-level guard: equity AFTER withdrawal must keep margin level >= floor
    floor = float(cfg["margin_floor_pct"]) / 100.0
    if margin > 0:
        max_w = equity - floor * margin
        if amount > max_w:
            res["ok"] = False
            res["max_withdraw"] = round(max(0.0, max_w), 2)
            res["reason"] = (f"This withdrawal would drop your margin level below "
                             f"{cfg['margin_floor_pct']:.0f}%. You can withdraw up to "
                             f"${max(0.0, max_w):,.2f}, or close some open trades first.")
            return res
    return res


def apply_withdraw_clawback(db: Session, client_id: int, amount: float) -> dict:
    """Remove bonus proportionally to the withdrawn fraction of balance, after a withdrawal."""
    balance, credit, *_ = account_money_state(db, client_id)
    if credit <= 0 or balance <= 0:
        return {"clawback": 0.0}
    frac = min(1.0, max(0.0, float(amount) / balance))
    clawback = round(credit * frac, 2)
    if clawback <= 0:
        return {"clawback": 0.0}
    db.execute(text("UPDATE clients SET credit = GREATEST(0, COALESCE(credit,0) - :c) WHERE id=:id"),
               {"c": clawback, "id": client_id})
    # write the clawback against the most-recent grants (FIFO newest-first), for the ledger
    remaining = clawback
    rows = db.execute(text("""
        SELECT id, amount, COALESCE(clawed_back,0) FROM bonus_grants
        WHERE client_id=:id AND status='credited' AND (amount - COALESCE(clawed_back,0)) > 0
        ORDER BY id DESC
    """), {"id": client_id}).fetchall()
    for gid, amt, cb in rows:
        if remaining <= 0:
            break
        avail = float(amt) - float(cb)
        take = min(avail, remaining)
        new_cb = float(cb) + take
        status = "clawed_back" if new_cb >= float(amt) - 0.01 else "credited"
        db.execute(text("UPDATE bonus_grants SET clawed_back=:cb, status=:s WHERE id=:gid"),
                   {"cb": round(new_cb, 2), "s": status, "gid": gid})
        remaining -= take
    db.commit()
    return {"clawback": clawback}


# ───────────────────────── PORTAL STATUS PAYLOAD ─────────────────────────
def bonus_status(db: Session, client_id: int) -> dict:
    """Everything the portal bonus KPI row + bonus page need, in one call."""
    cfg = get_config(db)
    crow = db.execute(text("SELECT country FROM clients WHERE id=:id"), {"id": client_id}).fetchone()
    country = (crow[0] if crow else "") or ""
    blocked = country_blocked(cfg, country)

    welcome = welcome_state(db, client_id)

    # deposit-bonus progress
    prior = total_deposits(db, client_id)
    given = deposit_bonus_given(db, client_id)
    t1cap = float(cfg["dep_tier1_cap"])
    t1_dep_left = max(0.0, t1cap - prior)
    t1_bonus_left = round(t1_dep_left * float(cfg["dep_tier1_pct"]) / 100.0, 2)
    total_cap = float(cfg["dep_total_cap"])
    cap_left = round(max(0.0, total_cap - given), 2)

    deposit_lines = [
        {"key": "welcome", "label": f"Welcome bonus ${cfg['welcome_amount']:,.0f}",
         "done": welcome["state"] in ("claimed", "not_eligible", "blocked", "family_claimed"),
         "remaining": None},
        {"key": "tier1", "label": f"{cfg['dep_tier1_pct']:.0f}% deposit bonus",
         "remaining": t1_bonus_left, "done": t1_bonus_left <= 0,
         "sub": f"remaining ${t1_bonus_left:,.0f}"},
        {"key": "tier2", "label": f"{cfg['dep_tier2_pct']:.0f}% deposit bonus",
         "remaining": cap_left, "done": cap_left <= 0,
         "sub": f"remaining ${cap_left:,.0f}"},
    ]

    offers = active_offers(db, country=country if not blocked else None)
    offer_out = []
    for o in offers:
        offer_out.append({**o, "claimed": offer_claimed(db, o["id"], client_id)})

    # birthday bonus (own engine; local import to avoid a circular import)
    try:
        import birthday_engine as BD
        birthday = BD.birthday_status(db, client_id)
    except Exception:
        db.rollback()
        birthday = {"enabled": False, "state": "disabled", "in_window": False}

    return {
        "enabled": cfg["bonuses_enabled"],
        "blocked": blocked,
        "country": country,
        "birthday": birthday,
        "credit": float(db.execute(text("SELECT COALESCE(credit,0) FROM clients WHERE id=:id"),
                                   {"id": client_id}).scalar() or 0),
        "welcome": welcome,
        "deposit": {
            "tier1_pct": cfg["dep_tier1_pct"], "tier2_pct": cfg["dep_tier2_pct"],
            "tier1_cap": t1cap,
            "tier1_deposit_remaining": round(t1_dep_left, 2),
            "tier1_bonus_remaining": t1_bonus_left,
            "total_cap": total_cap, "given": round(given, 2), "cap_remaining": cap_left,
            "lines": deposit_lines,
        },
        "offers": offer_out,
    }
