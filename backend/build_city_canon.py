"""
build_city_canon.py — unify the free-text CITY field.

Clients/leads type their city by hand (no drop-down), so the same place arrives as Erbil/Arbil/Irbil,
Baghdad/Bagdad/بغداد, Basra/Basrah/Basraa/AL Bashra… 10.8k distinct spellings over ~96k rows. That
makes "same city" useless as a connection signal. This job writes a CANONICAL city
(clients.city_canon / leads.city_canon) while KEEPING the raw user-typed `city` untouched.

How it maps (deliberately conservative — a wrong merge is worse than no merge):
  1. normalise: lowercase, strip Latin diacritics (ad dīwānīyah -> ad diwaniyah), drop punctuation/
     digits, drop a leading 'iraq ', drop 'al '/'el ' prefixes, drop trailing city/governorate/
     province/district/muhafazah noise, collapse spaces.
  2. exact alias lookup against the gazetteer below (includes Arabic-script forms).
  3. TIGHT guarded fuzzy (>= FUZZY_MIN similarity) for anything left, with:
       - a CONFUSABLE guard so Irbid (Jordan) never becomes Erbil (Iraq), Basra != Basrah-adjacent
         foreign names, etc.
       - ambiguity rejection: if two canonicals tie within 0.02, we refuse to guess.
  4. anything still unmatched keeps its normalised form (no forced merge).
COUNTRIES typed into the city box (iraq, syria, saudi arabia…) map to '' = unknown, so they can never
act as a "same city" link.

Run:  python build_city_canon.py            (report only)
      python build_city_canon.py --commit   (writes city_canon)
"""
import sys, re, unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
import db_config

FUZZY_MIN = 0.88

# ── canonical -> aliases (normalised forms are matched; add raw variants freely) ────────────────
# Iraq: the 18 governorates and their principal cities are folded together (the desk uses e.g.
# Hillah/Babil, Nasiriyah/Dhi Qar interchangeably), so one place = one canonical.
CANON = {
    "Baghdad":      ["baghdad", "bagdad", "bghdad", "baghded", "baghdaad", "bagdhad", "baghdadi",
                     "new baghdad", "baghdada", "bagdade", "bagdead", "baghdad university",
                     "abu ghraib", "abu ghraib district", "sadr city", "kadhimiya", "karkh", "rusafa",
                     "بغداد", "مدينة بغداد", "بغداد الجديدة"],
    "Basra":        ["basra", "basrah", "basraa", "bashra", "basra city", "albasra", "albasrah",
                     "al basrah al qadimah", "basrah al qadimah", "basara", "basrra", "basrah city",
                     "البصرة", "بصرة"],
    "Erbil":        ["erbil", "arbil", "irbil", "erbile", "arbill", "arbili", "hawler", "hewler",
                     "erbil city", "irbil kurdistan", "erbil kurdistan", "أربيل", "اربيل"],
    "Sulaymaniyah": ["sulaymaniyah", "sulaimani", "sulaimania", "slemani", "sulaymaniya",
                     "sulaimaniyah", "as sulaymaniyah", "السليمانية", "سليمانية"],
    "Duhok":        ["duhok", "dohuk", "duhoke", "duhuk", "dahuk", "dihok", "زاخو", "دهوك", "zakho"],
    "Kirkuk":       ["kirkuk", "karkuk", "kerkuk", "kirkouk", "كركوك"],
    "Mosul":        ["mosul", "nineveh", "ninawa", "ninevah", "mousl", "mousul", "musil", "al mawsil",
                     "الموصل", "نينوى"],
    "Najaf":        ["najaf", "alnajaf", "al najaf", "najaf ashraf", "alnajaf alashraf", "annajaf",
                     "النجف", "نجف"],
    "Karbala":      ["karbala", "karbalaa", "kerbala", "karballa", "karbalah", "kerbalaa", "kerbela",
                     "كربلاء", "كربلا"],
    "Babil":        ["babil", "babylon", "hillah", "al hillah", "alhillah", "hilla", "musayyib",
                     "al musayyib", "babel", "بابل", "الحلة"],
    "Diyala":       ["diyala", "baqubah", "baquba", "baqouba", "diala", "ديالى", "بعقوبة"],
    "Anbar":        ["anbar", "alanbar", "al anbar", "ramadi", "ar ramadi", "fallujah", "al fallujah",
                     "falluja", "hit", "haditha", "الأنبار", "الانبار", "الرمادي", "الفلوجة"],
    "Wasit":        ["wasit", "kut", "al kut", "alkut", "واسط", "الكوت"],
    "Maysan":       ["maysan", "amarah", "al amarah", "amara", "missan", "misan", "ميسان", "العمارة"],
    "Dhi Qar":      ["dhi qar", "dhiqar", "thiqar", "thi qar", "nasiriyah", "an nasiriyah",
                     "nasiriya", "nassiriya", "ذي قار", "الناصرية"],
    "Muthanna":     ["muthanna", "almuthanna", "al muthanna", "samawah", "as samawah", "المثنى",
                     "السماوة"],
    "Qadisiyah":    ["qadisiyah", "alqadisiyah", "al qadisiyah", "diwaniyah", "ad diwaniyah",
                     "diwaniya", "القادسية", "الديوانية"],
    "Saladin":      ["saladin", "salahaddin", "salah al din", "salah aldin", "salahuddin", "tikrit",
                     "samarra", "balad", "صلاح الدين", "تكريت", "سامراء"],
    "Halabja":      ["halabja", "حلبجة"],
    # ── common foreign cities typed by expat clients (kept distinct; Irbid guarded vs Erbil) ──
    "Irbid":        ["irbid", "اربد"],
    "Amman":        ["amman", "عمان"],
    "Damascus":     ["damascus", "dimashq", "دمشق"],
    "Aleppo":       ["aleppo", "halab", "حلب"],
    "Homs":         ["homs", "حمص"],
    "Latakia":      ["latakia", "lattakia", "اللاذقية"],
    "Dubai":        ["dubai", "دبي"],
    "Istanbul":     ["istanbul", "استانبول", "اسطنبول"],
    "Cairo":        ["cairo", "القاهرة"],
    "Gaza":         ["gaza", "غزة"],
}

