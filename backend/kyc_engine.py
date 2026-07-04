"""
kyc_engine.py — process one registration's KYC end to end:

  1) read the ID fields with Claude vision   (kyc_ai, paid, ~10c)   -> falls back gracefully if no key
  2) face-match the selfie against the ID     (face_match, local, free)
  3) auto-verify  (name match / not expired / face / ID# not reused)
  4) network & family cross-check (duplicate phone/email, shared family code/surname)

Writes the structured fields + verdicts onto the registration (and mirrors key bits to the lead),
and returns a summary. Designed to run in a FastAPI BackgroundTask so the client is never blocked.
"""
import re
import json
import datetime
from difflib import SequenceMatcher
from sqlalchemy import text

import kyc_ai
import face_match


def ensure_kyc_columns(db):
    for col, typ in [
        ("ocr_fields", "JSONB"), ("face_score", "DOUBLE PRECISION"), ("face_verdict", "TEXT"),
        ("name_match", "BOOLEAN"), ("doc_expired", "BOOLEAN"), ("id_number", "TEXT"),
        ("verify_status", "TEXT"), ("network_json", "JSONB"), ("processed_at", "TIMESTAMP"),
        ("verify_reason", "TEXT"), ("family_group", "TEXT"), ("dup_handled", "BOOLEAN"),
    ]:
        db.execute(text(f"ALTER TABLE registrations ADD COLUMN IF NOT EXISTS {col} {typ}"))
    db.commit()


def _phone9(p):
    d = re.sub(r"[^0-9]", "", p or "")
    return d[-9:] if len(d) >= 9 else d


def _tokens(s):
    return [t for t in re.sub(r"[^a-z؀-ۿ ]", " ", (s or "").lower()).split() if len(t) > 1]


def _script(s):
    s = s or ""
    ar = len(re.findall(r"[؀-ۿ]", s))
    la = len(re.findall(r"[a-zA-Z]", s))
    return "ar" if ar > la else ("la" if la else "")


def _name_match(entered, extracted):
    a, b = set(_tokens(entered)), set(_tokens(extracted))
    if not a or not b:
        return None
    # Different scripts (e.g. the client typed their name in English but the ID is in Arabic) —
    # we can't reliably token-compare across scripts, so return None ("can't auto-compare" -> manual
    # review) rather than False ("mismatch"). Avoids falsely flagging legitimate Arabic-doc clients.
    if _script(entered) and _script(extracted) and _script(entered) != _script(extracted):
        return None
    # FUZZY token match: a typed token counts if it's ~the same as ANY token on the document
    # (>=0.8 similarity). Handles transliteration spelling variants like Ameer/Amir, Mohamed/
    # Muhammad, Hashim/Hashimi — which exact matching would wrongly reject.
    matched = sum(1 for x in a if any(SequenceMatcher(None, x, y).ratio() >= 0.8 for y in b))
    return matched >= min(2, len(a))      # at least 2 matching name tokens (or all, if name is short)


def _tok_eq(x, y):
    return bool(x) and bool(y) and SequenceMatcher(None, x, y).ratio() >= 0.85


def _name_chain_relation(applicant, holder):
    """Detect a PARENT / CHILD / SIBLING link from Arabic patronymic NAME CHAINS.
    Arabic names run [given, father, grandfather, great-grandfather, …]. So a man named
    'Ahmed Zaman Abdulsahib' has a FATHER whose name begins 'Zaman Abdulsahib …'. We can therefore
    tell that a proof of address in the name 'Zaman Abdulsahib Jasim' belongs to the applicant's
    FATHER purely from the name structure — before any Family-ID check. Likewise two people who
    share the chain from the 2nd name on are SIBLINGS (same father + grandfather).
    Cross-script safe (returns '' when the two names are in different scripts and can't be compared).
    Returns 'parent' | 'child' | 'sibling' | ''."""
    a, h = _tokens(applicant), _tokens(holder)
    if len(a) < 2 or len(h) < 2:
        return ""
    if a == h:                      # identical chain = the same person (handled by the own-name check)
        return ""
    if _script(applicant) and _script(holder) and _script(applicant) != _script(holder):
        return ""
    # holder is the applicant's FATHER: applicant[given, FATHER, GRANDF] vs holder[FATHER, GRANDF, …]
    if len(a) >= 3 and _tok_eq(a[1], h[0]) and _tok_eq(a[2], h[1]):
        return "parent"
    # applicant is the holder's FATHER (mirror image)
    if len(h) >= 3 and _tok_eq(h[1], a[0]) and _tok_eq(h[2], a[1]):
        return "child"
    # SIBLINGS: same father + grandfather chain (positions 2 and 3 line up)
    if len(a) >= 3 and len(h) >= 3 and _tok_eq(a[1], h[1]) and _tok_eq(a[2], h[2]):
        return "sibling"
    return ""


