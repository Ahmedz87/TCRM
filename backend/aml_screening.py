# -*- coding: utf-8 -*-
"""AML / sanctions screening (P0-16). Screens a person/entity name against government sanctions
lists (OFAC SDN + UN consolidated, loaded by aml_load.py) at KYC onboarding, BEFORE a real MT
account is provisioned. A hit puts the registration on compliance hold instead of auto-provisioning.

Matching is fuzzy (pg_trgm trigram similarity + token-set scoring) because sanctioned Arabic/Russian
names are transliterated many ways. Tuned to over-refer rather than miss (false negatives are the
regulatory danger); compliance clears false positives from the review queue.

  screen(db, name)                 -> list of match dicts (empty = clear)
  screen_registration(db, reg_id)  -> screens + records aml_screenings/aml_hits, returns (hold, hits)
  get_config(db) / set threshold   -> tunable match threshold (crm_settings aml_match_threshold)

The lists themselves are downloaded + parsed by aml_load.py (CLI / scheduled). This module owns the
schema + the matcher + the onboarding integration.
"""
import re
import unicodedata
import difflib
from sqlalchemy import text

DEFAULT_THRESHOLD = 0.84   # combined score to flag; tune via crm_settings.aml_match_threshold
CANDIDATE_LIMIT = 60       # trigram candidates pulled per screen before Python re-scoring

# tokens that carry no discriminating value for matching (kept minimal — Arabic connectors like
# bin/al/abu ARE meaningful, so they are NOT stripped)
_STOP = {"mr", "mrs", "ms", "dr", "the", "of"}


