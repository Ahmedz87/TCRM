"""
connection_engine.py — "who is this person connected to, and how sure are we?"

Powers the Network/Risk connection intelligence:
  • score_connections(db, login=…|lead_id=…)  -> ranked list of connected accounts,
    each with a CONFIDENCE % and an x/10 score and the signals that fired.
  • connection_groups(db)                      -> connected-component groups across ALL
    signals, each with a deterministic VERDICT (IB-commission farming / bonus abuse /
    toxic trading / swap abuse / hedging ring) + money/IB/bonus stats.
  • group_stats(db, logins)                    -> the money/trading/IB summary for a set.

Confidence model — noisy-OR over the signals that link two accounts:
    conf = 1 - Π(1 - weight_i)
A device match (CID) alone = 1.0 = 100% (10/10); weaker signals (IP, IB, city, payment)
stack toward — but don't trivially reach — 100%.

Signal strength (probability a true same-person/related link exists given the shared token):
    cid 1.00 · mqid 0.97 · email 0.92 · phone/family 0.90 · ip 0.55 · payment 0.55 · ib 0.45 · city 0.30
Strong signals (device/ip/email/phone) FIND the connected accounts; ib/city/payment BOOST
the confidence of accounts already found (they're too broad to enumerate on their own).
"""
import re
from collections import defaultdict
from sqlalchemy import text

SIGNAL_WEIGHT = {
    "cid": 1.00, "mqid": 0.97, "similar_email": 0.80,
    # EXACT phone / email are NOT connection factors: two different users can't share them — same phone
    # or same email = the SAME user (one customer), so they're handled by customer_no, not shown as a
    # "connection". Only SIMILAR email (different-but-related inbox) links two different people.
    # SAME PAYMENT SENDER = strong financial/family link. For Qi this is the same SENDER NAME on the
    # receipt (NOT the card number — cards rotate / are shared by exchangers); zain = sender wallet.
    "pay_sender": 0.85,
    "ib": 0.55, "city": 0.45,
    "payment": 0.20,   # same METHOD (e.g. both use Zain Cash) is near-noise — corroboration only
    # IP is the WEAKEST thing we hold and is NEVER a link on its own (see IP_NEEDS_CORROBORATION):
    # Iraq has no static IPs and every CRM + MT4/MT5 login stamps another one, so two strangers share
    # IPs constantly. It only counts next to another factor (city/IB/email/device)…
    "ip": 0.30,
    # …or when the TIMING lines up: the same IP that registered two accounts within hours, or funded
    # two first-deposits in the same window, is the same person/desk sitting at one connection.
    "ip_coreg": 0.85,
    "ip_codep": 0.80,
    # (kept for legacy callers; not fired as connection signals anymore)
    "email": 0.92, "phone": 0.90, "family": 0.90,
}
SIGNAL_LABEL = {
    "cid": "Same device (CID)", "mqid": "Same device (MetaQuotes ID)", "email": "Same email",
    "similar_email": "Similar email", "phone": "Same phone", "family": "Family / same phone",
    "pay_sender": "Same payment sender (same Qi sender name / wallet)",
    "ip": "Same IP address", "payment": "Same payment method", "ib": "Same IB / agent", "city": "Same city",
    "ip_coreg": "Same IP + registered at the same time",
    "ip_codep": "Same IP + first deposit in the same period",
    "reg_period": "Registered in the same period",
    "dep_period": "First deposit in the same period",
    "family_l1": "Family (direct — brother / parent / child)",
    "family_l2": "Family (extended)",
    "ip1": "Same IP address", "ip2": "Same IP (2 shared)", "ip3": "Same IP (3+ shared)",
    "email3": "Same / near-identical email", "email2": "Similar email", "email1": "Loosely similar email",
}
# Signal display priority — used to pick the headline reason (strong → weak).
SIGNAL_ORDER = ["cid", "mqid", "family_l1", "pay_sender", "ip3", "email3", "ip2", "email2",
                "similar_email", "family_l2", "ib", "city", "reg_period", "dep_period", "email1",
                "payment", "ip1", "ip_coreg", "ip_codep", "ip", "family", "phone", "email", "name"]

# Connection-tab ORDER: device(CID) → family → same-card → 3+IP/same-email → 2IP → … → single IP.
LINK_PRIORITY = {"cid": 1, "mqid": 1, "family_l1": 2, "pay_sender": 3, "ip3": 4, "email3": 4,
                 "ip2": 5, "email2": 6, "similar_email": 6, "family_l2": 7, "ib": 8, "city": 9,
                 "reg_period": 10, "dep_period": 10, "email1": 11, "payment": 12, "ip1": 13,
                 "ip_coreg": 13, "ip_codep": 13, "ip": 13, "family": 14, "phone": 14, "email": 14, "name": 15}

# ── IP RULE (Jul 2026 desk rule) ────────────────────────────────────────────────────────────────
# A shared IP ALONE never links two people. It links them only when a second factor agrees, or when
# the timing matches: registered from the same IP within IP_COREG_HOURS, or first-deposited from the
# same IP within IP_CODEP_HOURS (that pattern is a real co-located signup/funding, esp. around FTD).
IP_COREG_HOURS = 72        # ±72h — co-registration from one IP (desk-set Jul 2026)
IP_CODEP_HOURS = 24 * 7    # ±7 days — co-funding from one IP (deposits cluster over a longer window)
IP_ONLY = {"ip"}          # a candidate whose signals are only this is NOT a connection


def _norm_name(s):
    """Normalise a person name for same-identity comparison: lowercase, keep latin+arabic letters,
    sort the tokens — so 'Ahmed Zaman', 'Zaman Ahmed', 'ahmed  zaman' all collapse to the same key."""
    toks = re.sub("[^a-z؀-ۿ ]", " ", (s or "").lower()).split()
    return " ".join(sorted(toks))

# SQL: normalise an email's LOCAL part → lowercase, drop +tag, remove dots. So ahmed.zaman,
# ahme.dzaman, a.h.m.e.dzaman, ahmedzaman+test all collapse to "ahmedzaman" (Gmail treats dots as
# identical anyway). Used for similar-email linking. Pass the column name in.
def _norm_email_sql(col):
    return r"replace(regexp_replace(lower(split_part(coalesce(%s,''),'@',1)), '\+.*$', '', 'g'), '.', '')" % col


def _norm_email(e):
    e = (e or "").strip().lower()
    loc = e.split("@", 1)[0] if "@" in e else e
    return loc.split("+", 1)[0].replace(".", "")

# The email "core" = the normalised local part with the DIGITS stripped (ali1990 -> ali).
def _norm_email_core_sql(col):
    return "regexp_replace(%s, '[0-9]', '', 'g')" % _norm_email_sql(col)

