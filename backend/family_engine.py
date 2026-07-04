"""
family_engine.py — detect FAMILIES among clients + leads and give each family an internal code.

Desk rule: a person is put in a family when they match on >=3 of these FIVE attributes:
    grandfather name · surname (tribe/family name) · city · IB (agent) · IP
Severity:  >=4 of 5 match -> RED (very likely same household),  exactly 3 -> YELLOW (probable).
Everyone in the same family gets the SAME internal family code (FAM-xxxxx) with the tag colour, so
uncle/brother/wife/son etc. all carry one code. Names are Arabic 4-part: first · father · grandfather
· surname — grandfather = 3rd token, surname = last token (when >=4 tokens).

Blocking keeps it fast: candidates must share a NAME anchor (surname OR grandfather) — then the 5-way
score decides. City/IB/IP are too low-cardinality to anchor on (whole-city "families" would be wrong).

Run DRY (no writes, just the report):   python family_engine.py
Commit family codes to the DB:          python family_engine.py --commit
"""
import sys, re
from collections import defaultdict
import db_config

CAP = 600  # skip a name-anchor block bigger than this (too-generic surname → not a real family)


def _tokens(name):
    return re.sub("[^a-z؀-ۿ ]", " ", (name or "").lower()).split()


def _parts(name):
    """(grandfather, surname) from an Arabic 4-part name. grandfather=3rd token, surname=last token."""
    t = _tokens(name)
    gf = t[2] if len(t) >= 3 else ""
    sn = t[3] if len(t) >= 4 else (t[-1] if len(t) >= 2 else "")
    return gf, sn


def load_people(cur):
    """Return dict pid -> attrs. pid = ('C',login) or ('L',id)."""
    people = {}
    # clients: name, city, agent(IB)
    cur.execute("SELECT login, name, city, agent FROM clients WHERE name IS NOT NULL AND login IS NOT NULL")
    for login, name, city, agent in cur.fetchall():
        gf, sn = _parts(name)
        people[("C", login)] = {"name": name, "gf": gf, "sn": sn,
                                "city": (city or "").strip().lower(), "ib": str(agent or "") if agent else "",
                                "ip": ""}
    # one representative IP per client (most-seen)
    cur.execute("""SELECT login, identifier_value FROM account_identifiers
                   WHERE identifier_type='ip' AND identifier_value NOT IN ('0','')""")
    ipmap = {}
    for login, ip in cur.fetchall():
        ipmap.setdefault(login, ip)
    for (k, login), a in people.items():
        if k == "C" and login in ipmap:
            a["ip"] = ipmap[login]
    # leads: full_name, city (no IB/IP)
    cur.execute("SELECT id, full_name, city FROM leads WHERE full_name IS NOT NULL")
    for lid, name, city in cur.fetchall():
        gf, sn = _parts(name)
        people[("L", lid)] = {"name": name, "gf": gf, "sn": sn,
                              "city": (city or "").strip().lower(), "ib": "", "ip": ""}
    return people


def _score(a, b):
    """How many of the 5 attributes match (non-empty on both sides)."""
    n = 0
    for k in ("gf", "sn", "city", "ib", "ip"):
        if a[k] and b[k] and a[k] == b[k]:
            n += 1
    return n


def build_families(people):
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y); parent[rx] = ry if rx != ry else parent[rx]

    best = {}  # pair(frozenset) -> match count (for severity)
    # anchor blocks: by surname, and by grandfather (high-cardinality name tokens)
    for anchor in ("sn", "gf"):
        blocks = defaultdict(list)
        for pid, a in people.items():
            if a[anchor] and len(a[anchor]) >= 3:
                blocks[a[anchor]].append(pid)
        for val, members in blocks.items():
            if not (2 <= len(members) <= CAP):
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    s = _score(people[members[i]], people[members[j]])
                    if s >= 3:
                        union(members[i], members[j])
                        key = frozenset((members[i], members[j]))
                        best[key] = max(best.get(key, 0), s)

    fams = defaultdict(list)
    for pid in list(parent):
        fams[find(pid)].append(pid)
    fams = {r: ms for r, ms in fams.items() if len(ms) >= 2}

    # severity per family = best pairwise score among its members
    out = []
    for r, ms in fams.items():
        mx = 0
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                mx = max(mx, best.get(frozenset((ms[i], ms[j])), 0))
        out.append({"members": sorted(ms), "match": mx,
                    "severity": "red" if mx >= 4 else "yellow"})
    out.sort(key=lambda f: (-f["match"], -len(f["members"])))
    return out


def main():
    commit = "--commit" in sys.argv
    c = db_config.connect(); cur = c.cursor()
    people = load_people(cur)
    fams = build_families(people)
    red = sum(1 for f in fams if f["severity"] == "red")
    members = sum(len(f["members"]) for f in fams)
    print(f"people scanned: {len(people)} | families found: {len(fams)} "
          f"(RED {red}, YELLOW {len(fams)-red}) | tagged members: {members}")
    for f in fams[:8]:
        names = ", ".join(people[m]["name"] for m in f["members"][:4])
        print(f"  [{f['severity'].upper()} {f['match']}/5] {len(f['members'])} members: {names}")

    if not commit:
        print("\nDRY-RUN — nothing written. Re-run with --commit to assign family codes.")
        c.close(); return

    cur.execute("""CREATE TABLE IF NOT EXISTS families (
        family_id SERIAL PRIMARY KEY, code TEXT UNIQUE, severity TEXT, match_level INT,
        member_count INT, created_at TIMESTAMPTZ DEFAULT NOW())""")
    for t in ("clients", "leads"):
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS family_code TEXT")
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS family_tag TEXT")
    # rebuild fresh each run
    cur.execute("UPDATE clients SET family_code=NULL, family_tag=NULL WHERE family_code IS NOT NULL")
    cur.execute("UPDATE leads   SET family_code=NULL, family_tag=NULL WHERE family_code IS NOT NULL")
    cur.execute("TRUNCATE families RESTART IDENTITY")
    for n, f in enumerate(fams, 1):
        code = f"FAM-{n:05d}"
        cur.execute("INSERT INTO families (code, severity, match_level, member_count) VALUES (%s,%s,%s,%s)",
                    (code, f["severity"], f["match"], len(f["members"])))
        clogins = [m[1] for m in f["members"] if m[0] == "C"]
        lids = [m[1] for m in f["members"] if m[0] == "L"]
        if clogins:
            cur.execute("UPDATE clients SET family_code=%s, family_tag=%s WHERE login = ANY(%s)",
                        (code, f["severity"], clogins))
        if lids:
            cur.execute("UPDATE leads SET family_code=%s, family_tag=%s WHERE id = ANY(%s)",
                        (code, f["severity"], lids))
    c.commit(); c.close()
    print(f"\nCOMMITTED {len(fams)} families.")


if __name__ == "__main__":
    main()