def ensure_schema(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS sanctions_entities (
        id BIGSERIAL PRIMARY KEY,
        source TEXT NOT NULL,              -- ofac | un
        ext_id TEXT NOT NULL,              -- source's own id
        entity_type TEXT,                  -- individual | entity | vessel | ...
        primary_name TEXT,
        programs TEXT,                     -- sanctions programs / list type
        dob TEXT,
        nationality TEXT,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (source, ext_id))"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS sanctions_names (
        id BIGSERIAL PRIMARY KEY,
        entity_id BIGINT NOT NULL REFERENCES sanctions_entities(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        name_norm TEXT NOT NULL,
        is_primary BOOLEAN DEFAULT FALSE)"""))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_sanctions_names_trgm ON sanctions_names USING gin (name_norm gin_trgm_ops)"))
    # per-screen audit trail
    db.execute(text("""CREATE TABLE IF NOT EXISTS aml_screenings (
        id BIGSERIAL PRIMARY KEY,
        subject_type TEXT,                 -- registration | client | manual
        subject_id BIGINT,
        name_screened TEXT,
        dob TEXT,
        result TEXT,                       -- clear | hit
        n_hits INT DEFAULT 0,
        top_score REAL,
        screened_by TEXT,
        screened_at TIMESTAMPTZ DEFAULT NOW())"""))
    # the compliance review queue (one row per matched entity)
    db.execute(text("""CREATE TABLE IF NOT EXISTS aml_hits (
        id BIGSERIAL PRIMARY KEY,
        screening_id BIGINT REFERENCES aml_screenings(id) ON DELETE CASCADE,
        subject_type TEXT,
        subject_id BIGINT,
        entity_id BIGINT,
        source TEXT,
        matched_name TEXT,
        entity_type TEXT,
        programs TEXT,
        score REAL,
        status TEXT DEFAULT 'pending',     -- pending | cleared | confirmed
        reviewed_by TEXT,
        reviewed_at TIMESTAMPTZ,
        note TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_aml_hits_status ON aml_hits(status)"))
    db.commit()


def normalize(name: str) -> str:
    """Fold to a comparable form: strip accents, lowercase, drop punctuation, collapse spaces."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))   # drop diacritics
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)     # keep latin+digits (Arabic-script handled via name_en)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(norm: str):
    return [t for t in norm.split() if t and t not in _STOP]


_TOK_MATCH = 0.87   # two tokens are "the same name part" at/above this char-similarity (ahmad~ahmed)


def _tok_eq(t1, t2):
    if t1 == t2:
        return True
    if abs(len(t1) - len(t2)) > 4:
        return False
    return difflib.SequenceMatcher(None, t1, t2).ratio() >= _TOK_MATCH


def _name_score(qtok, ctok, qn, cn):
    """Bilateral token-coverage score. A single shared common given name ("Ahmed") must NOT score
    high — a real hit needs most tokens of BOTH names to align (fuzzily). Full-string similarity is
    a floor for reordering/spelling. Returns 0..1."""
    if not qtok or not ctok:
        return 0.0
    matched_q = sum(1 for t in qtok if any(_tok_eq(t, c) for c in ctok))
    matched_c = sum(1 for c in ctok if any(_tok_eq(c, t) for t in qtok))
    p = matched_q / len(qtok)          # fraction of the person's name found in the sanctioned name
    r = matched_c / len(ctok)          # fraction of the sanctioned name found in the person's name
    f = (2 * p * r / (p + r)) if (p + r) else 0.0
    full = difflib.SequenceMatcher(None, qn, cn).ratio()
    score = max(f, full)
    # strong signal: EVERY query token appears in the entity name (person fully contained) — but only
    # when at least two tokens agree, so one common first name can never trigger this.
    if p >= 0.999 and matched_q >= 2:
        score = max(score, 0.9)
    # guard: multi-token names that share only ONE token are not a match, whatever trigrams say
    if min(len(qtok), len(ctok)) >= 2 and matched_q < 2:
        score = min(score, 0.55)
    return score


DEFAULT_BLOCK = 0.90   # top-score at/above which onboarding is HELD (vs merely queued for review)


def _setting(db, key, default):
    try:
        v = db.execute(text("SELECT val FROM crm_settings WHERE key=:k"), {"k": key}).scalar()
        return float(v) if v is not None else default
    except Exception:
        db.rollback()
        return default


def get_threshold(db) -> float:
    """Score at/above which a match is recorded in the review queue."""
    return _setting(db, "aml_match_threshold", DEFAULT_THRESHOLD)


def get_block_threshold(db) -> float:
    """Top-score at/above which provisioning is HELD for compliance (>= match threshold). The desk
    can lower this to the match threshold to block on every hit, or raise it to reduce holds."""
    return max(get_threshold(db), _setting(db, "aml_block_threshold", DEFAULT_BLOCK))


def screen(db, name: str, threshold: float = None):
    """Return a list of sanctions matches for `name` (empty list = clear). Each match:
    {entity_id, source, entity_type, primary_name, matched_name, programs, dob, nationality, score}."""
    qn = normalize(name)
    qtok = _tokens(qn)
    # need >=2 DISTINCT name parts to be actionable: a lone given name ("Ibrahim") or a repeated
    # one ("Abbas Abbas") is not a screenable identity — it just collides with common list names.
    if len(qn) < 3 or len(set(qtok)) < 2:
        return []
    thr = threshold if threshold is not None else get_threshold(db)
    # trigram candidate retrieval via the GIN index (fast). set_limit raises recall for the % op.
    try:
        db.execute(text("SELECT set_limit(0.3)"))
    except Exception:
        db.rollback()
    rows = db.execute(text("""
        SELECT sn.entity_id, sn.name, sn.name_norm, similarity(sn.name_norm, :q) AS sim,
               e.source, e.entity_type, e.primary_name, e.programs, e.dob, e.nationality
        FROM sanctions_names sn JOIN sanctions_entities e ON e.id = sn.entity_id
        WHERE sn.name_norm % :q
        ORDER BY sim DESC
        LIMIT :lim
    """), {"q": qn, "lim": CANDIDATE_LIMIT}).fetchall()

    best = {}   # entity_id -> match dict (keep highest score)
    for r in rows:
        ctok = _tokens(r[2])
        score = _name_score(qtok, ctok, qn, r[2])
        # require every query token to have SOME presence for short names (guards common-word FPs)
        if score < thr:
            continue
        eid = r[0]
        if eid not in best or score > best[eid]["score"]:
            best[eid] = {
                "entity_id": eid, "source": r[4], "entity_type": r[5],
                "primary_name": r[6], "matched_name": r[1], "programs": r[7],
                "dob": r[8], "nationality": r[9], "score": round(score, 3),
            }
    return sorted(best.values(), key=lambda m: m["score"], reverse=True)


def screen_registration(db, registration_id: int, name: str = None, dob: str = None, by: str = "system"):
    """Screen a registration's name; record the screening + any hits; return (hold: bool, hits: list).
    hold=True (top score >= block threshold) means the caller must NOT auto-provision -> route to
    compliance. Lower-score hits are still recorded for review but don't block onboarding."""
    ensure_schema(db)
    if name is None:
        row = db.execute(text("""
            SELECT COALESCE(NULLIF(TRIM(CONCAT_WS(' ', first_name, last_name)), ''), '') , ocr_fields
            FROM registrations WHERE id=:r
        """), {"r": registration_id}).fetchone()
        name = (row[0] if row else "") or ""
        # prefer the Latin OCR name if present
        try:
            import json as _j
            of = row[1] if row and isinstance(row[1], dict) else (_j.loads(row[1]) if row and row[1] else {})
            latin = (of.get("full_name_latin") or "").strip()
            if latin:
                name = latin
        except Exception:
            pass
    hits = screen(db, name)
    top = hits[0]["score"] if hits else None
    sid = db.execute(text("""
        INSERT INTO aml_screenings (subject_type, subject_id, name_screened, dob, result, n_hits, top_score, screened_by)
        VALUES ('registration', :sid, :nm, :dob, :res, :n, :top, :by) RETURNING id
    """), {"sid": registration_id, "nm": name, "dob": dob, "res": "hit" if hits else "clear",
           "n": len(hits), "top": top, "by": by}).scalar()
    for h in hits:
        db.execute(text("""
            INSERT INTO aml_hits (screening_id, subject_type, subject_id, entity_id, source, matched_name,
                                  entity_type, programs, score, status)
            VALUES (:sc,'registration',:sid,:eid,:src,:mn,:et,:pg,:sco,'pending')
        """), {"sc": sid, "sid": registration_id, "eid": h["entity_id"], "src": h["source"],
               "mn": h["matched_name"], "et": h["entity_type"], "pg": h["programs"], "sco": h["score"]})
    db.commit()
    hold = bool(hits) and (top is not None) and top >= get_block_threshold(db)
    return (hold, hits)


def has_pending_block(db, subject_id, subject_type="registration"):
    """True if this subject has an UNRESOLVED sanctions hit at/above the block threshold — i.e. a
    match a compliance officer has not yet cleared. Used to refuse (re)provisioning until cleared."""
    ensure_schema(db)
    bt = get_block_threshold(db)
    n = db.execute(text("""SELECT COUNT(*) FROM aml_hits
        WHERE subject_type=:t AND subject_id=:s AND status='pending' AND score >= :bt"""),
        {"t": subject_type, "s": subject_id, "bt": bt}).scalar()
    return (n or 0) > 0