# COMMON-NAME GUARD (Jul 2026 desk rule). In Iraq/the Arab world millions share a first name, so
# ali1990@x / ali2005@y / mohammedi1994@z are NOT relatives — ~89% of similar-email pairs in this DB
# come from such cores. A core shared by >= this many DIFFERENT people is treated as NOT identifying:
# a similar-email match on it only counts when CORROBORATED by same city / IP / IB. Distinctive cores
# (a real surname shared by 2-4 people) still link on their own. Data-driven, so it also catches
# non-name junk like 'souriahost', 'iraqx', 'tnfx'. Table built by build_network_scores.py.
COMMON_CORE_MIN_PEOPLE = 5
# signals that can corroborate a common-name email match (anything real that ties the two people)
EMAIL_CORROBORATORS = {"cid", "mqid", "ip", "ib", "city", "pay_sender"}
# …but a MEGA-city is not corroboration: ~1/3 of the book is Baghdad, so "both named Ali AND both in
# Baghdad" is still two strangers. Baghdad is excluded as a corroborator; any smaller city counts.
# (Cities are compared on the CANONICAL name — clients.city_canon, build_city_canon.py — because the
# field is free text: Erbil/Arbil/Irbil, Baghdad/Bagdad/بغداد, Basra/Basrah/Basraa all collapse to one.)
WEAK_CITIES = {"baghdad"}


def _core_variants(core):
    """The core plus its 1-2 trailing-letter-stripped forms, so a decorated common token is still
    caught: iraq1224x -> core 'iraqx' -> 'iraq' (common). Keeps real surnames safe (alialwan -> 'ali'
    only after stripping 5 chars, which we never do)."""
    out = [core]
    for k in (1, 2):
        if len(core) - k >= 3:
            out.append(core[:-k])
    return out


def core_is_common(core, common_set):
    """Pure form of the guard for bulk jobs that already hold the common-core set."""
    if not core or len(core) < 3:
        return True
    return any(v in common_set for v in _core_variants(core))


def is_common_core(db, core):
    """True if this email core is a common name / generic token (not identifying on its own)."""
    if not core or len(core) < 3:
        return True          # too short to identify anyone
    try:
        return db.execute(text("SELECT 1 FROM common_email_cores WHERE core = ANY(:c) LIMIT 1"),
                          {"c": _core_variants(core)}).scalar() is not None
    except Exception:
        return False         # table not built yet -> behave as before

# IP / device tokens shared by more than this many logins are treated as noise (NAT, shared PC bank).
MAX_TOKEN_FANOUT = 25
# A payment sender (Qi card / wallet) shared by more than this many clients is a money exchanger /
# agent funding many unrelated people — NOT a family link, so it's excluded from the pay_sender signal.
PAY_SENDER_MAX_FANOUT = 6

_TABLE_CACHE = {}
def _table_exists(db, name):
    if name not in _TABLE_CACHE:
        _TABLE_CACHE[name] = db.execute(text("SELECT to_regclass(:n)"), {"n": "public." + name}).scalar() is not None
    return _TABLE_CACHE[name]


def _phone9(p):
    d = re.sub(r"[^0-9]", "", p or "")
    return d[-9:] if len(d) >= 9 else d


def _ts(v):
    """Parse an ISO date/datetime string (reg_date / first_deposit_at are VARCHAR) -> datetime|None."""
    if not v:
        return None
    s = str(v).strip()[:19].replace("T", " ")
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return __import__("datetime").datetime.strptime(s[:len(f) + 2] if f.endswith("S") else s[:10], f)
        except Exception:
            continue
    return None


def _within(a, b, hours):
    """True if both timestamps parse and land within `hours` of each other."""
    ta, tb = _ts(a), _ts(b)
    if not ta or not tb:
        return False
    return abs((ta - tb).total_seconds()) <= hours * 3600


def _noisy_or(weights):
    prod = 1.0
    for w in weights:
        prod *= (1.0 - min(0.999, w))
    return 1.0 - prod


def _confidence(signals):
    """signals: set of signal keys. Device match forces ~100%."""
    if "cid" in signals:
        return 100, 10
    conf = _noisy_or([SIGNAL_WEIGHT.get(s, 0.2) for s in signals])
    pct = int(round(conf * 100))
    pct = max(1, min(99, pct))
    return pct, max(1, round(pct / 10))


# ── ONE canonical network-risk level + colour (the SINGLE source used everywhere) ──────────────
# The x/10 badge on every page (Clients, Leads, IB, Transactions, Neg-balance, the detail popup)
# reads the SAME stored score and maps it through THIS function. Any device (CID/MQID) share pushes
# the score to 10 → "critical" → red, so "any CID = red" holds automatically.
RISK_COLORS = {"critical": "#ff4d4d", "high": "#ff8c00", "medium": "#ffd166",
               "low": "#5a6472", "none": "#3a4150"}

def risk_level(score10):
    """score10 (0-10) -> (level, colour). Shared by the scorer, the API and (mirrored) the UI."""
    s = int(score10 or 0)
    if s >= 8:   lvl = "critical"     # DEVICE (CID/MQID) link -> always here -> red
    elif s >= 5: lvl = "high"         # same payment card / multi-signal
    elif s >= 3: lvl = "medium"       # similar email
    elif s >= 1: lvl = "low"          # shared IP only
    else:        lvl = "none"
    return lvl, RISK_COLORS[lvl]

def top_reason(sigs):
    """Headline signal (strongest link type) for a set of fired signals."""
    if not sigs:
        return ""
    best = min(sigs, key=lambda s: LINK_PRIORITY.get(s, 99))
    return SIGNAL_LABEL.get(best, best)

# SUBJECT-level risk weight per signal (distinct from the per-connection confidence used in the
# detail popup). RED is reserved for a DEVICE match, per the desk rule "any CID = red". A same-card
# link is high; a similar-email is medium; a shared IP alone is low. Multiple signals nudge upward.
SUBJECT_SIGNAL_SCORE = {"cid": 10, "mqid": 10, "pay_sender": 6,
                        "ip3": 6, "email3": 6, "ip2": 4, "email2": 4, "similar_email": 4,
                        "ip1": 2, "ip": 2, "email1": 2, "reg_period": 2, "dep_period": 2,
                        "ib": 2, "city": 2, "payment": 1}

def score_signals(sigs):
    """Canonical subject score from a set of fired signal keys -> (score10, level, colour, reason)."""
    sigs = set(sigs)
    # IP ALONE IS NOT A LINK (Iraq: no static IPs, every CRM/MT login stamps a new one). It scores
    # only alongside another factor, or via the timing signals ip_coreg / ip_codep.
    if not sigs or sigs <= IP_ONLY:
        return 0, "none", RISK_COLORS["none"], ""
    scoring = set(sigs)
    # ip_coreg/ip_codep ARE the IP evidence with timing attached — don't also count the bare 'ip' as a
    # separate corroborating signal, or a co-registration would inflate to red (red stays for a DEVICE).
    if scoring & {"ip_coreg", "ip_codep"}:
        scoring.discard("ip")
    base = max(SUBJECT_SIGNAL_SCORE.get(s, 1) for s in scoring)
    extra = len([s for s in scoring if SUBJECT_SIGNAL_SCORE.get(s, 0) >= 2]) - 1  # +1 per extra signal
    s10 = min(10, base + max(0, extra))
    lvl, col = risk_level(s10)
    return s10, lvl, col, top_reason(sigs)


