"""
kyc_ai.py — read KYC ID documents with Claude vision and return structured fields.

The model is ONE config line (KYC_MODEL). The API key is read from ai_key.txt (NOT .env —
database.py's pydantic Settings forbids extra .env keys and would crash the backend; same
baked-credential pattern the Yeastar/Meta integrations use).

If no key is present yet, extract_id_fields() returns {"_status": "pending_no_key"} so the rest
of the KYC pipeline (face-match, network cross-check) still runs — the Claude half just stays
'pending' until you drop the key in ai_key.txt.
"""
import os
import json
import base64

# verification accuracy matters (gates funding) -> Opus 4.8. Swap to claude-sonnet-4-6 /
# claude-haiku-4-5 to trade accuracy for cost. Same code, same key.
KYC_MODEL = "claude-opus-4-8"

_KEY_FILE = os.path.join(os.path.dirname(__file__), "ai_key.txt")
_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
          ".webp": "image/webp", ".gif": "image/gif"}

# structured output schema — what we pull off an ID (Iraqi national IDs carry the family fields)
ID_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "full_name_ar": {"type": "string"},
        "full_name_latin": {"type": "string"},
        "first_name": {"type": "string"},
        "father_name": {"type": "string"},
        "grandfather_name": {"type": "string"},
        "surname": {"type": "string"},
        "mother_name": {"type": "string"},
        "mother_father_name": {"type": "string"},
        "date_of_birth": {"type": "string"},
        "id_number": {"type": "string"},
        "expiry_date": {"type": "string"},
        "issue_date": {"type": "string"},
        "place_of_birth": {"type": "string"},
        "city": {"type": "string"},
        "family_code": {"type": "string"},
        "gender": {"type": "string"},
        "nationality": {"type": "string"},
        "document_type": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["full_name"],
    "additionalProperties": False,
}

_PROMPT = (
    "This is a {doc} (often an Iraqi document with Arabic + English text). Extract every "
    "identity field you can read. For Iraqi national IDs include the mother's name, the "
    "mother's father name, the father's name, grandfather's name, surname/family name, city, "
    "and the family/record code if visible. Use ISO dates (YYYY-MM-DD) where possible. "
    "Read both the Arabic and the English/Latin text.\n\n"
    "full_name_latin: the person's full name in LATIN/English letters. If the name is printed in "
    "Latin on the document, copy it. If the name is ONLY in Arabic, provide your best standard "
    "transliteration of the Arabic name into Latin letters — transliteration is REQUIRED here and "
    "is NOT considered fabrication (it is a faithful romanization of the visible Arabic name).\n\n"
    "CRITICAL ACCURACY RULES — NEVER fabricate data:\n"
    "- Return an EMPTY STRING for any field that is not clearly visible on the document. "
    "NEVER guess, invent, transcribe a partial, or generate a placeholder value.\n"
    "- id_number: if the document does NOT show a visible ID / serial / document / record "
    "number, return an EMPTY STRING for id_number. Do NOT invent one, do NOT reuse another "
    "number on the card, do NOT output a placeholder.\n"
    "- date_of_birth, expiry_date, issue_date and any other numeric/date field: return an "
    "EMPTY STRING if it is not actually printed on the document. Never approximate or guess.\n"
    "Return only the structured fields."
)