# Values that are COUNTRIES/regions, not cities -> unknown ('') so they never link two people.
NOT_A_CITY = {"iraq", "syria", "india", "saudi arabia", "ksa", "turkey", "jordan", "iran", "egypt",
              "uae", "kuwait", "lebanon", "yemen", "palestine", "germany", "usa", "uk", "kurdistan",
              "العراق", "سوريا", "الاردن", "ايران", "تركيا", "كردستان", "none", "null", "n a", "na",
              "unknown", "test", "city"}

# Never let fuzzy collapse these into each other (real, different places that look alike).
CONFUSABLE = [{"Erbil", "Irbid"}, {"Basra", "Bursa"}, {"Amman", "Oman"}, {"Halabja", "Aleppo"}]

_DIAC = re.compile(r"[̀-ͯ]")
_NOISE = re.compile(r"\b(city|governorate|province|district|muhafazah|prov|gov|centre|center|"
                    r"markaz|qadha|nahiya)\b")


def norm(s):
    s = (s or "").strip().lower()
    if not s:
        return ""
    # strip Latin diacritics (ad dīwānīyah -> ad diwaniyah); Arabic script is left intact
    s = _DIAC.sub("", unicodedata.normalize("NFKD", s))
    s = re.sub(r"[^\w؀-ۿ ]+", " ", s)     # punctuation -> space (keep Arabic block)
    s = re.sub(r"\d+", " ", s)                       # drop digits (9baghdad -> baghdad)
    s = re.sub(r"^iraq\b", " ", s)                   # "iraq baghdad" -> "baghdad"
    s = _NOISE.sub(" ", s)                           # "basra city" -> "basra"
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(al|el|as|ar|an|ad)[\s-]+", "", s)  # al najaf -> najaf
    s = re.sub(r"^ال", "", s)                        # النجف -> نجف
    return re.sub(r"\s+", " ", s).strip()


ALIAS = {}
for canon, al in CANON.items():
    ALIAS[norm(canon)] = canon
    for a in al:
        ALIAS[norm(a)] = canon
# compare countries in NORMALISED form too — norm() strips the Arabic 'ال', so 'العراق' arrives as 'عراق'
_NOT_CITY_N = {norm(x) for x in NOT_A_CITY} | set(NOT_A_CITY)
_CANON_NORMS = {norm(c): c for c in CANON}
_BLOCK = {}
for grp in CONFUSABLE:
    for a in grp:
        _BLOCK.setdefault(a, set()).update(grp - {a})