def stored_subject_score(db, login=None, lead_id=None):
    """Read the PRECOMPUTED canonical score for one subject (the value every badge shows).
    Returns {score10, level, colour, reason}. Kept trivial so the detail popup header matches the
    list badge exactly — both come from clients.network_score / leads.network_score."""
    row = None
    if login is not None:
        row = db.execute(text("SELECT COALESCE(network_score,0), COALESCE(network_reason,'') "
                              "FROM clients WHERE login=:l"), {"l": login}).fetchone()
    elif lead_id is not None:
        row = db.execute(text("SELECT COALESCE(network_score,0), COALESCE(network_reason,'') "
                              "FROM leads WHERE id=:l"), {"l": lead_id}).fetchone()
    s10 = int(row[0]) if row else 0
    lvl, col = risk_level(s10)
    return {"score10": s10, "level": lvl, "colour": col, "reason": (row[1] if row else "") or ""}


def _subject(db, login=None, lead_id=None):
    """Resolve the subject's identifying tokens (device ids, ips, email, phone, city, IB)."""
    if login is not None:
        c = db.execute(text("""
            SELECT login, name, email, phone,
                   COALESCE(NULLIF(city_canon,''), city) AS city,   -- canonical (free-text unified)
                   country, agent, customer_no,
                   NULLIF(reg_date,''), NULLIF(first_deposit_at,'')  -- for the IP+timing signals
            FROM clients WHERE login=:l
        """), {"l": login}).fetchone()
        if not c:
            return None
        # reg/first-deposit for the IP+timing signals are taken at CUSTOMER level (earliest across all
        # of this person's logins) — the same grain the bulk score builder uses, so the popup's timing
        # links and the stored badge always agree.
        # reg / first-deposit / city / IB are ALL read at customer grain (the person, not the one
        # account) — build_network_scores scores the customer, so the popup must judge the same facts
        # or the badge and the connection list disagree (e.g. the IB sits on a sibling login).
        reg, fda, city, agent = c[8], c[9], (c[4] or "").strip(), c[6] or 0
        if c[7]:
            r2 = db.execute(text("""
                SELECT MIN(NULLIF(reg_date,'')), MIN(NULLIF(first_deposit_at,'')),
                       MIN(NULLIF(city_canon,'')), MIN(NULLIF(agent,0))
                FROM clients WHERE customer_no=:cn
            """), {"cn": c[7]}).fetchone()
            if r2:
                reg, fda = r2[0] or reg, r2[1] or fda
                city, agent = (r2[2] or city), (r2[3] or agent)
        # USER-WISE: collect the device/IP tokens across ALL of this person's logins, not just the one
        # we were asked about — a sibling account's device/IP is still this person's. This is the grain
        # build_network_scores uses, so the popup and the stored badge see the same evidence.
        own_logins = [login]
        if c[7]:
            own_logins = [r[0] for r in db.execute(text(
                "SELECT login FROM clients WHERE customer_no=:cn"), {"cn": c[7]}).fetchall()] or [login]
        ids = db.execute(text("""
            SELECT DISTINCT identifier_type, identifier_value FROM account_identifiers
            WHERE login = ANY(:l) AND identifier_value NOT IN ('0','')
        """), {"l": own_logins}).fetchall()
        cids = [v for t, v in ids if t == "cid"]
        mqids = [v for t, v in ids if t == "mqid"]
        ips = [v for t, v in ids if t == "ip"]
        return {"kind": "client", "id": login, "login": login, "name": c[1] or f"#{login}",
                "email": (c[2] or "").lower().strip(), "email_norm": _norm_email(c[2]),
                "phone": c[3] or "", "phone9": _phone9(c[3]),
                "city": city, "country": c[5] or "", "agent": agent,
                "customer_no": str(c[7]) if c[7] else "", "cids": cids, "mqids": mqids, "ips": ips,
                "reg": reg, "fda": fda, "own_logins": set(own_logins)}
    if lead_id is not None:
        l = db.execute(text("""
            SELECT id, full_name, email, phone,
                   COALESCE(NULLIF(city_canon,''), city) AS city, country, customer_no
            FROM leads WHERE id=:l
        """), {"l": lead_id}).fetchone()
        if not l:
            return None
        return {"kind": "lead", "id": lead_id, "login": None, "name": l[1] or f"lead#{lead_id}",
                "reg": None, "fda": None,
                "email": (l[2] or "").lower().strip(), "email_norm": _norm_email(l[2]),
                "phone": l[3] or "", "phone9": _phone9(l[3]),
                "city": (l[4] or "").strip(), "country": l[5] or "", "agent": 0,
                "customer_no": str(l[6]) if l[6] else "", "cids": [], "mqids": [], "ips": []}
    return None


