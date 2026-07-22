"""
family_engine.py — detect FAMILY members (level 1 = direct: brothers / father↔son / same mother) and
feed them into the ONE relation engine via the `entity_family` table (relation_engine reads it and
turns them into family_l1 / family_l2 signals → they count for NDA and block the welcome bonus).

DATA REALITY (measured): 83% of customers have only a 3-part name (first · father · grandfather); a
real surname exists for ~1%, and mother_name for 0.2%. So we anchor on the NAME CHAIN, not a surname:

  BROTHERS   — same father AND same grandfather  (Ahmed·Ali·Hussein  &  Omar·Ali·Hussein)
  FATHER↔SON — the chain shifts by one: son [S, F, G]  ⇔  father [F, G, GG]
  (same mother, when present, is treated as a hard confirm.)

GUARDS (learned from the email/IP work — do NOT repeat the "40-person Adnan family" mistake):
  • junk names (ib account / test / 2-letter garbage) are skipped.
  • a COMMON name chain (father+grandfather shared by many — e.g. "ali hussein" ×226) is NOT a family
    on its own; such pairs are kept ONLY when corroborated by same city (not Baghdad) or same IB.
  • rare chains (shared by <= RARE_CAP people) are accepted directly — a specific father+grandfather
    match among 2-3 people is already strong.

Run:  python family_engine.py            (DRY — report the groups, writes NOTHING)
      python family_engine.py --commit   (write entity_family; then re-run relation_engine.py)
"""
import sys, re
from collections import defaultdict
import db_config

RARE_CAP = 4          # a father+grandfather chain shared by <= this many people is specific enough
JUNK = {"account", "test", "ib", "na", "none", "null", "customer", "client", "vc", "ccv", "cv"}


def toks(name):
    return [t for t in re.sub(r"[^a-z؀-ۿ ]", " ", (name or "").lower()).split() if t not in JUNK]


def load(cur):
    """entity-key -> (tokens, city, ib, mother)."""
    ent = {}
    cur.execute("""SELECT DISTINCT ON (customer_no) customer_no, name, lower(COALESCE(city_canon,'')),
                          COALESCE(agent,0), lower(COALESCE(mother_name,''))
                   FROM clients WHERE customer_no IS NOT NULL AND name IS NOT NULL
                   ORDER BY customer_no, length(name) DESC NULLS LAST""")
    for cn, name, city, ib, mother in cur.fetchall():
        t = toks(name)
        if len(t) >= 3:
            ent[f"C{cn}"] = (t, city, ib, (mother or "").strip())
    cur.execute("""SELECT id, full_name, lower(COALESCE(city_canon,'')), lower(COALESCE(mother_name,''))
                   FROM leads WHERE full_name IS NOT NULL""")
    for lid, name, city, mother in cur.fetchall():
        t = toks(name)
        if len(t) >= 3:
            ent[f"L{lid}"] = (t, city, 0, (mother or "").strip())
    return ent


def corroborated(a, b):
    _, ca, ia, ma = a
    _, cb, ib, mb = b
    if ma and ma == mb:
        return True                       # same mother = hard confirm
    if ca and ca == cb and ca != "baghdad":
        return True
    if ia and ia == ib:
        return True
    return False


def build(ent):
    edges = {}     # (a,b) -> reason
    def emit(a, b, reason):
        p = (a, b) if a < b else (b, a)
        edges.setdefault(p, reason)

    # block by (father, grandfather) — used both as the brothers key and the common-chain gauge
    blocks = defaultdict(list)
    for k, v in ent.items():
        t = v[0]
        blocks[(t[1], t[2])].append(k)

    # ── BROTHERS ──
    for (fa, gf), members in blocks.items():
        if len(members) < 2 or len(fa) < 3 or len(gf) < 3:
            continue
        common = len(members) > RARE_CAP
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if not common or corroborated(ent[a], ent[b]):
                    emit(a, b, "brothers")

    # ── FATHER ↔ SON: son [S,F,G] ⇔ father [F,G,GG] ──
    by_first2 = defaultdict(list)     # (t0,t1) -> entities whose name STARTS with this
    for k, v in ent.items():
        t = v[0]
        by_first2[(t[0], t[1])].append(k)
    for k, v in ent.items():
        t = v[0]
        parent_key = (t[1], t[2])     # this person's father+grandfather = the father's first+father
        if len(parent_key[0]) < 3 or len(parent_key[1]) < 3:
            continue
        for fa in by_first2.get(parent_key, []):
            if fa == k:
                continue
            if len(blocks.get((t[1], t[2]), [])) > RARE_CAP and not corroborated(ent[k], ent[fa]):
                continue
            emit(k, fa, "father-son")
    return edges


def families(edges):
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    fam = defaultdict(set)
    for a, b in edges:
        r = find(a); fam[r].add(a); fam[r].add(b)
    return list(fam.values())


def main():
    commit = "--commit" in sys.argv
    c = db_config.connect(); cur = c.cursor()
    ent = load(cur)
    edges = build(ent)
    fams = families(edges)
    fams.sort(key=len, reverse=True)
    print(f"entities scanned: {len(ent):,} | family edges: {len(edges):,} | families: {len(fams):,}")
    sizes = defaultdict(int)
    for f in fams:
        sizes[min(len(f), 6)] += 1
    print("family sizes:", {(f"{k}+" if k == 6 else str(k)): v for k, v in sorted(sizes.items())})
    print("\nlargest families (sanity-check for over-merging):")
    for f in fams[:12]:
        names = ", ".join(" ".join(ent[m][0][:3]) for m in list(f)[:5])
        print(f"  {len(f):>3} people: {names}")

    if not commit:
        print("\nDRY-RUN — nothing written. Re-run with --commit to feed family into the relation engine.")
        c.close(); return

    cur.execute("""CREATE TABLE IF NOT EXISTS entity_family(
        ent_a TEXT, ent_b TEXT, level INT, value TEXT, PRIMARY KEY(ent_a, ent_b))""")
    cur.execute("DELETE FROM entity_family")
    from psycopg2.extras import execute_values
    execute_values(cur, "INSERT INTO entity_family(ent_a,ent_b,level,value) VALUES %s",
                   [(a, b, 1, r) for (a, b), r in edges.items()], page_size=2000)
    c.commit()
    print(f"\nCOMMITTED {len(edges):,} family edges (level 1). Now run: python relation_engine.py")
    c.close()


if __name__ == "__main__":
    main()