def _api_key():
    try:
        with open(_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None


def available():
    return bool(_api_key())


# Max decoded image size (bytes). Reject anything larger so a huge upload can't be
# decoded into memory or sent to the model. ~7 MB (Ticket #25 cap).
MAX_IMAGE_BYTES = 7 * 1024 * 1024


def _sniff_media(b):
    """Detect image type from magic bytes; returns an Anthropic-supported media type or None."""
    if len(b) < 12:
        return None
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


def _build_prompt(doc_type):
    return _PROMPT.format(doc=doc_type.replace("_", " ")) + \
        "\n\nThe photo may be rotated, sideways, upside-down, landscape OR portrait — mentally " \
        "rotate it as needed and read every field correctly regardless of orientation.\n" \
        "\nReturn ONLY a single JSON object (no prose, no markdown) with these exact keys. " \
        "Use an EMPTY STRING for ANY field not clearly present on the document — never invent, " \
        "guess, or use a placeholder (especially for id_number and dates):\n" + \
        ", ".join(ID_SCHEMA["properties"].keys())


def _extract_json(raw):
    """Robustly pull a JSON object out of the model's reply. Handles: markdown ```json fences,
    leading/trailing prose, and stray text — by isolating the first '{' … matching last '}'.
    Returns a dict, or None if nothing parses. This is what stops a perfectly-good OCR from
    being thrown away as a 'parse_error' just because the model added a sentence around the JSON.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    # strip a ```json … ``` (or ``` … ```) fence if present
    if "```" in raw:
        import re as _re
        m = _re.search(r"```(?:json)?\s*(.*?)```", raw, _re.DOTALL | _re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
    # 1) try as-is
    try:
        return json.loads(raw)
    except Exception:
        pass
    # 2) isolate the outermost { … } and try that
    i, j = raw.find("{"), raw.rfind("}")
    if i != -1 and j != -1 and j > i:
        try:
            return json.loads(raw[i:j + 1])
        except Exception:
            pass
    return None


def _call_vision(key, model, media, b64, doc_type):
    """Shared Claude-vision call + defensive JSON parse. Never raises; PII is never logged.
    Retries transient API errors (529 overloaded / 429 rate-limit / 5xx) so a momentary Anthropic
    overload doesn't leave a KYC stuck on 'pending' forever."""
    import time
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
        {"type": "text", "text": _build_prompt(doc_type)},
    ]
    msg = None
    for attempt in range(4):
        try:
            msg = client.messages.create(
                model=model, max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            break
        except Exception as e:
            s = str(e).lower()
            transient = any(t in s for t in ("529", "overloaded", "429", "rate", "500", "502", "503", "timeout", "timed out"))
            if transient and attempt < 3:
                time.sleep(2 * (attempt + 1))   # 2s, 4s, 6s backoff
                continue
            raise
    if msg is None:
        return {"_status": "error", "_error": "no response after retries"}
    raw = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "{}")
    data = _extract_json(raw)
    if data is None:
        data = {"_status": "parse_error"}           # NB: do NOT echo raw PII back
    if isinstance(data, dict):
        data["_model"] = model
        # never let the model smuggle in a status/flag that would mark this as simulated
        data.pop("_simulated", None)
    else:
        data = {"_status": "parse_error"}
    return data


def names_match(entered, doc_names):
    """AI judge: does the registered name match the name(s) on the ID? Allows Arabic<->English
    transliteration and common spelling variants (Ameer/Amir, Mohamed/Muhammad, Hashim/Hashimi,
    Abdul/Abd al), and a short first+last form of a longer full name. Returns True / False / None
    (None = couldn't decide / no key). Cheap text-only call. Never raises."""
    key = _api_key()
    if not key:
        return None
    cands = [str(c).strip() for c in (doc_names or []) if c and str(c).strip()]
    entered = (entered or "").strip()
    if not entered or not cands:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        prompt = (
            f"A person registered with the name: '{entered}'.\n"
            f"Their ID document shows the name(s): {' | '.join(cands)}.\n"
            "Do these PLAUSIBLY refer to the same person? Be reasonably LENIENT — clients type their "
            "name in many ways:\n"
            "• Allow Arabic<->English transliteration and spelling variants (Ameer/Amir, Mohamed/"
            "Muhammad, Narmeen/Narmin, Hashim/Hashimi, Abdul/Abd al).\n"
            "• The registered name may be a SHORTER or partial form, in a different order, missing the "
            "father/grandfather/family names, or contain extra/placeholder words NOT on the document.\n"
            "Answer YES if the person's GIVEN (first) name clearly matches the document AND nothing "
            "directly contradicts it. Answer NO ONLY if the core given names clearly belong to "
            "DIFFERENT people (e.g. registered 'Ali' but the document says 'Mohammed').\n"
            "Answer with ONLY one word: YES or NO."
        )
        msg = client.messages.create(model=KYC_MODEL, max_tokens=5,
                                     messages=[{"role": "user", "content": prompt}])
        txt = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "").strip().upper()
        if "YES" in txt:
            return True
        if "NO" in txt:
            return False
        return None
    except Exception:
        return None