def score_connections(db, login=None, lead_id=None, limit=60):
    """Return the subject's connections ranked by confidence (most-certain first)."""
    subj = _subject(db, login=login, lead_id=lead_id)
    if not subj:
        return {"subject": None, "connections": []}

    # candidate client login -> {signal -> shared value}
    cand = defaultdict(dict)

    # ── strong: shared device/ip tokens (cid/mqid/ip) — clients only ──
    tokens = [("cid", v) for v in subj["cids"]] + [("mqid", v) for v in subj["mqids"]] + \
             [("ip", v) for v in subj["ips"]]
    if tokens:
        # fan-out is capped on DISTINCT CUSTOMERS (not logins) — one person's 10 accounts on their own
        # IP must not burn the cap, and this is the same grain build_network_scores uses, so the popup
        # and the stored badge never disagree about which tokens count.
        rows = db.execute(text("""
            SELECT ai.identifier_type, ai.identifier_value, array_agg(DISTINCT ai.login) AS logins
            FROM account_identifiers ai
            LEFT JOIN clients c ON c.login = ai.login
            WHERE (ai.identifier_type, ai.identifier_value) IN :pairs
            GROUP BY ai.identifier_type, ai.identifier_value
            HAVING COUNT(DISTINCT COALESCE(c.customer_no, ai.login::text)) <= :fan
        """).bindparams(__import__("sqlalchemy").bindparam("pairs", expanding=True)),
            {"pairs": tokens, "fan": MAX_TOKEN_FANOUT}).fetchall()
        _own = subj.get("own_logins") or {subj["login"]}
        for typ, val, logins in rows:
            for lg in logins:
                if lg not in _own:                    # skip this person's own sibling accounts
                    cand[("client", lg)][typ] = val

    # ── IP + TIMING: a bare shared IP means nothing here (no static IPs; every CRM/MT login adds one),
    #    but the SAME IP that registered two accounts within IP_COREG_HOURS — or funded their first
    #    deposits within IP_CODEP_HOURS — is one person/desk at one connection. That IS a link.
    _ip_keys = [k for k, s in cand.items() if "ip" in s and k[0] == "client"]
    if _ip_keys and (subj.get("reg") or subj.get("fda")):
        for lg, reg, fda in db.execute(text("""
            -- CUSTOMER-level earliest reg / first deposit (same grain as build_network_scores)
            SELECT c.login,
                   MIN(NULLIF(COALESCE(s.reg_date, c.reg_date),'')),
                   MIN(NULLIF(COALESCE(s.first_deposit_at, c.first_deposit_at),''))
            FROM clients c
            LEFT JOIN clients s ON c.customer_no IS NOT NULL AND s.customer_no = c.customer_no
            WHERE c.login = ANY(:l)
            GROUP BY c.login
        """), {"l": [k[1] for k in _ip_keys]}).fetchall():
            k = ("client", lg)
            if k not in cand:
                continue
            if _within(subj.get("reg"), reg, IP_COREG_HOURS):
                cand[k]["ip_coreg"] = str(reg)[:16]
            if _within(subj.get("fda"), fda, IP_CODEP_HOURS):
                cand[k]["ip_codep"] = str(fda)[:16]

    # NOTE: EXACT email / phone are NOT connection factors (two different users can't share them =
    # same customer, handled by customer_no). Only SIMILAR email links two DIFFERENT people.

    # ── SIMILAR email: same normalized local part (dots/+tags moved → same inbox, e.g. ahmed.zaman
    #    ≈ ahme.dzaman ≈ ahmedzaman) OR a ≤2-character typo (ahmedzaman ≈ ahmadzaman). Catches the
    #    relative/duplicate-email trick where a fraudster tweaks 1-4 letters. ──
    sne = subj.get("email_norm") or ""
    sco = re.sub(r"\d", "", sne)                       # letters-only core (ahmedzaman1 ≈ ahmedzaman)
    # COMMON-NAME GUARD: if the subject's core is a common first name / generic token (ali, ahmed,
    # mohammed, iraqx, souriahost…), a similar-email hit means nothing on its own — millions share it.
    # Those candidates are marked PROVISIONAL and are kept only if same city / IP / IB corroborates.
    sco_common = is_common_core(db, sco)
    provisional_se = set()
    if len(sne) >= 4:
        nec = _norm_email_sql("email")
        core = f"regexp_replace({nec}, '[0-9]', '', 'g')"
        # similar-email = normalized-equal (dots/+tags) OR same letters-core (ignores digit suffixes:
        # ahmedzaman1 ≈ ahmedzaman2). The old Levenshtein<=3 arm was REMOVED: it matched different
        # people outright (ahmed1990 vs ahmad1991 = distance 2) and it was the one rule the bulk score
        # builder could not reproduce, so badge and popup disagreed. Both now use these two rules only.
        cond = (f"( {nec} = :ne OR (length(:sco) >= 5 AND {core} = :sco) )")
        p = {"ne": sne[:64], "sco": sco}
        for lg, em in db.execute(text(f"""
            SELECT login, email FROM clients
            WHERE login<>:self AND email IS NOT NULL AND email<>'' AND {cond} LIMIT 120
        """), {**p, "self": subj["login"] or -1}).fetchall():
            if not cand[("client", lg)].get("email"):          # don't downgrade an exact match
                cand[("client", lg)]["similar_email"] = em
                if sco_common:
                    provisional_se.add(("client", lg))
        for lid, em in db.execute(text(f"""
            SELECT id, email FROM leads
            WHERE id<>:self AND email IS NOT NULL AND email<>'' AND {cond} LIMIT 120
        """), {**p, "self": subj["id"] if subj["kind"] == "lead" else -1}).fetchall():
            if not cand[("lead", lid)].get("email"):
                cand[("lead", lid)]["similar_email"] = em
                if sco_common:
                    provisional_se.add(("lead", lid))

    # (exact phone removed as a connection factor — same phone = same customer; family comes from the
    #  family-code system, not a raw phone match.)

    # ── strong: shared PAYMENT SENDER — two accounts funded by the SAME sender (Qi = same sender NAME
    #    on the receipt, NOT the card number; zain = same wallet) are directly linked (family / same
    #    funder), unlike merely sharing a payment METHOD. High-fanout senders (a money exchanger funding
    #    many unrelated clients) are excluded (fanout > PAY_SENDER_MAX_FANOUT).
    if subj["login"] and _table_exists(db, "client_payment_senders"):
        for lg, mth, key in db.execute(text("""
            SELECT DISTINCT b.client_login, a.method, a.sender_key
            FROM client_payment_senders a
            JOIN client_payment_senders b
              ON b.method=a.method AND b.sender_key=a.sender_key AND b.client_login<>a.client_login
            WHERE a.client_login=:self AND a.fanout BETWEEN 2 AND :maxfan
        """), {"self": subj["login"], "maxfan": PAY_SENDER_MAX_FANOUT}).fetchall():
            if lg != subj["login"]:
                cand[("client", lg)]["pay_sender"] = f"{mth.upper()} · {key}"

    if not cand:
        return {"subject": _subject_brief(subj), "connections": []}

    client_logins = [cid for (k, cid) in cand if k == "client"]
    lead_ids = [lid for (k, lid) in cand if k == "lead"]

    # enrich candidates + add BOOSTER signals (ib / city / payment)
    cmeta = {}
    if client_logins:
        # city / IB at CUSTOMER grain (cc), same as the subject and the score builder — a person's IB
        # or city may sit on a sibling login, and judging the single account made badge != popup.
        for r in db.execute(text("""
            SELECT c.login, c.name,
                   COALESCE(NULLIF(cc.city,''), NULLIF(c.city_canon,''), c.city) AS city,
                   c.country, COALESCE(cc.agent, c.agent) AS agent, COALESCE(c.balance,0),
                   i.name AS ib_name, c.customer_no
            FROM clients c
            LEFT JOIN LATERAL (
                SELECT MIN(NULLIF(s.city_canon,'')) AS city, MIN(NULLIF(s.agent,0)) AS agent
                FROM clients s WHERE c.customer_no IS NOT NULL AND s.customer_no = c.customer_no
            ) cc ON TRUE
            LEFT JOIN ibs i ON i.agent_id = COALESCE(cc.agent, c.agent)
            WHERE c.login=ANY(:l)
        """), {"l": client_logins}).fetchall():
            cmeta[("client", r[0])] = {"name": r[1] or f"#{r[0]}", "city": (r[2] or "").strip(),
                                       "country": r[3] or "", "agent": r[4] or 0,
                                       "balance": float(r[5] or 0), "ib_name": r[6] or "",
                                       "customer_no": str(r[7]) if r[7] else ""}
    lmeta = {}
    if lead_ids:
        for r in db.execute(text("""
            SELECT id, full_name, COALESCE(NULLIF(city_canon,''), city) AS city, country
            FROM leads WHERE id=ANY(:l)
        """), {"l": lead_ids}).fetchall():
            lmeta[("lead", r[0])] = {"name": r[1] or f"lead#{r[0]}", "city": (r[2] or "").strip(),
                                     "country": r[3] or "", "agent": 0, "balance": 0.0, "ib_name": ""}

    # payment methods (real ones) per subject + candidates, for the payment booster
    def real_methods(logins):
        if not logins:
            return set()
        rows = db.execute(text("""
            SELECT DISTINCT lower(trim(method)) FROM transactions
            WHERE login=ANY(:l) AND method IS NOT NULL AND trim(method)<>''
              AND tx_type IN ('deposit','withdrawal')
        """), {"l": logins}).fetchall()
        # Qi / ZainCash / ShamCash are handled by the SAME-SENDER signal (pay_sender), NOT by "same
        # method" — two people both using "Qi card" is not a link; using the same Qi CARD is. So drop
        # those methods from the method-booster; keep USDT and the rest (same method still counts there).
        skip = {"deposit", "withdrawal", "credit", "bonus", "adjustment", ".", "",
                "qi card", "qi", "qicard", "zaincash", "zain cash", "zc", "sham cash", "shamcash", "sham"}
        return {m for (m,) in rows if m and m not in skip and "bonus" not in m and "adjust" not in m
                and "qi" not in m and "zain" not in m and "sham" not in m}
    subj_methods = real_methods([subj["login"]] if subj["login"] else [])

    out = []
    subj_cn = subj.get("customer_no") or ""
    for key, sigs in cand.items():
        meta = cmeta.get(key) or lmeta.get(key)
        if not meta:
            continue
        # USER-WISE: never list the subject's OWN other trading accounts (same customer_no) as a
        # connection — a person's multiple accounts are one user, not a link.
        if subj_cn and meta.get("customer_no") and meta["customer_no"] == subj_cn:
            continue
        # booster: same IB
        if subj["agent"] and meta["agent"] and subj["agent"] == meta["agent"]:
            sigs["ib"] = meta["ib_name"] or f"#{subj['agent']}"
        # booster: same city
        if subj["city"] and meta["city"] and subj["city"].lower() == meta["city"].lower():
            sigs["city"] = meta["city"]
        # COMMON-NAME GUARD: this candidate was found only because a COMMON email core matched
        # (ali/ahmed/mohammed/iraqx…). Millions share those, so it is NOT a link unless something
        # real corroborates it — same city, IP, IB (or a device/payment tie). Otherwise drop it.
        # Baghdad does NOT corroborate: it's ~1/3 of the book, so "both Ali + both Baghdad" is noise.
        if key in provisional_se:
            corr = set(sigs) & EMAIL_CORROBORATORS
            if "city" in corr and (meta["city"] or "").strip().lower() in WEAK_CITIES:
                corr.discard("city")
            if not corr:
                continue
        # IP RULE: a shared IP on its own is NOT a connection — only alongside another factor
        # (city / IB / email / device) or with matching registration/deposit timing. A Baghdad "same
        # city" is NOT that factor (WEAK_CITIES: ~1/3 of the book), so IP + Baghdad is still nothing.
        eff = set(sigs)
        if "city" in eff and (meta["city"] or "").strip().lower() in WEAK_CITIES:
            eff.discard("city")
        if eff <= IP_ONLY:
            continue
        # collapse mqid into a device signal next to cid for scoring
        conf, x10 = _confidence(set(sigs.keys()))
        reasons = [{"type": s, "label": SIGNAL_LABEL.get(s, s), "value": str(v)[:40]}
                   for s, v in sorted(sigs.items(), key=lambda kv: SIGNAL_ORDER.index(kv[0]) if kv[0] in SIGNAL_ORDER else 99)]
        top = reasons[0]["type"] if reasons else ""
        out.append({
            "kind": key[0], "id": key[1], "login": key[1] if key[0] == "client" else None,
            "name": meta["name"], "city": meta["city"], "country": meta["country"],
            "ib_name": meta["ib_name"], "balance": meta["balance"], "customer_no": meta.get("customer_no", ""),
            "confidence": conf, "score10": x10, "reasons": reasons, "top_reason": top,
            "signal_count": len(sigs),
        })

    # payment booster needs candidate methods in batch (client candidates only)
    if subj_methods and client_logins:
        cand_methods = defaultdict(set)
        for lg, m in db.execute(text("""
            SELECT login, lower(trim(method)) FROM transactions
            WHERE login=ANY(:l) AND method IS NOT NULL AND trim(method)<>''
              AND tx_type IN ('deposit','withdrawal')
        """), {"l": client_logins}).fetchall():
            cand_methods[lg].add(m)
        for o in out:
            if o["kind"] == "client":
                shared = subj_methods & cand_methods.get(o["id"], set())
                shared = {m for m in shared if m not in ("deposit", "withdrawal", "credit")}
                if shared and not any(r["type"] == "payment" for r in o["reasons"]):
                    sigset = {r["type"] for r in o["reasons"]} | {"payment"}
                    o["confidence"], o["score10"] = _confidence(sigset)
                    o["reasons"].append({"type": "payment", "label": SIGNAL_LABEL["payment"],
                                         "value": ", ".join(sorted(shared))[:40]})
                    o["signal_count"] = len(sigset)

    out.sort(key=lambda o: (o["confidence"], o["signal_count"], o["balance"]), reverse=True)
    # USER-WISE dedupe: collapse a candidate CUSTOMER's multiple trading accounts into ONE connection
    # (keep the strongest). Leads + customers with no customer_no stay as-is.
    seen, deduped = set(), []
    for o in out:
        cn = o.get("customer_no") or ""
        if o["kind"] == "client" and cn:
            if cn in seen:
                continue
            seen.add(cn)
        deduped.append(o)
    return {"subject": _subject_brief(subj), "connections": deduped[:limit]}


