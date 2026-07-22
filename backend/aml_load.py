# -*- coding: utf-8 -*-
"""Download + parse government sanctions lists into sanctions_entities/sanctions_names (for
aml_screening.py). Sources: OFAC SDN (+ AKA alt list) and the UN consolidated list. Per-source full
refresh (small tables) inside a transaction, so a failed download never leaves a half-loaded list.

  python aml_load.py            # refresh all sources
  python aml_load.py --source ofac
  python aml_load.py --stats    # counts only

Wire a daily refresh the same way as the other loops (Task Scheduler / a loop) — lists change often.
"""
import sys, io, os, csv, re, urllib.request, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import xml.etree.ElementTree as ET
from sqlalchemy import text
from database import SessionLocal
import aml_screening as A

UA = {"User-Agent": "Mozilla/5.0 (TNFX-CRM AML loader)"}
OFAC_SDN = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OFAC_ALT = "https://www.treasury.gov/ofac/downloads/alt.csv"
UN_XML   = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
# EU consolidated financial-sanctions list — the EU's OWN public webgate XML (public-sector data,
# clean licensing for commercial use). The token is the EU's fixed public download token.
EU_XML   = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
EU_NS    = "{http://eu.europa.ec/fpi/fsd/export}"
NULL = {"-0- ", "-0-", "", None}