def extract_poa_fields(image_path, known_names=None):
    """Read a PROOF-OF-ADDRESS document (utility bill / bank statement / residence card) FROM DISK
    and return {holder_name, head_of_household, all_names, address, document_kind}. `known_names` is
    an optional list of the applicant's family names (from their ID) used ONLY to disambiguate unclear
    HANDWRITING — many Iraqi residence cards are hand-written, so a hint of the expected names lets the
    model read e.g. 'كافي/Kafi' correctly instead of guessing 'Kamil'. Never raises."""
    key = _api_key()
    if not key:
        return {"_status": "pending_no_key"}
    if not image_path or not os.path.exists(image_path):
        return {"_status": "no_file"}
    try:
        import time
        import anthropic
        ext = os.path.splitext(image_path)[1].lower()
        media = _MEDIA.get(ext, "image/jpeg")
        with open(image_path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode()
        prompt = (
            "This image is a PROOF OF ADDRESS. It may be a utility bill, a bank statement, a tenancy "
            "contract, OR an Iraqi RESIDENCE / HOUSING CARD (بطاقة السكن / بطاقة معلومات السكن — a card, "
            "often handwritten in Arabic, that may carry a photo of the holder and the name of the HEAD "
            "OF HOUSEHOLD 'اسم رب الأسرة'). The photo may be rotated/sideways — mentally rotate it. Read "
            "EVERY person's name on it. Transliterate Arabic names to Latin/English letters. Return ONLY "
            "a single JSON object (no prose, no markdown) with EXACTLY these keys:\n"
            "  holder_name: the name of the PERSON the document primarily belongs to / is addressed to. "
            "On a residence card with a photo, this is the card holder (the person pictured). Empty if none.\n"
            "  head_of_household: on a residence card, the 'رب الأسرة / head of household' name. Empty if none.\n"
            "  all_names: a JSON array of EVERY distinct person name visible anywhere on the document "
            "(holder, head of household, any other names), each transliterated to Latin. [] if none.\n"
            "  address: the full address shown on the document. Empty string if none.\n"
            "  document_kind: a short label e.g. 'electricity bill', 'bank statement', 'residence card'.\n"
            "Use an EMPTY STRING / empty array for anything not clearly present — never invent or guess."
        )
        hints = [str(n).strip() for n in (known_names or []) if str(n).strip()]
        if hints:
            prompt += (
                "\n\nHANDWRITING AID: this document may be HAND-WRITTEN in Arabic, and it likely belongs "
                "to the applicant or a family member. The applicant's national ID lists these names: "
                + " ، ".join(hints) + ". If an unclear handwritten name closely resembles one of these, "
                "read it AS that name (e.g. don't misread 'كافي/Kafi' as 'Kamil'). But never force a "
                "match — if the handwriting clearly shows a different name, report what is actually written."
            )
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
            {"type": "text", "text": prompt},
        ]
        client = anthropic.Anthropic(api_key=key)
        msg = None
        for attempt in range(4):
            try:
                msg = client.messages.create(model=KYC_MODEL, max_tokens=512,
                                             messages=[{"role": "user", "content": content}])
                break
            except Exception as e:
                s = str(e).lower()
                if any(t in s for t in ("529", "overloaded", "429", "rate", "500", "502", "503", "timeout", "timed out")) and attempt < 3:
                    time.sleep(2 * (attempt + 1)); continue
                raise
        if msg is None:
            return {"_status": "error", "_error": "no response after retries"}
        raw = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "{}")
        data = _extract_json(raw)
        if not isinstance(data, dict):
            return {"_status": "parse_error"}
        names = data.get("all_names")
        names = [str(n).strip() for n in names if str(n).strip()] if isinstance(names, list) else []
        return {"holder_name": (data.get("holder_name") or "").strip(),
                "head_of_household": (data.get("head_of_household") or "").strip(),
                "all_names": names,
                "address": (data.get("address") or "").strip(),
                "document_kind": (data.get("document_kind") or "").strip()}
    except Exception as e:
        return {"_status": "error", "_error": str(e)[:300]}


def poa_household_match(applicant, poa):
    """AI judge: does this PROOF OF ADDRESS belong to the applicant, or to a member of their immediate
    FAMILY / HOUSEHOLD? Real proofs of address are often in a relative's name — a parent, sibling, the
    head of household on an Iraqi residence card, or a MATERNAL relative (a woman keeps her own name,
    so her father's name appears in her brothers' names). Exact string matching can't see these links,
    especially with handwriting + Arabic↔Latin transliteration. This call reasons over the full ID
    context instead.
      applicant = {full_name, full_name_latin, father, grandfather, mother, mother_father, family_code, city}
      poa       = {holder_name, head_of_household, all_names(list), kind}
    Returns {"related": bool, "relationship": str, "confidence": "high|med|low", "reason": str} or None
    (None = couldn't decide / no key). Never raises."""
    key = _api_key()
    if not key:
        return None
    try:
        import json as _json
        import anthropic
        names = poa.get("all_names") or []
        if poa.get("holder_name") and poa["holder_name"] not in names:
            names = [poa["holder_name"]] + names
        if poa.get("head_of_household") and poa["head_of_household"] not in names:
            names = names + [poa["head_of_household"]]
        prompt = (
            "You verify proof-of-address documents for an Iraqi forex broker. Decide whether a proof of "
            "address belongs to the APPLICANT or to a member of their IMMEDIATE FAMILY / SAME HOUSEHOLD.\n\n"
            "APPLICANT (from their national ID):\n"
            f"  name: {applicant.get('full_name_latin') or applicant.get('full_name','')}\n"
            f"  father's name: {applicant.get('father','')}\n"
            f"  grandfather's name: {applicant.get('grandfather','')}\n"
            f"  mother's name: {applicant.get('mother','')}\n"
            f"  mother's father's name: {applicant.get('mother_father','')}\n"
            f"  family record no.: {applicant.get('family_code','')}\n"
            f"  city: {applicant.get('city','')}\n\n"
            "PROOF OF ADDRESS:\n"
            f"  document type: {poa.get('kind','')}\n"
            f"  name(s) found on it: {' | '.join(names) if names else '(none read)'}\n\n"
            "Use Arabic naming rules: names are [given, father, grandfather, ...]; siblings share the "
            "chain from the 2nd name; a MOTHER keeps her own chain so her FATHER's name appears in her "
            "brothers' names (a name 'X <mother's-father>' is likely the applicant's maternal uncle); a "
            "residence card's head-of-household is usually the applicant's father, grandfather or an "
            "uncle. Allow Arabic↔English transliteration and handwriting variance. Be reasonably "
            "lenient for a CLEAR family/household link, but answer related=false if the names show no "
            "plausible family connection.\n"
            "Answer with ONLY one JSON object: {\"related\": true/false, \"relationship\": "
            "\"self|father|mother|sibling|grandparent|maternal_uncle|paternal_uncle|household|other\", "
            "\"confidence\": \"high|med|low\", \"reason\": \"one short sentence\"}"
        )
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=KYC_MODEL, max_tokens=200,
                                     messages=[{"role": "user", "content": prompt}])
        txt = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "{}")
        data = _extract_json(txt)
        if not isinstance(data, dict) or "related" not in data:
            return None
        return {"related": bool(data.get("related")),
                "relationship": (data.get("relationship") or "other").strip(),
                "confidence": (data.get("confidence") or "low").strip().lower(),
                "reason": (data.get("reason") or "").strip()}
    except Exception:
        return None