def _subject_brief(subj):
    return {"kind": subj["kind"], "id": subj["id"], "login": subj["login"], "name": subj["name"],
            "city": subj["city"], "country": subj["country"]}


# ══════════════════════════════════════════════════════════════════════════════
# GROUP analysis — the "Connections" tab: a cluster of linked accounts + a verdict
# ══════════════════════════════════════════════════════════════════════════════
def group_stats(db, logins):
    """Money + trading + IB summary for a set of logins (per-member + totals)."""
    if not logins:
        return {"members": [], "totals": {}}
    rows = db.execute(text("""
        SELECT c.login, c.name, c.city, c.country, c.agent, c.group_name,
               COALESCE(c.credit,0), i.name AS ib_name,
               COALESCE(tx.dep,0), COALESCE(tx.wd,0), COALESCE(tx.bonus,0), tx.last_dep,
               COALESCE(dl.pnl,0), COALESCE(dl.trades,0), dl.winrate, COALESCE(dl.lots,0),
               COALESCE(ic.comm,0)
        FROM clients c
        LEFT JOIN ibs i ON i.agent_id=c.agent
        LEFT JOIN (
            SELECT login, SUM(amount) FILTER (WHERE tx_type='deposit') dep,
                   SUM(amount) FILTER (WHERE tx_type='withdrawal') wd,
                   SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus%') bonus,
                   MAX(tx_date) FILTER (WHERE tx_type='deposit') last_dep
            FROM transactions WHERE login=ANY(:l) GROUP BY login
        ) tx ON tx.login=c.login
        LEFT JOIN (
            SELECT login, SUM(profit) FILTER (WHERE entry=1) pnl,
                   COUNT(*) FILTER (WHERE entry=1 AND direction IN ('buy','sell')) trades,
                   AVG(CASE WHEN entry=1 AND profit>0 THEN 1.0 WHEN entry=1 THEN 0 END) winrate,
                   SUM(volume) FILTER (WHERE direction IN ('buy','sell'))/10000.0 lots
            FROM deals WHERE login=ANY(:l) GROUP BY login
        ) dl ON dl.login=c.login
        LEFT JOIN (
            SELECT client_login, SUM(commission_usd) comm
            FROM ib_commissions WHERE client_login=ANY(:l) GROUP BY client_login
        ) ic ON ic.client_login=c.login
        WHERE c.login=ANY(:l)
    """), {"l": logins}).fetchall()
    members = []
    T = {"deposits": 0.0, "withdrawals": 0.0, "bonus": 0.0, "pnl": 0.0, "lots": 0.0,
         "ib_commission": 0.0, "trades": 0}
    ibs = defaultdict(int)
    islamic = 0
    for r in rows:
        grp = r[5] or ""
        is_isl = ("-IS" in ("-" + grp.upper().replace("\\", "-") + "-")) or ("SWAP" in grp.upper())
        dep, wd, bonus, pnl = float(r[8] or 0), float(r[9] or 0), float(r[10] or 0), float(r[12] or 0)
        comm = float(r[16] or 0)
        m = {"login": r[0], "name": r[1] or f"#{r[0]}", "city": r[2] or "", "country": r[3] or "",
             "agent": r[4] or 0, "group": grp, "credit": float(r[6] or 0), "ib_name": r[7] or "",
             "deposits": dep, "withdrawals": wd, "bonus": bonus,
             "last_deposit": str(r[11]) if r[11] else "", "pnl": pnl, "trades": int(r[13] or 0),
             "win_rate": round(float(r[14]) * 100) if r[14] is not None else None,
             "lots": float(r[15] or 0), "ib_commission": comm, "is_islamic": is_isl}
        members.append(m)
        T["deposits"] += dep; T["withdrawals"] += wd; T["bonus"] += bonus; T["pnl"] += pnl
        T["lots"] += m["lots"]; T["ib_commission"] += comm; T["trades"] += m["trades"]
        if r[7]:
            ibs[r[7]] += 1
        if is_isl:
            islamic += 1
    T["net_to_clients"] = round(T["withdrawals"] - T["deposits"], 2)
    T = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in T.items()}
    members.sort(key=lambda x: x["deposits"] + x["withdrawals"], reverse=True)
    top_ib = sorted(ibs.items(), key=lambda kv: kv[1], reverse=True)
    return {"members": members, "totals": T, "islamic_count": islamic,
            "ib_names": [k for k, _ in top_ib],
            "dominant_ib": top_ib[0][0] if top_ib else "",
            "dominant_ib_share": (top_ib[0][1] / max(1, len(members))) if top_ib else 0}