def _stated_relative_match(holder, fields):
    """Match the proof-of-address holder against the parent names PRINTED ON THE APPLICANT'S OWN ID.
    A MOTHER keeps her own name chain (given · HER father · HER grandfather) so the patronymic trick
    can't see her — but Iraqi IDs carry the mother's name + her father's name, and the father's name,
    so we can confirm a parent straight from the applicant's document (no extra upload needed).
    Local fuzzy first, then the AI judge (transliteration-aware) for the cross-script case.
    Returns 'mother' | 'parent' | ''."""
    h = _tokens(holder)
    if len(h) < 2:
        return ""
    mother = " ".join(x for x in [fields.get("mother_name"), fields.get("mother_father_name")] if x).strip()
    father = " ".join(x for x in [fields.get("father_name"), fields.get("grandfather_name")] if x).strip()

    def _overlap(name):
        t = _tokens(name)
        return sum(1 for x in t if any(SequenceMatcher(None, x, y).ratio() >= 0.85 for y in h))

    for rel, name in (("mother", mother), ("parent", father)):
        if not name:
            continue
        if _overlap(name) >= 2:
            return rel
        # cross-script / transliteration spelling — ask the AI judge
        try:
            if kyc_ai.names_match(name, [holder]) is True:
                return rel
        except Exception:
            pass
    return ""


def _expired(expiry):
    try:
        d = datetime.date.fromisoformat((expiry or "")[:10])
        return d < datetime.date.today()
    except Exception:
        return None                        # unknown / unreadable


def _mask_email(e):
    """ahmad@gmail.com -> ah***d@gmail.com (enough for the owner to recognise, not enough to leak)."""
    e = (e or "").strip()
    if "@" not in e:
        return ""
    local, dom = e.split("@", 1)
    if len(local) <= 2:
        ml = local[:1] + "*"
    else:
        ml = local[:2] + "*" * max(1, len(local) - 3) + local[-1]
    return ml + "@" + dom


def _mask_phone(p):
    d = re.sub(r"[^0-9]", "", p or "")
    if len(d) < 6:
        return ""
    return d[:4] + "*" * (len(d) - 8) + d[-4:] if len(d) > 8 else d[:2] + "****" + d[-2:]


def _handle_existing_account(db, registration_id, reg, existing):
    """A re-registration was detected as an EXISTING client. Tag the existing lead so sales acts on it:
    +100 score (pull it to the top), a 'duplicate attempt' badge, the NEW contact the person tried (so
    the leads page can show it in a different colour), and a plain-language note. Best-effort; the email
    is sent by the caller. Never raises."""
    try:
        new_name = ((reg.first_name or "") + " " + (reg.last_name or "")).strip()
        new_email = reg.email or ""
        new_phone = reg.phone or ""
        basis = existing.get("match_basis") or "identity match"
        ex_email = existing.get("email") or ""
        ex_phone = existing.get("phone") or ""
        ex_login = existing.get("login")
        for tbl in ("leads", "clients"):
            for col, typ in (("has_dup_attempt", "BOOLEAN"), ("dup_new_contact", "JSONB")):
                try:
                    db.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {typ}")); db.commit()
                except Exception:
                    db.rollback()
        note = (f"⚠ POSSIBLE RE-REGISTRATION ({basis}). This person already has a TNFX account"
                + (f" (login {ex_login})" if ex_login else "")
                + f" and just tried to register again as '{new_name}' with NEW phone {new_phone} / NEW email "
                f"{new_email}. They were told to log in to their existing account. Please call to confirm.")
        newc = json.dumps({"name": new_name, "phone": new_phone, "email": new_email, "basis": basis})
        lead = db.execute(text("""
            SELECT id FROM leads
            WHERE (:em<>'' AND lower(email)=lower(:em))
               OR (:p9<>'' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p9)
            ORDER BY id LIMIT 1
        """), {"em": ex_email, "p9": (_phone9(ex_phone) if ex_phone else "")}).fetchone()
        if lead:
            db.execute(text("""
                UPDATE leads SET score = COALESCE(score,0) + 100, has_dup_attempt=TRUE,
                    dup_new_contact=CAST(:nc AS JSONB),
                    notes = CASE WHEN COALESCE(notes,'')='' THEN :note ELSE notes || E'\n' || :note END
                WHERE id=:l
            """), {"nc": newc, "note": note, "l": lead.id})
        if ex_login:
            db.execute(text("UPDATE clients SET has_dup_attempt=TRUE, dup_new_contact=CAST(:nc AS JSONB) WHERE login=:lg"),
                       {"nc": newc, "lg": ex_login})
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[kyc] existing-account tagging failed for reg {registration_id}: {e}", flush=True)