def extract_id_fields(image_path, doc_type="national_id"):
    """Read one ID image FROM DISK -> dict of fields. Never raises; returns a status on failure."""
    key = _api_key()
    if not key:
        return {"_status": "pending_no_key"}
    if not image_path or not os.path.exists(image_path):
        return {"_status": "no_file"}
    try:
        ext = os.path.splitext(image_path)[1].lower()
        media = _MEDIA.get(ext, "image/jpeg")
        with open(image_path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode()
        return _call_vision(key, KYC_MODEL, media, b64, doc_type)
    except Exception as e:
        return {"_status": "error", "_error": str(e)[:300]}


def extract_id_fields_from_b64(image_b64, doc_type="national_id", model=None):
    """Read one ID image FROM RAW (base64) BYTES -> dict of fields (Ticket #25 portal upload path).

    - Strips any `data:image/...;base64,` prefix.
    - Caps the DECODED size at MAX_IMAGE_BYTES (rejects oversized uploads).
    - Uses `model` (defaults to ai_config.CHAT_MODEL — a vision model) so the portal reuses the
      same key/model as the chat bot.
    - NEVER fabricates: the strict prompt makes the model return "" for unreadable fields; the
      caller treats "" / missing id_number as NULL.
    Never raises; never logs the image bytes or extracted PII.
    """
    key = _api_key()
    if not key:
        # fall back to the chat-bot key so the portal can OCR even if ai_key.txt is empty
        try:
            import ai_config
            if ai_config.is_configured():
                key = ai_config.ANTHROPIC_API_KEY
        except Exception:
            key = None
    if not key:
        return {"_status": "pending_no_key"}
    if not image_b64 or not isinstance(image_b64, str):
        return {"_status": "no_file"}

    s = image_b64.strip()
    media = "image/jpeg"
    if s.startswith("data:"):
        # data:image/png;base64,AAAA...
        try:
            header, s = s.split(",", 1)
            mt = header[5:].split(";", 1)[0].strip()
            if mt:
                media = mt
        except Exception:
            return {"_status": "bad_data_uri"}
    s = "".join(s.split())  # drop any whitespace/newlines in the b64 payload

    try:
        raw_bytes = base64.b64decode(s, validate=False)
    except Exception:
        return {"_status": "bad_base64"}
    if not raw_bytes:
        return {"_status": "no_file"}
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        return {"_status": "too_large", "_limit_mb": round(MAX_IMAGE_BYTES / (1024 * 1024), 1)}

    # Trust the ACTUAL bytes over the declared media type (sniff magic numbers) so the
    # Anthropic API never rejects a mislabeled image.
    sniffed = _sniff_media(raw_bytes)
    if sniffed:
        media = sniffed
    elif media not in _MEDIA.values():
        media = "image/jpeg"  # normalise unknown declared types

    # re-encode cleanly so the wire payload is exactly the validated bytes
    clean_b64 = base64.standard_b64encode(raw_bytes).decode()

    if model is None:
        try:
            import ai_config
            model = ai_config.CHAT_MODEL
        except Exception:
            model = KYC_MODEL
    try:
        return _call_vision(key, model, media, clean_b64, doc_type)
    except Exception as e:
        return {"_status": "error", "_error": str(e)[:300]}