def classify_group(stats):
    """Deterministic verdicts on a connection group. Returns a list of {tag,severity,title,detail}."""
    m = stats["members"]; T = stats["totals"]
    n = len(m)
    verdicts = []
    if n < 2:
        return verdicts
    dep, wd, bonus = T["deposits"], T["withdrawals"], T["bonus"]
    comm = T["ib_commission"]

    # 1) IB-commission farming — one IB owns most of the group, earns commission, accounts
    #    are bonus-fed / net-negative depositors (the IB profits off introduced churn).
    if stats["dominant_ib"] and stats["dominant_ib_share"] >= 0.5 and comm > 0 and (bonus > 0 or T["net_to_clients"] > 0):
        verdicts.append({
            "tag": "ib_farming", "severity": "high",
            "title": f"IB commission farming — {stats['dominant_ib']}",
            "detail": (f"{int(round(stats['dominant_ib_share']*100))}% of this group is introduced by "
                       f"{stats['dominant_ib']}, who has earned ${comm:,.0f} commission while the group took "
                       f"${bonus:,.0f} in bonus and is net {'+' if T['net_to_clients']>=0 else ''}${T['net_to_clients']:,.0f} "
                       f"to clients. The IB is monetising introduced churn / bonus.")})

    # 2) Bonus abuse / extraction — bonus given and clients pulled out >= what they deposited.
    if bonus > 0 and wd >= dep * 0.95 and wd > 0:
        verdicts.append({
            "tag": "bonus_abuse", "severity": "critical" if wd >= dep * 1.1 else "high",
            "title": "Bonus extraction",
            "detail": (f"The group received ${bonus:,.0f} in bonus and withdrew ${wd:,.0f} against "
                       f"${dep:,.0f} deposited (net {'+' if T['net_to_clients']>=0 else ''}${T['net_to_clients']:,.0f} "
                       f"to clients) — bonus is being converted to withdrawable cash.")})

    # 3) Toxic / latency-style — a member with near-perfect win-rate on real volume.
    toxic = [x for x in m if (x["win_rate"] or 0) >= 85 and x["trades"] >= 40]
    if toxic:
        names = ", ".join(f"#{x['login']} ({x['win_rate']}%)" for x in toxic[:3])
        verdicts.append({
            "tag": "toxic", "severity": "high",
            "title": "Toxic / abnormal win-rate",
            "detail": (f"{len(toxic)} account(s) win >=85% of trades on real volume ({names}) - "
                       f"a signature of latency/feed arbitrage or offsetting, not normal trading.")
        })

    # 4) Swap-free farming — Islamic accounts trading actively (carry harvested swap-free).
    isl_traders = [x for x in m if x["is_islamic"] and x["trades"] >= 20]
    if stats["islamic_count"] >= 2 and isl_traders:
        verdicts.append({
            "tag": "swap_free", "severity": "medium",
            "title": "Swap-free (Islamic) cluster",
            "detail": (f"{stats['islamic_count']} accounts are swap-free and {len(isl_traders)} trade actively — "
                       f"review for overnight carry harvested without paying swap.")})

    # 5) Internal money shuffling — one member feeds others (one big loser, others win).
    losers = [x for x in m if x["pnl"] < -200]
    winners = [x for x in m if x["pnl"] > 200]
    if losers and winners and bonus > 0:
        biggest_loser = min(m, key=lambda x: x["pnl"])
        verdicts.append({
            "tag": "offsetting", "severity": "high",
            "title": "Offsetting inside the group",
            "detail": (f"#{biggest_loser['login']} is the designated loser (P&L ${biggest_loser['pnl']:,.0f}, "
                       f"bonus ${biggest_loser['bonus']:,.0f}) while {len(winners)} linked accounts win — "
                       f"the loss (funded by bonus) is moved to clean winners that can withdraw.")})

    if not verdicts:
        verdicts.append({"tag": "linked", "severity": "low", "title": "Linked accounts",
                         "detail": f"{n} accounts are linked but show no strong abuse pattern yet."})
    return verdicts