def process(db, registration_id):
    ensure_kyc_columns(db)
    reg = db.execute(text("""
        SELECT id, first_name, last_name, phone, email, country, state, city, lead_id, mt_login, address
        FROM registrations WHERE id=:r
    """), {"r": registration_id}).fetchone()
    if not reg:
        return {"ok": False, "error": "registration not found"}

    docs = db.execute(text("""
        SELECT id, doc_type, side, file_path, status FROM reg_kyc_documents WHERE registration_id=:r
    """), {"r": registration_id}).fetchall()
    id_doc = next((d for d in docs if d.side in ("front", "main")), None)
    selfie = next((d for d in docs if d.side == "selfie"), None)

    # 1) OCR the ID (front)
    fields = {}
    if id_doc:
        fields = kyc_ai.extract_id_fields(id_doc.file_path, id_doc.doc_type) or {}
        db.execute(text("UPDATE reg_kyc_documents SET ocr_json=:j, status='read' WHERE id=:i"),
                   {"j": json.dumps(fields), "i": id_doc.id})

    # 1b) OCR the BACK side too — on Iraqi national IDs the date of birth, family/record number
    # and the mother's name (+ her father's name) live on the back. Merge anything the front lacks.
    back_doc = next((d for d in docs if d.side == "back"), None)
    back_fields_keys = ("date_of_birth", "family_code", "mother_name", "mother_father_name",
                        "id_number", "issue_date", "expiry_date", "place_of_birth", "grandfather_name")
    if back_doc and not all((fields.get(k) or "").strip() for k in ("date_of_birth", "family_code", "mother_name")):
        back = kyc_ai.extract_id_fields(back_doc.file_path, (id_doc.doc_type if id_doc else "national_id")) or {}
        if not back.get("_status"):
            for k in back_fields_keys:
                if not (fields.get(k) or "").strip() and (back.get(k) or "").strip():
                    fields[k] = back.get(k)
            db.execute(text("UPDATE reg_kyc_documents SET ocr_json=:j WHERE id=:i"),
                       {"j": json.dumps(back), "i": back_doc.id})
            # keep the merged superset on the front/main row so detail views show everything
            if id_doc:
                db.execute(text("UPDATE reg_kyc_documents SET ocr_json=:j WHERE id=:i"),
                           {"j": json.dumps(fields), "i": id_doc.id})

    # 2) face-match selfie vs ID
    face = {"verdict": "no_selfie"} if not (id_doc and selfie) else \
        face_match.compare(id_doc.file_path, selfie.file_path)

    # 3) auto-verify
    entered_name = ((reg.first_name or "") + " " + (reg.last_name or "")).strip()
    extracted_name = fields.get("full_name") or fields.get("full_name_latin") or fields.get("full_name_ar") or ""
    # id_number: only a GENUINE, non-empty value counts. The model is instructed to return ""
    # when no ID/serial number is visible — never store a placeholder. Empty -> NULL (below).
    # HARD GUARD: never trust an id_number from a simulated/placeholder OCR payload. If the
    # fields dict is flagged simulated (e.g. a demo/fallback generator), drop the id_number so
    # a fabricated value can never be persisted or cross-checked. Real Claude OCR (kyc_ai) never
    # sets these flags. (Ticket #25: a portal demo path produced random 12-digit IDs.)
    simulated = bool(fields.get("_simulated") or fields.get("_status") in ("simulated", "placeholder"))
    id_number = "" if simulated else (fields.get("id_number") or "").strip()
    if not id_number:
        id_number = ""
    # match the typed name against EVERY name variant the document gives us — crucially the Latin
    # transliteration (full_name_latin), so an English-typed name matches an Arabic-only document
    # and legitimate Arabic-ID clients auto-verify instead of all queuing for manual review.
    _name_candidates = [
        fields.get("full_name_latin"), fields.get("full_name"), fields.get("full_name_ar"),
        " ".join(x for x in [fields.get("first_name"), fields.get("father_name"), fields.get("surname")] if x),
    ]
    nm = None
    for _cand in _name_candidates:
        _r = _name_match(entered_name, _cand)
        if _r is True:
            nm = True
            break
        if _r is False:
            nm = False   # a real mismatch on one variant; keep looking for a positive match
    # If the fast local match didn't clearly confirm, ask the AI (it understands Arabic<->English
    # transliteration & spelling variants) — this is what lets legitimate Arabic-ID clients
    # auto-verify instead of all queueing for manual review. AI verdict is authoritative.
    if nm is not True and entered_name and any(_name_candidates):
        _ai_nm = kyc_ai.names_match(entered_name, _name_candidates)
        if _ai_nm is not None:
            nm = _ai_nm
    expired = _expired(fields.get("expiry_date"))
    fv = face.get("verdict")

    has_ocr = bool(extracted_name) and not fields.get("_status")
    # face-match is OPTIONAL (no selfie collected) — it only blocks on an explicit mismatch.
    if fv == "mismatch" or expired is True:
        status = "rejected"
    elif not has_ocr or fields.get("_status") == "pending_no_key":
        status = "pending"               # Claude half not run yet (no key)
    elif nm and expired is not True:     # name matches + doc not known-expired (unknown expiry is OK) -> verified
        status = "verified"
    else:
        status = "review"                # name uncertain/mismatch -> desk review

    # 4) network & family cross-check
    p9 = _phone9(reg.phone)
    dup_phone = db.execute(text("""
        SELECT (SELECT COUNT(*) FROM clients WHERE RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p)
             + (SELECT COUNT(*) FROM leads WHERE id<>:lid AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=:p)
    """), {"p": p9, "lid": reg.lead_id or 0}).scalar() if p9 else 0
    dup_email = db.execute(text("""
        SELECT (SELECT COUNT(*) FROM clients WHERE lower(email)=lower(:e))
             + (SELECT COUNT(*) FROM leads WHERE id<>:lid AND lower(email)=lower(:e))
    """), {"e": reg.email or "", "lid": reg.lead_id or 0}).scalar() if reg.email else 0

    # ── FAMILY DETECTION (informational, NEVER blocks; only a duplicate ID blocks) ──
    # Tiers requested by the desk:
    #   • same OFFICIAL family ID (family_code) OR same home ADDRESS            -> GREEN (confirmed)
    #   • same grandfather name AND surname                                     -> YELLOW (probable)
    #   • (same grandfather OR surname) + same province/city                    -> GREEN (confirmed)
    # NEVER group on grandfather name alone. Each household also gets one stable INTERNAL family code.
    # GUARD: family/network detection is INFORMATIONAL — it must NEVER crash the verdict. The whole
    # block is wrapped in try/except so a bug here can't silently freeze a KYC (it used to: a missing
    # reg column threw, the background task swallowed it, and the client sat on "under review").
    fam_code = (fields.get("family_code") or "").strip()                 # OFFICIAL family ID from the ID
    fam_matches = []
    family = {}
    family_group = None
    try:
        def _norm(s):
            return re.sub(r"\s+", " ", (s or "").strip().lower())

        def _surname_of(fd):
            return _norm(fd.get("surname") or (fd.get("full_name_latin") or fd.get("full_name") or "").split(" ")[-1])

        my_surname = _surname_of(fields)
        my_gf = _norm(fields.get("grandfather_name"))
        my_prov = _norm(reg.state or reg.city or fields.get("city"))
        addr = _norm(reg.address)

        members = []
        inherited_group = None   # the FIRST (earliest-registered) family member's code — we reuse it
        inherited_from = None
        others = db.execute(text("""
            SELECT id, first_name, last_name, state, city, address, ocr_fields, family_group
            FROM registrations WHERE id<>:r AND ocr_fields IS NOT NULL
            ORDER BY id ASC
        """), {"r": registration_id}).fetchall()
        for o in others:
            of = o.ocr_fields if isinstance(o.ocr_fields, dict) else {}
            o_fid = (of.get("family_code") or "").strip()
            o_surname = _surname_of(of)
            o_gf = _norm(of.get("grandfather_name"))
            o_prov = _norm(o.state or o.city or of.get("city"))
            o_addr = _norm(o.address)
            color = link = None
            if fam_code and o_fid and fam_code == o_fid:
                color, link = "green", "same family ID"
            elif addr and o_addr and addr == o_addr and len(addr) >= 6:
                color, link = "green", "same address"
            elif my_gf and my_surname and o_gf == my_gf and o_surname == my_surname:
                color, link = ("green", "surname + grandfather + city") if (my_prov and my_prov == o_prov) else ("yellow", "surname + grandfather")
            elif my_prov and my_prov == o_prov and ((my_gf and o_gf == my_gf) or (my_surname and o_surname == my_surname)):
                color, link = "green", "name + city"
            if color:
                members.append({"registration_id": o.id,
                                "name": ((o.first_name or "") + " " + (o.last_name or "")).strip(),
                                "link": link, "color": color, "family_group": o.family_group})
                # the FIRST green relative who already has a family code -> we ALL share theirs
                if color == "green" and o.family_group and not inherited_group:
                    inherited_group = o.family_group
                    inherited_from = ((o.first_name or "") + " " + (o.last_name or "")).strip()

        # internal FAMILY CODE — ONE stable id per household. Reuse the FIRST family member's code so
        # the whole family shares it (e.g. Ameer registered first -> Zain inherits Ameer's code). Only
        # mint a new code if no earlier relative has one (official family ID if present, else a hash).
        import hashlib
        if inherited_group:
            family_group = inherited_group
        elif fam_code:
            family_group = "FID-" + re.sub(r"[^0-9A-Za-z]", "", fam_code)[:16]
        elif my_surname and (my_gf or my_prov):
            family_group = "FAM-" + hashlib.md5((my_surname + "|" + my_gf + "|" + my_prov).encode("utf-8")).hexdigest()[:8].upper()
        else:
            family_group = None

        fam_matches = members          # KYCPanel/network read family_code_matches
        any_green = any(m["color"] == "green" for m in members)
        family = {
            "members": members, "count": len(members),
            "color": ("green" if any_green else "yellow") if members else None,
            "same_address": any(m["link"] == "same address" for m in members),
            "same_family_id": any(m["link"] == "same family ID" for m in members),
            "family_code": family_group, "official_family_id": fam_code or None,
            "rank": len(members) + 1,
        } if (members or family_group) else {}
    except Exception as _fe:
        print(f"[kyc] family detection skipped for reg {registration_id}: {_fe}", flush=True)
        fam_matches = []; family = {}; family_group = None

    # ── ALREADY-HAVE-AN-ACCOUNT detection ──
    # The same person may re-register with a DIFFERENT email/phone/ID. We catch it with HIGH confidence:
    #   (a) same ID number, OR
    #   (b) same full NAME + (date of birth OR mother's name) — a KYC'd registration, OR
    #   (c) a full (3+ part) NAME match against an existing client (legacy accounts carry only a name).
    # -> status 'exists': the portal pops "log in to your existing account" with MASKED contact, signs
    #    them out, tags the existing lead, and emails the registrant.
    id_reuse = 0
    existing_account = {}
    match_basis = None
    def _nrm(s):
        return re.sub(r"\s+", " ", (s or "").strip().lower())
    my_name = _nrm(entered_name) or _nrm(extracted_name)
    my_dob = (fields.get("date_of_birth") or "").strip()
    my_mother = _nrm(fields.get("mother_name"))
    try:
        ex = None
        if id_number:                                   # (a) same ID number — strongest
            ex = db.execute(text("""
                SELECT id, first_name, last_name, email, phone, mt_login, created_at
                FROM registrations WHERE id<>:r AND id_number=:idn ORDER BY id LIMIT 1
            """), {"r": registration_id, "idn": id_number}).fetchone()
            if ex:
                match_basis = "same ID number"
        if not ex and my_name and (my_dob or my_mother):  # (b) same name + DOB/mother
            ex = db.execute(text("""
                SELECT id, first_name, last_name, email, phone, mt_login, created_at FROM registrations
                WHERE id<>:r
                  AND lower(regexp_replace(COALESCE(first_name,'')||' '||COALESCE(last_name,''),'\\s+',' ','g'))=:nm
                  AND ( (:dob<>'' AND ocr_fields->>'date_of_birth'=:dob)
                     OR (:mo<>''  AND lower(ocr_fields->>'mother_name')=:mo) )
                ORDER BY id LIMIT 1
            """), {"r": registration_id, "nm": my_name, "dob": my_dob, "mo": my_mother}).fetchone()
            if ex:
                match_basis = "same name + date of birth / mother"
        if ex:
            existing_account = {
                "registration_id": ex.id, "name": ((ex.first_name or "") + " " + (ex.last_name or "")).strip(),
                "email": ex.email, "phone": ex.phone, "login": ex.mt_login,
                "created_at": str(ex.created_at) if ex.created_at else None,
                "email_masked": _mask_email(ex.email), "phone_masked": _mask_phone(ex.phone)}
        elif my_name and len(my_name.split()) >= 3:       # (c) full-name match vs a legacy client
            exc = db.execute(text("""
                SELECT login, name, email, phone, reg_date FROM clients
                WHERE lower(regexp_replace(COALESCE(name,''),'\\s+',' ','g'))=:nm AND login IS NOT NULL
                ORDER BY login LIMIT 1
            """), {"nm": my_name}).fetchone()
            if exc:
                match_basis = "same full name"
                existing_account = {
                    "client_login": exc.login, "name": exc.name, "email": exc.email, "phone": exc.phone,
                    "login": exc.login, "created_at": str(exc.reg_date) if exc.reg_date else None,
                    "email_masked": _mask_email(exc.email), "phone_masked": _mask_phone(exc.phone)}
    except Exception as _ee:
        print(f"[kyc] exists-detection skipped for reg {registration_id}: {_ee}", flush=True)
    if existing_account:
        status = "exists"
        id_reuse = 1
        existing_account["match_basis"] = match_basis

    # only a duplicate ID is "strong" (it blocks). Family/address links are informational, NOT blocking.
    level = "strong" if id_reuse else ("family" if family else "none")
    network = {
        "dup_phone": int(dup_phone or 0), "dup_email": int(dup_email or 0),
        "family_code": fam_code, "family_code_matches": fam_matches,
        "id_number_reused": int(id_reuse), "level": level,
        "existing_account": existing_account,
        "family": family,
    }

    # ── PER-DOCUMENT completeness: the ID can be APPROVED while the proof of address is still
    # missing/rejected. In that case don't sit in vague "review" — approve the ID and tell the
    # client exactly what to upload next.
    present_sides = {d.side for d in docs}
    rejected_sides = {d.side for d in docs if (d.status or "") == "rejected"}
    id_dt = (id_doc.doc_type if id_doc else (docs[0].doc_type if docs else None))
    need_back = id_dt in ("national_id", "driving_license", "drivers_license")
    poa_ok = ("proof_of_address" in present_sides) and ("proof_of_address" not in rejected_sides)

    # ── PROOF-OF-ADDRESS holder check (household / spouse handling) ──
    # The address proof is frequently in a SPOUSE's or PARENT's name. In Arab regions a wife keeps
    # her own surname and the husband is NOT named on her ID, so we must NOT match by surname — the
    # household link is the shared FAMILY ID (family_code on the back of the national ID). Desk policy:
    # accept the bill if it's in the applicant's own name, OR a family member's ID is supplied whose
    # Family ID matches the applicant's. Otherwise the ID is still approved but we ask for the named
    # person's ID and flag the case MANUAL for the KYC team + sales to review / call / action.
    # GUARDED: POA OCR must never crash the verdict.
    poa_info = {}
    poa_family_ask = False
    poa_doc = next((d for d in docs if d.side == "proof_of_address"), None)
    if poa_doc and status == "verified" and "proof_of_address" not in rejected_sides:
        try:
            def _pn(s):
                return re.sub(r"\s+", " ", (s or "").strip().lower())
            # pass the applicant's ID names (Arabic) as handwriting hints so a hand-written residence
            # card reads e.g. the mother's name 'كافي' correctly instead of guessing a similar name.
            _known = [fields.get(k) for k in ("full_name", "father_name", "mother_name",
                      "mother_father_name", "grandfather_name", "surname")]
            pf = kyc_ai.extract_poa_fields(poa_doc.file_path, known_names=[k for k in _known if k]) or {}
            poa_hoh = (pf.get("head_of_household") or "").strip()
            poa_all = pf.get("all_names") or []
            # the representative name to test against the applicant: the addressee if present, else the
            # residence-card HEAD OF HOUSEHOLD, else the first name found. (A residence card often has
            # NO billed-to name — the relevant name is the head of household.)
            poa_name = (pf.get("holder_name") or "").strip() or poa_hoh or (poa_all[0] if poa_all else "")
            poa_info = {"holder_name": poa_name, "address": pf.get("address") or "",
                        "kind": pf.get("document_kind") or "",
                        "head_of_household": poa_hoh, "all_names": poa_all}
            if not poa_name and not poa_all:
                poa_info["verdict"] = "unreadable"   # genuinely no name on it — don't punish a blurry bill
            else:
                own = _name_match(entered_name, poa_name)
                if own is not True:
                    ai = kyc_ai.names_match(entered_name, [poa_name])
                    if ai is not None:
                        own = ai
                if own is True:
                    poa_info["verdict"] = "own_name"
                else:
                    # a DIFFERENT person is on the bill. We confirm the SAME HOUSEHOLD by identifying
                    # the relationship FROM THE DOCUMENTS WE ALREADY HAVE:
                    #  (a) the Arabic NAME CHAIN shows a father/child/sibling link (patronymic overlap), or
                    #  (b) the holder matches the MOTHER's / father's name printed on the applicant's OWN
                    #      ID (this is how we catch the mother, whose own chain doesn't overlap).
                    # Desk policy (Jun 2026): if we can IDENTIFY the relative, just APPROVE and keep a
                    # note — no extra upload, no address-match requirement (the relationship is already
                    # proven by the applicant's own documents). Only when we CANNOT identify the person
                    # (e.g. a spouse with no name link) do we ask for that person's ID to match the
                    # Family ID, shown as a separate "upload their ID" card under the green "ID approved".
                    relation = _name_chain_relation(entered_name, poa_name) or _stated_relative_match(poa_name, fields)
                    my_fid = (fields.get("family_code") or "").strip()
                    fam_fid = ""
                    fam_name = ""
                    fam_provided = False
                    for d in docs:
                        if d.side in ("family_id_back", "family_id_front", "family_id"):
                            fam_provided = True
                            fo = kyc_ai.extract_id_fields(d.file_path, "national_id") or {}
                            fam_fid = fam_fid or (fo.get("family_code") or "").strip()
                            fam_name = fam_name or (fo.get("full_name_latin") or fo.get("full_name") or "")
                    same_family = bool(my_fid and fam_fid and _pn(my_fid) == _pn(fam_fid))
                    # SPOUSE / FAMILY: a married couple keeps SEPARATE Family IDs (each stays on their own
                    # birth-family record), so the family_code often WON'T match between husband and wife.
                    # But if the applicant uploaded the POA holder's OWN national ID — i.e. the name on the
                    # uploaded ID matches the name on the proof of address — that possession IS the household
                    # proof: you don't hold a stranger's national ID. Accept it in that case too.
                    poa_id_provided = False
                    if fam_provided and poa_name and fam_name:
                        poa_id_provided = _name_match(poa_name, fam_name)
                        if not poa_id_provided:
                            try:
                                poa_id_provided = bool(kyc_ai.names_match(poa_name, [fam_name]))
                            except Exception:
                                poa_id_provided = False
                    poa_addr = _pn(pf.get("address"))
                    same_addr = bool(poa_addr and (poa_addr == _pn(reg.address) or poa_addr == _pn(fields.get("address"))))
                    poa_info.update({"relationship": relation or None, "family_id_provided": fam_provided,
                                     "family_id_match": same_family, "poa_holder_id_match": poa_id_provided,
                                     "address_match": same_addr,
                                     "family_member_name": fam_name, "applicant_family_code": my_fid,
                                     "family_member_family_code": fam_fid})
                    # If the cheap exact checks didn't identify the relative, ask the AI to REASON over
                    # the full ID context + every name on the document. This catches the hard real
                    # cases: a residence card whose name is the HEAD OF HOUSEHOLD, a MATERNAL relative
                    # (shares the mother's father's name), and handwriting/Arabic↔Latin transliteration.
                    judge = None
                    if not (same_family or relation or poa_id_provided):
                        judge = kyc_ai.poa_household_match(
                            {"full_name": fields.get("full_name"), "full_name_latin": fields.get("full_name_latin"),
                             "father": fields.get("father_name"), "grandfather": fields.get("grandfather_name"),
                             "mother": fields.get("mother_name"), "mother_father": fields.get("mother_father_name"),
                             "family_code": my_fid, "city": reg.city or fields.get("city")},
                            {"holder_name": poa_name, "head_of_household": pf.get("head_of_household"),
                             "all_names": pf.get("all_names") or [], "kind": pf.get("document_kind")})
                        if judge:
                            poa_info["ai_verdict"] = judge
                    ai_ok = bool(judge and judge.get("related") and judge.get("confidence") in ("high", "med"))
                    relword = {"parent": "father's", "mother": "mother's", "child": "child's",
                               "sibling": "sibling's"}.get(relation, "family member's")
                    if same_family or relation or ai_ok or poa_id_provided:
                        poa_info["verdict"] = "household_ok"   # accepted — family/household link established
                        if same_family:
                            poa_info["accept_basis"] = "family_id"
                            poa_info["note"] = (f"Proof of address is in a family member's name "
                                                f"({poa_name}) — confirmed by a matching Family ID.")
                        elif poa_id_provided:
                            poa_info["accept_basis"] = "poa_holder_id"
                            poa_info["note"] = (f"Proof of address is in {poa_name}'s name — confirmed by "
                                                "uploading THEIR national ID (spouse / family member). Note: "
                                                "spouses keep separate Family IDs, so the family codes differ.")
                        elif relation:
                            poa_info["accept_basis"] = "relationship:" + relation
                            poa_info["note"] = (f"Proof of address is in the applicant's {relword} name "
                                                f"({poa_name}) — accepted as a household member"
                                                + (" (address matches)" if same_addr else "") + ".")
                        else:
                            rel = (judge.get("relationship") or "family").replace("_", " ")
                            poa_info["relationship"] = judge.get("relationship")
                            poa_info["accept_basis"] = "ai_household"
                            poa_info["note"] = (f"Proof of address is in {poa_name}'s name — accepted as the "
                                                f"applicant's {rel}. {judge.get('reason','')}".strip())
                    else:
                        poa_info["verdict"] = "need_family_id"
                        poa_info["manual_review"] = True
                        poa_ok = False                         # not confirmed yet
                        poa_family_ask = True
        except Exception as e:
            poa_info = {"verdict": "error", "_error": str(e)[:200]}
    network["poa"] = poa_info

    missing = []
    if status == "verified":   # the ID itself passed — now check the rest of the documents
        if need_back and ("back" not in present_sides or "back" in rejected_sides):
            missing.append("the back side of your ID")
        if not poa_ok:
            if poa_family_ask:
                who = poa_info.get("holder_name") or "the person named on your proof of address"
                missing.append("the ID of " + who + " (we confirm family by the Family ID on the back of the card)")
            else:
                missing.append("a proof of address (utility bill / bank statement)")
        if missing:
            status = "docs_needed"

    # human-readable reason the client (and the desk) can read — explains the verdict in plain words
    if status == "verified":
        reason = "Your identity has been verified."
    elif status == "docs_needed":
        if poa_family_ask:
            who = poa_info.get("holder_name") or "another person"
            rel = poa_info.get("relationship")
            relword = {"parent": "your parent's", "mother": "your mother's", "child": "your child's",
                       "sibling": "your sibling's"}.get(rel)
            if relword:
                # we already inferred the relationship from the Arabic name chain — say so.
                reason = ("Your ID has been approved ✅. Your proof of address appears to be in " + relword
                          + " name (" + who + "). To confirm you live in the same household, please upload "
                          "THEIR ID — we match the Family ID on the back of the national ID card. "
                          "Our team will also review and may contact you.")
            else:
                reason = ("Your ID has been approved ✅. Your proof of address is in the name of "
                          + who + ". If this is your husband/wife, parent or a family member, please upload "
                          "THEIR ID — we confirm family by the Family ID on the back of the national ID "
                          "card. Our team will also review and may contact you.")
            others = [m for m in missing if "Family ID" not in m]
            if others:
                reason += " Please also upload " + " and ".join(others) + "."
        else:
            reason = "Your ID has been approved ✅. Please upload " + " and ".join(missing) + " to finish verifying your account."
    elif status == "exists":
        reason = "We already have an account registered with this ID. Please log in to your existing account instead of creating a new one."
    elif status == "rejected":
        if id_reuse:
            reason = "This ID document is already linked to an existing account. If this is you, please log in or contact support."
        elif fv == "mismatch":
            reason = "The selfie photo didn't match the photo on your ID. Please upload a clearer selfie and ID."
        elif expired is True:
            reason = "The document appears to be expired. Please upload a valid, in-date document."
        else:
            reason = "We couldn't verify your documents. Please upload clear, full-frame photos and try again."
    elif status == "review":
        reason = "Your documents are being reviewed manually by our team — no action needed, we'll update you shortly."
    else:   # pending
        reason = "Your documents are being processed."

    # persist
    db.execute(text("""
        UPDATE registrations SET ocr_fields=:f, face_score=:fs, face_verdict=:fvd,
            name_match=:nm, doc_expired=:exp, id_number=:idn, verify_status=:st, verify_reason=:rsn,
            network_json=:net, processed_at=NOW(), status=CASE WHEN :st='verified' THEN 'verified' ELSE status END
        WHERE id=:r
    """), {"f": json.dumps(fields), "fs": face.get("score"), "fvd": fv, "nm": nm,
           "exp": expired, "idn": id_number or None, "st": status, "rsn": reason, "net": json.dumps(network),
           "r": registration_id})

    db.execute(text("UPDATE registrations SET family_group=:fg WHERE id=:r"),
               {"fg": family.get("family_code"), "r": registration_id})

    # ── per-document status (so the profile + admin show each doc's outcome individually) ──
    id_doc_status = "approved" if status in ("verified", "docs_needed") else \
        ("rejected" if status in ("rejected", "exists") else "review")
    db.execute(text("UPDATE reg_kyc_documents SET status=:s WHERE registration_id=:r AND side IN ('front','main','back')"),
               {"s": id_doc_status, "r": registration_id})
    if status in ("verified", "docs_needed"):
        # the ID passed -> approve the proof of address, UNLESS it's in another person's name and we
        # still need the family member's ID to confirm the household (then it sits in manual review).
        poa_doc_status = "review" if poa_family_ask else "approved"
        db.execute(text("""UPDATE reg_kyc_documents SET status=:ps
            WHERE registration_id=:r AND side LIKE 'proof_of_address%' AND COALESCE(status,'') <> 'rejected'"""),
                   {"ps": poa_doc_status, "r": registration_id})

    if reg.lead_id:
        id_uploaded = any(s in present_sides for s in ("front", "main", "back"))
        id_verified = id_doc_status == "approved"
        poa_uploaded = any(s.startswith("proof_of_address") for s in present_sides)
        poa_verified = (poa_uploaded and status in ("verified", "docs_needed")
                        and "proof_of_address" not in rejected_sides and not poa_family_ask)
        db.execute(text("""UPDATE leads SET kyc_status=:k, kyc_id_uploaded=:iu, kyc_id_verified=:iv,
                           kyc_address_uploaded=:au, kyc_address_verified=:av WHERE id=:l"""),
                   {"k": status, "iu": id_uploaded, "iv": id_verified, "au": poa_uploaded,
                    "av": poa_verified, "l": reg.lead_id})
    # also reflect the result on the client's row so the CLIENT PORTAL shows the real status.
    # NB: a 'verified' verdict maps to 'pending_review' here ON PURPOSE — the green "approved" KPI
    # must NOT appear until the trading account actually exists. kyc_postverify.on_verified() (called
    # just below) provisions the account and flips clients.kyc_status='verified' atomically with it,
    # so the client never sees "approved" with no account / no docs (the old timing race).
    portal_kyc = {"verified": "pending_review", "review": "pending_review", "docs_needed": "docs_needed",
                  "rejected": "rejected", "exists": "exists", "pending": "pending_review"}.get(status, "pending_review")
    if reg.mt_login:
        db.execute(text("UPDATE clients SET kyc_status=:k WHERE login=:lg"),
                   {"k": portal_kyc, "lg": reg.mt_login})
        # Capture the date of birth from the ID OCR so the birthday bonus (birthday_engine.py) can fire
        # for this client. Additive — only set when clients.date_of_birth is empty.
        try:
            from birthday_engine import _parse_dob as _pdob
            _d = _pdob(fields.get("date_of_birth"))
            if _d:
                db.execute(text("UPDATE clients SET date_of_birth=:d WHERE login=:lg "
                                "AND (date_of_birth IS NULL OR date_of_birth='')"),
                           {"d": _d.isoformat(), "lg": reg.mt_login})
        except Exception:
            pass
    db.commit()

    # KYC just got APPROVED -> provision the trading account + convert the lead + notify
    # client / IB / sales (idempotent, simulated provisioning).
    if status == "verified":
        try:
            import kyc_postverify
            kyc_postverify.on_verified(db, registration_id)
        except Exception as e:
            print(f"[kyc] post-verify workflow failed for reg {registration_id}: {e}", flush=True)

    # ── EXISTING-ACCOUNT side-effects (run ONCE): tag the existing lead for sales + email the registrant ──
    if status == "exists" and existing_account:
        try:
            already = db.execute(text("SELECT COALESCE(dup_handled,FALSE) FROM registrations WHERE id=:r"),
                                 {"r": registration_id}).scalar()
        except Exception:
            already = False
        if not already:
            _handle_existing_account(db, registration_id, reg, existing_account)
            try:
                db.execute(text("UPDATE registrations SET dup_handled=TRUE WHERE id=:r"), {"r": registration_id})
                db.commit()
            except Exception:
                db.rollback()

    # email the client on a non-approval outcome, stating the reason
    if reg.email and status in ("rejected", "exists"):
        try:
            import email_send
            if email_send.configured():
                if status == "exists":
                    ea = existing_account or {}
                    subj, heading = "You already have a TNFX account", "You already have an account with us"
                    reg_to = " and ".join(x for x in [ea.get("email_masked"), ea.get("phone_masked")] if x)
                    reason = (f"Our records show you already have a TNFX account"
                              + (f" registered with {reg_to}" if reg_to else "") + ". "
                              "Please log in to your existing account at https://my1.tnfx.co instead of "
                              "creating a new one.")
                    sub = "If this wasn't you, please contact us at support@tnfx.co right away."
                else:
                    subj, heading = "Your TNFX verification needs attention", "We couldn't verify your documents"
                    sub = "Please log in and upload clear, valid documents to try again, or contact support if you need help."
                email_send.send(reg.email, subj, reason,
                                body_html=email_send.notice_html(heading, reason, sub))
        except Exception as e:
            print(f"[kyc] notify email failed for reg {registration_id}: {e}", flush=True)

    return {"ok": True, "registration_id": registration_id, "verify_status": status,
            "fields": fields, "face": face, "name_match": nm, "expired": expired,
            "network": network}