def _dl(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def _clean(v):
    v = (v or "").strip()
    return "" if v in NULL else v


def _extract(remarks, key):
    m = re.search(key + r"\s+([^;]+)", remarks or "", re.I)
    return _clean(m.group(1)) if m else ""


def load_ofac(db, workdir):
    sdn = _dl(OFAC_SDN, os.path.join(workdir, "sdn.csv"))
    alt = _dl(OFAC_ALT, os.path.join(workdir, "alt.csv"))
    # ent_num -> (entity_type, primary_name, program, dob, nationality)
    ents = {}
    names = {}   # ent_num -> set of names
    with open(sdn, encoding="latin-1", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 12:
                continue
            en = _clean(row[0]); nm = _clean(row[1]); typ = _clean(row[2]).lower()
            prog = _clean(row[3]); remarks = row[11]
            if not en or not nm:
                continue
            etype = "individual" if typ == "individual" else (typ or "entity")
            ents[en] = (etype, nm, prog, _extract(remarks, "DOB"), _extract(remarks, "nationality"))
            names.setdefault(en, set()).add(nm)
    # AKAs
    if os.path.exists(alt):
        with open(alt, encoding="latin-1", newline="") as f:
            for row in csv.reader(f):
                if len(row) < 4:
                    continue
                en = _clean(row[0]); an = _clean(row[3])
                if en in ents and an:
                    names.setdefault(en, set()).add(an)
    _replace_source(db, "ofac", ents, names)
    return len(ents)


def load_un(db, workdir):
    xmlp = _dl(UN_XML, os.path.join(workdir, "un.xml"))
    tree = ET.parse(xmlp); root = tree.getroot()
    ents, names = {}, {}

    def _txt(node, tag):
        el = node.find(tag)
        return _clean(el.text) if el is not None and el.text else ""

    for ind in root.iter("INDIVIDUAL"):
        did = _txt(ind, "DATAID") or _txt(ind, "REFERENCE_NUMBER")
        if not did:
            continue
        parts = [_txt(ind, t) for t in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
        primary = " ".join(p for p in parts if p).strip()
        if not primary:
            continue
        nat = ""
        natnode = ind.find("NATIONALITY")
        if natnode is not None:
            nat = _clean("".join(v.text or "" for v in natnode.findall("VALUE")))
        dob = ""
        dobn = ind.find("INDIVIDUAL_DATE_OF_BIRTH")
        if dobn is not None:
            dob = _txt(dobn, "DATE") or _txt(dobn, "YEAR") or ""
        prog = _txt(ind, "UN_LIST_TYPE")
        ents[did] = ("individual", primary, prog, dob, nat)
        nm = {primary}
        for al in ind.findall("INDIVIDUAL_ALIAS"):
            a = _clean(al.findtext("ALIAS_NAME"))
            if a:
                nm.add(a)
        names[did] = nm

    for ent in root.iter("ENTITY"):
        did = _txt(ent, "DATAID") or _txt(ent, "REFERENCE_NUMBER")
        primary = _txt(ent, "FIRST_NAME")
        if not did or not primary:
            continue
        ents[did] = ("entity", primary, _txt(ent, "UN_LIST_TYPE"), "", "")
        nm = {primary}
        for al in ent.findall("ENTITY_ALIAS"):
            a = _clean(al.findtext("ALIAS_NAME"))
            if a:
                nm.add(a)
        names[did] = nm
    _replace_source(db, "un", ents, names)
    return len(ents)


def load_eu(db, workdir):
    xmlp = _dl(EU_XML, os.path.join(workdir, "eu.xml"))
    root = ET.parse(xmlp).getroot()
    ents, names = {}, {}
    for se in root.findall(EU_NS + "sanctionEntity"):
        did = _clean(se.get("euReferenceNumber")) or _clean(se.get("logicalId"))
        if not did:
            continue
        st = se.find(EU_NS + "subjectType")
        code = (st.get("code") if st is not None else "") or ""
        etype = "individual" if code == "person" else "entity"
        nm = set()
        for na in se.findall(EU_NS + "nameAlias"):
            whole = _clean(na.get("wholeName"))
            if not whole:
                whole = " ".join(p for p in (_clean(na.get("firstName")), _clean(na.get("middleName")),
                                             _clean(na.get("lastName"))) if p).strip()
            if whole:
                nm.add(whole)
        if not nm:
            continue
        primary = sorted(nm, key=len, reverse=True)[0]          # fullest name variant
        cit = se.find(EU_NS + "citizenship")
        nat = _clean(cit.get("countryDescription")) if cit is not None else ""
        bd = se.find(EU_NS + "birthdate")
        dob = (_clean(bd.get("birthdate")) or _clean(bd.get("year"))) if bd is not None else ""
        reg = se.find(EU_NS + "regulation")
        prog = _clean(reg.get("programme")) if reg is not None else ""
        ents[did] = (etype, primary, prog, dob, nat)
        names[did] = nm
    _replace_source(db, "eu", ents, names)
    return len(ents)


def _replace_source(db, source, ents, names):
    """Full refresh of one source inside a transaction."""
    db.execute(text("DELETE FROM sanctions_entities WHERE source=:s"), {"s": source})
    for en, (etype, primary, prog, dob, nat) in ents.items():
        eid = db.execute(text("""
            INSERT INTO sanctions_entities (source, ext_id, entity_type, primary_name, programs, dob, nationality)
            VALUES (:s,:x,:t,:p,:pg,:d,:n) RETURNING id
        """), {"s": source, "x": en, "t": etype, "p": primary[:500], "pg": prog[:200],
               "d": dob[:100], "n": nat[:200]}).scalar()
        seen = set()
        for i, nm in enumerate(sorted(names.get(en, {primary}))):
            nn = A.normalize(nm)
            if not nn or nn in seen:
                continue
            seen.add(nn)
            db.execute(text("""INSERT INTO sanctions_names (entity_id, name, name_norm, is_primary)
                               VALUES (:e,:nm,:nn,:pr)"""),
                       {"e": eid, "nm": nm[:500], "nn": nn, "pr": (nm == primary)})
    db.commit()


def refresh_if_stale(hours=20):
    """Reload the lists only if the newest entity is older than `hours` (staleness-based so process
    restarts don't re-download). Safe to call every enrich cycle. Returns True if it reloaded."""
    import datetime, tempfile
    db = SessionLocal()
    try:
        A.ensure_schema(db)
        last = db.execute(text("SELECT max(updated_at) FROM sanctions_entities")).scalar()
        if last is not None and (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds() < hours * 3600:
            return False
        with tempfile.TemporaryDirectory() as wd:
            try:
                load_ofac(db, wd)
            except Exception as e:
                db.rollback(); print(f"[aml] OFAC refresh failed: {e}", flush=True)
            try:
                load_un(db, wd)
            except Exception as e:
                db.rollback(); print(f"[aml] UN refresh failed: {e}", flush=True)
            try:
                load_eu(db, wd)
            except Exception as e:
                db.rollback(); print(f"[aml] EU refresh failed: {e}", flush=True)
        print("[aml] sanctions lists refreshed", flush=True)
        return True
    finally:
        db.close()


def stats(db):
    for r in db.execute(text("""SELECT source, count(*) FROM sanctions_entities GROUP BY source ORDER BY source""")).fetchall():
        print(f"  {r[0]:6} entities: {r[1]:,}")
    n = db.execute(text("SELECT count(*) FROM sanctions_names")).scalar()
    print(f"  total name variants: {n:,}")


def main():
    db = SessionLocal()
    A.ensure_schema(db)
    if "--stats" in sys.argv:
        stats(db); db.close(); return
    src = "all"
    if "--source" in sys.argv:
        src = sys.argv[sys.argv.index("--source") + 1]
    with tempfile.TemporaryDirectory() as wd:
        if src in ("all", "ofac"):
            try:
                n = load_ofac(db, wd); print(f"OFAC loaded: {n:,} entities", flush=True)
            except Exception as e:
                db.rollback(); print(f"OFAC FAILED: {e}", flush=True)
        if src in ("all", "un"):
            try:
                n = load_un(db, wd); print(f"UN loaded: {n:,} entities", flush=True)
            except Exception as e:
                db.rollback(); print(f"UN FAILED: {e}", flush=True)
        if src in ("all", "eu"):
            try:
                n = load_eu(db, wd); print(f"EU loaded: {n:,} entities", flush=True)
            except Exception as e:
                db.rollback(); print(f"EU FAILED: {e}", flush=True)
    print("---- totals ----"); stats(db)
    db.close()


if __name__ == "__main__":
    main()