def _risk_rank(severity):
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 0)


def refresh_account(db, login):
    """Wire a freshly-opened account into the network the moment it's created. score_connections()
    reads live, but the persisted network_edges layer (network graph + abuse views + clients.
    network_score) is refreshed here so the new account appears at once. Builds the immediately-known
    clients-table links (same phone = family, same name, same IB); device/IP edges are added by the
    bridge when the account first logs into MT. Idempotent + guarded."""
    if not login:
        return
    try:
        p = {"lg": int(login)}
        # same phone (last 9 digits) -> family/household
        db.execute(text("""
            INSERT INTO network_edges (login_a, login_b, reason, value)
            SELECT LEAST(a.login,b.login), GREATEST(a.login,b.login), 'family', a.phone
            FROM clients a JOIN clients b
              ON RIGHT(regexp_replace(COALESCE(b.phone,''),'[^0-9]','','g'),9) =
                 RIGHT(regexp_replace(COALESCE(a.phone,''),'[^0-9]','','g'),9)
             AND b.login <> a.login AND b.login IS NOT NULL
            WHERE a.login=:lg AND LENGTH(regexp_replace(COALESCE(a.phone,''),'[^0-9]','','g'))>=9
            ON CONFLICT DO NOTHING
        """), p)
        # same exact full name
        db.execute(text("""
            INSERT INTO network_edges (login_a, login_b, reason, value)
            SELECT LEAST(a.login,b.login), GREATEST(a.login,b.login), 'family', a.name
            FROM clients a JOIN clients b ON LOWER(TRIM(b.name))=LOWER(TRIM(a.name))
             AND b.login <> a.login AND b.login IS NOT NULL
            WHERE a.login=:lg AND LENGTH(TRIM(COALESCE(a.name,'')))>5
            ON CONFLICT DO NOTHING
        """), p)
        # same IB / agent
        db.execute(text("""
            INSERT INTO network_edges (login_a, login_b, reason, value)
            SELECT LEAST(a.login,b.login), GREATEST(a.login,b.login), 'ib', CAST(a.agent AS TEXT)
            FROM clients a JOIN clients b ON b.agent=a.agent AND b.login <> a.login AND b.login IS NOT NULL
            WHERE a.login=:lg AND a.agent>0
            ON CONFLICT DO NOTHING
        """), p)
        # NOTE: clients.network_score is NO LONGER written here. It is now a single canonical
        # 0-10 score owned by build_network_scores.py (customer-wise, same scale everywhere). This
        # per-login edge writer produced a divergent 0-100 value and is why the same client showed a
        # different x/10 on different pages. We keep maintaining `network_edges` above; the canonical
        # score refreshes on the nightly build (or on-demand: python build_network_scores.py).
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[connection] refresh_account({login}) failed: {e}", flush=True)