def resolve(raw):
    """raw city -> (canonical, how). how = exact|fuzzy|unknown|country|asis"""
    n = norm(raw)
    if not n or len(n) < 2:
        return "", "unknown"
    if n in _NOT_CITY_N:
        return "", "country"
    if n in ALIAS:
        return ALIAS[n], "exact"
    # tight, guarded fuzzy
    best, second, best_c = 0.0, 0.0, None
    for cn, canon in _CANON_NORMS.items():
        r = SequenceMatcher(None, n, cn).ratio()
        if r > best:
            second, best, best_c = best, r, canon
        elif r > second:
            second = r
    if best_c and best >= FUZZY_MIN and (best - second) > 0.02:
        # guard: never fuzz across a known confusable pair (irbid !-> erbil)
        exact_self = ALIAS.get(n)
        if exact_self and best_c in _BLOCK.get(exact_self, ()):
            return exact_self, "exact"
        if any(n == norm(x) for x in _BLOCK.get(best_c, ())):
            return n.title(), "asis"
        return best_c, "fuzzy"
    return n.title(), "asis"


def main():
    commit = "--commit" in sys.argv
    c = db_config.connect(); cur = c.cursor()
    cur.execute("""
        SELECT city, SUM(n) FROM (
            SELECT trim(city) AS city, COUNT(*) n FROM clients WHERE COALESCE(trim(city),'')<>'' GROUP BY 1
            UNION ALL
            SELECT trim(city), COUNT(*) FROM leads WHERE COALESCE(trim(city),'')<>'' GROUP BY 1
        ) t GROUP BY city
    """)
    raws = cur.fetchall()
    groups = defaultdict(list); how_n = defaultdict(int); rows_by_how = defaultdict(int)
    mapping = {}
    for raw, n in raws:
        canon, how = resolve(raw)
        mapping[raw] = canon
        how_n[how] += 1; rows_by_how[how] += int(n)
        if canon:
            groups[canon].append((raw, int(n)))

    tot = sum(int(n) for _, n in raws)
    print(f"raw distinct spellings: {len(raws):,} | rows: {tot:,}")
    print(f"resolved -> {len(groups):,} canonical cities\n")
    print("by method   (distinct spellings / rows):")
    for h in ("exact", "fuzzy", "country", "unknown", "asis"):
        print(f"   {h:8} {how_n[h]:>6,} / {rows_by_how[h]:>7,}")
    print("\nTOP canonical cities and the spellings folded into them:")
    for canon, mem in sorted(groups.items(), key=lambda kv: -sum(m[1] for m in kv[1]))[:14]:
        tot_n = sum(m[1] for m in mem)
        variants = ", ".join(f"{r}({n})" for r, n in sorted(mem, key=lambda m: -m[1])[:7])
        print(f"   {canon:14} {tot_n:>7,} rows  <- {len(mem):>4} spellings: {variants}")

    if not commit:
        print("\nDRY-RUN — nothing written. Re-run with --commit to write city_canon.")
        c.close(); return

    # ALTER only if missing — an unconditional ADD COLUMN IF NOT EXISTS still takes an
    # AccessExclusiveLock on a live table and can block every reader (API freeze).
    for t in ("clients", "leads"):
        cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name='city_canon'", (t,))
        if not cur.fetchone():
            cur.execute(f"ALTER TABLE {t} ADD COLUMN city_canon TEXT")
        cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_city_canon ON {t}(city_canon)")
    from psycopg2.extras import execute_values
    cur.execute("CREATE TEMP TABLE _cm(raw TEXT, canon TEXT) ON COMMIT DROP")
    execute_values(cur, "INSERT INTO _cm(raw,canon) VALUES %s", list(mapping.items()))
    cur.execute("CREATE INDEX ON _cm(raw)")
    for t in ("clients", "leads"):
        cur.execute(f"""UPDATE {t} x SET city_canon = NULLIF(_cm.canon,'')
                        FROM _cm WHERE trim(x.city) = _cm.raw""")
        cur.execute(f"UPDATE {t} SET city_canon = NULL WHERE COALESCE(trim(city),'') = ''")
    c.commit()
    for t in ("clients", "leads"):
        cur.execute(f"SELECT COUNT(*) FILTER (WHERE city_canon IS NOT NULL), COUNT(DISTINCT city_canon) FROM {t}")
        a, b = cur.fetchone()
        print(f"\n{t}: {a:,} rows given a canonical city across {b:,} distinct cities")
    c.close()


if __name__ == "__main__":
    main()