def connection_groups(db, limit=60, min_size=2):
    """Connected-component groups across device(cid/mqid)/ip/phone/email, annotated with
    money/IB stats + a deterministic verdict. The Network 'Connections' tab."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # ── USER-WISE, not account-wise: collapse a customer's many trading accounts (logins) into ONE
    #    node keyed by customer_no. We union CUSTOMERS — so one customer's own accounts can NEVER form a
    #    ring; only links between DIFFERENT customers (clients/leads/IB) do. ──────────────────────────
    cust = {}
    for lg, cn in db.execute(text("SELECT login, customer_no FROM clients WHERE customer_no IS NOT NULL AND login IS NOT NULL")).fetchall():
        cust[lg] = "C:" + str(cn)
    def _ck(lg):
        return cust.get(lg) or ("L:" + str(lg))
    cust_logins = defaultdict(list)
    for lg, ck in cust.items():
        cust_logins[ck].append(lg)

    links = defaultdict(list)  # customer_key pairs + reason type
    def _union_members(members, typ):
        cs = sorted({_ck(lg) for lg in members})           # collapse logins → customers first
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                union(cs[i], cs[j]); links[find(cs[i])].append((cs[i], cs[j], typ))

    # device (cid/mqid) + IP only — EXACT email/phone are NOT connection factors (same = same customer)
    for typ, val, members in db.execute(text("""
        SELECT identifier_type, identifier_value, array_agg(DISTINCT login) m
        FROM account_identifiers
        WHERE identifier_type IN ('cid','mqid','ip') AND identifier_value NOT IN ('0','')
        GROUP BY identifier_type, identifier_value
        HAVING COUNT(DISTINCT login) BETWEEN 2 AND :fan
    """), {"fan": MAX_TOKEN_FANOUT}).fetchall():
        _union_members(members, typ)
    _NE = _norm_email_sql("email")
    for nemail, members in db.execute(text(f"""
        SELECT {_NE} ne, array_agg(DISTINCT login) m FROM clients
        WHERE email IS NOT NULL AND email<>'' AND length({_NE})>=4
        GROUP BY {_NE} HAVING COUNT(DISTINCT login) BETWEEN 2 AND :fan
    """), {"fan": MAX_TOKEN_FANOUT}).fetchall():
        _union_members(members, "similar_email")
    # shared PAYMENT SENDER (same Qi card / wallet funded them) — SAME strong signal the per-client
    # view uses; low fanout only (a money exchanger funding many people is NOT a family link).
    if _table_exists(db, "client_payment_senders"):
        for _k, members in db.execute(text("""
            SELECT method || ':' || sender_key AS k, array_agg(DISTINCT client_login) m
            FROM client_payment_senders WHERE fanout BETWEEN 2 AND :maxfan
            GROUP BY method, sender_key HAVING COUNT(DISTINCT client_login) BETWEEN 2 AND :fan
        """), {"maxfan": PAY_SENDER_MAX_FANOUT, "fan": MAX_TOKEN_FANOUT}).fetchall():
            _union_members(members, "pay_sender")

    # components of CUSTOMERS; keep rings of 2..fan DIFFERENT customers, then expand to their logins
    comp = defaultdict(set)
    for node in list(parent):
        comp[find(node)].add(node)
    comps = []
    for root, custs in comp.items():
        if not (min_size <= len(custs) <= MAX_TOKEN_FANOUT):
            continue
        logins = [lg for ck in custs for lg in cust_logins.get(ck, [])] or \
                 [int(ck[2:]) for ck in custs if ck.startswith("L:") and ck[2:].isdigit()]
        comps.append((root, logins, len(custs)))

    # ── PRE-RANK cheaply (no deals): one pass over transactions for dep/wd/bonus per login ──
    tx_by_login = {}
    for lg, dep, wd, bonus in db.execute(text("""
        SELECT login, COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit'),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal'),0),
               COALESCE(SUM(amount) FILTER (WHERE tx_type ILIKE 'bonus%'),0)
        FROM transactions GROUP BY login
    """)).fetchall():
        tx_by_login[lg] = (float(dep), float(wd), float(bonus))
    scored = []
    for root, members, n_cust in comps:
        dep = wd = bonus = 0.0
        for lg in members:
            d, w, b = tx_by_login.get(lg, (0, 0, 0))
            dep += d; wd += w; bonus += b
        exposure = bonus + max(0.0, wd - dep)
        scored.append((exposure, n_cust, root, members))
    scored.sort(reverse=True, key=lambda x: (x[0], x[1]))
    top = scored[:max(limit * 2, limit)]

    groups = []
    for exposure, n_cust, root, members in top:
        st = group_stats(db, members)
        cmembers = _collapse_by_customer(st["members"], cust)   # ONE row per customer, accounts summed
        verdicts = classify_group(st)
        sev = max((v["severity"] for v in verdicts), key=_risk_rank, default="low")
        reasons = sorted({r[2] for r in links.get(root, [])},
                         key=lambda s: SIGNAL_ORDER.index(s) if s in SIGNAL_ORDER else 99)
        primary = sorted(reasons, key=lambda s: LINK_PRIORITY.get(s, 99))[0] if reasons else "link"
        groups.append({
            "id": min(members) if members else 0, "size": len(members), "members": cmembers,
            "totals": st["totals"], "ib_names": st["ib_names"], "dominant_ib": st["dominant_ib"],
            "link_reasons": reasons, "primary_link": primary, "verdicts": verdicts, "severity": sev,
            "same_person": False, "n_people": n_cust, "_logins": members,
            "top_verdict": verdicts[0]["title"] if verdicts else "Linked accounts",
        })
    # ORDER: link type (CID → IB → City → Family → Email → IP → Payment) then severity then exposure
    groups.sort(key=lambda g: (LINK_PRIORITY.get(g["primary_link"], 99),
                               -_risk_rank(g["severity"]),
                               -(g["totals"].get("bonus", 0) + max(0, g["totals"].get("net_to_clients", 0)))))
    out_groups = groups[:limit]
    # connection detail uses ALL logins of the ring's customers (so cross-customer links are found)
    for g in out_groups:
        g["links"] = group_links(db, g.pop("_logins"))
    return out_groups


def _collapse_by_customer(members, cust):
    """Collapse a ring's per-login member rows into ONE row per CUSTOMER (a person may hold several
    trading accounts). Sums money; keeps a representative name/city/IB; counts the accounts."""
    by = {}
    for m in members:
        ck = cust.get(m.get("login")) or ("L:" + str(m.get("login")))
        g = by.get(ck)
        if not g:
            by[ck] = {**m, "accounts": 1, "logins": [m.get("login")]}
        else:
            for k in ("deposits", "withdrawals", "bonus", "pnl", "trades"):
                if m.get(k) is not None:
                    g[k] = (g.get(k) or 0) + m[k]
            g["accounts"] += 1
            g["logins"].append(m.get("login"))
            if not g.get("ib_name") and m.get("ib_name"):
                g["ib_name"] = m["ib_name"]
            if not g.get("city") and m.get("city"):
                g["city"] = m["city"]
            g["is_islamic"] = g.get("is_islamic") or m.get("is_islamic")
            if m.get("win_rate") is not None:
                g["win_rate"] = max(g.get("win_rate") or 0, m["win_rate"])
    out = list(by.values())
    out.sort(key=lambda x: (x.get("deposits", 0) + x.get("withdrawals", 0)), reverse=True)
    return out


def group_links(db, logins):
    """The 'how are they connected' web: each shared identifier (device CID/MQID, IP, email, phone,
    same name) and the exact group members that share it. This is the CONNECTION evidence — shown
    before/alongside the abuse verdict so the desk sees the links first, doubt second."""
    if not logins:
        return []
    out = []
    for typ, val, m in db.execute(text("""
        SELECT identifier_type, identifier_value, array_agg(DISTINCT login ORDER BY login) m
        FROM account_identifiers
        WHERE login = ANY(:l) AND identifier_type IN ('cid','mqid','ip')
          AND identifier_value NOT IN ('0','')
        GROUP BY identifier_type, identifier_value
        HAVING COUNT(DISTINCT login) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": typ, "value": str(val)[:60], "logins": [int(x) for x in m]})
    for nm, m in db.execute(text("""
        SELECT LOWER(TRIM(name)) nm, array_agg(DISTINCT login ORDER BY login) m FROM clients
        WHERE login = ANY(:l) AND length(trim(COALESCE(name,''))) > 5
        GROUP BY LOWER(TRIM(name)) HAVING COUNT(DISTINCT login) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": "name", "value": str(nm)[:60], "logins": [int(x) for x in m]})
    # similar/variant emails within the group (normalized inbox shared by ≥2 DIFFERENT raw emails)
    _NE = _norm_email_sql("email")
    for ne, m, ex in db.execute(text(f"""
        SELECT {_NE} ne, array_agg(DISTINCT login ORDER BY login) m, string_agg(DISTINCT lower(email), ', ') ex
        FROM clients WHERE login = ANY(:l) AND email IS NOT NULL AND email<>'' AND length({_NE})>=4
        GROUP BY {_NE} HAVING COUNT(DISTINCT login) >= 2 AND COUNT(DISTINCT lower(email)) >= 2
    """), {"l": logins}).fetchall():
        out.append({"type": "similar_email", "value": str(ex)[:70], "logins": [int(x) for x in m]})
    # shared payment sender (same Qi card / wallet) within the group
    if _table_exists(db, "client_payment_senders"):
        for mth, key, m in db.execute(text("""
            SELECT method, sender_key, array_agg(DISTINCT client_login ORDER BY client_login) m
            FROM client_payment_senders WHERE client_login = ANY(:l)
            GROUP BY method, sender_key HAVING COUNT(DISTINCT client_login) >= 2
        """), {"l": logins}).fetchall():
            out.append({"type": "pay_sender", "value": (str(mth).upper() + " · " + str(key))[:60],
                        "logins": [int(x) for x in m]})
    out.sort(key=lambda x: (SIGNAL_ORDER.index(x["type"]) if x["type"] in SIGNAL_ORDER else 99, -len(x["logins"])))
    return out
