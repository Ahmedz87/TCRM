# -*- coding: utf-8 -*-
"""Screen the EXISTING client base against the sanctions lists (AML backfill). Onboarding screening
only covers NEW registrations — a client who signed up before the gate could already be sanctioned.
Records hits into the SAME aml_screenings/aml_hits queue the compliance UI (/aml/hits) reads.

FAST path: one index-accelerated trigram JOIN (pg_trgm % operator) pulls candidate (client-name,
sanctions-name) pairs on the DB; Python then scores only those candidates with the real matcher.
Uses a RAW psycopg2 connection (db_config) so the % operator isn't mangled by SQLAlchemy's param
escaping. Read-only on client/sanctions data; writes only review rows. Direct :5432 (batch job).

  python aml_screen_existing.py
"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from collections import defaultdict
import db_config
import aml_screening as A

JOIN_SQL = """
WITH cn AS (
  SELECT min(id) AS cid,
         min(COALESCE(NULLIF(name_en,''), name)) AS disp,
         trim(regexp_replace(lower(COALESCE(NULLIF(name_en,''), name)), '[^a-z0-9]+', ' ', 'g')) AS norm
  FROM clients
  WHERE COALESCE(NULLIF(name_en,''), name) IS NOT NULL
    AND length(COALESCE(NULLIF(name_en,''), name)) > 4
  GROUP BY lower(COALESCE(NULLIF(name_en,''), name))
)
SELECT cn.cid, cn.disp, sn.name, e.id, e.source, e.entity_type, e.programs
FROM cn
JOIN sanctions_names sn ON sn.name_norm % cn.norm
JOIN sanctions_entities e ON e.id = sn.entity_id
WHERE cn.norm <> ''
"""


def main():
    c = db_config.connect(); cur = c.cursor()
    try:
        cur.execute("SELECT val FROM crm_settings WHERE key='aml_match_threshold'")
        r = cur.fetchone(); thr = float(r[0]) if r and r[0] else A.DEFAULT_THRESHOLD
    except Exception:
        c.rollback(); thr = A.DEFAULT_THRESHOLD

    cur.execute("DELETE FROM aml_hits WHERE subject_type='client'")
    cur.execute("DELETE FROM aml_screenings WHERE subject_type='client'")
    c.commit()

    # 0.5 trigram floor: 0.3 (full recall, used at onboarding) explodes to millions of pairs on the
    # whole client base; 0.5 keeps ~68k pairs — a fast, sensible first-pass BACKFILL floor that catches
    # exact/near-exact/mild-reorder matches. New clients still get full-recall screening at onboarding.
    cur.execute("SELECT set_limit(0.5)")
    t0 = time.time()
    print("running trigram candidate join (distinct client names x sanctions names)...", flush=True)
    cur.execute(JOIN_SQL)                          # NO params -> % is the trigram operator, index-accelerated
    rows = cur.fetchall()
    print(f"  join returned {len(rows):,} candidate pairs in {time.time()-t0:.0f}s; scoring...", flush=True)

    cand = defaultdict(list)
    for cid, disp, matched, eid, source, etype, programs in rows:
        cand[(cid, disp)].append((matched, eid, source, etype, programs))

    hits = 0
    for (cid, disp), cands in cand.items():
        qn = A.normalize(disp); qtok = A._tokens(qn)
        if len(qn) < 3 or len(set(qtok)) < 2:   # >=2 DISTINCT name parts (skips "Abbas Abbas")
            continue
        best = {}
        for matched, eid, source, etype, programs in cands:
            score = A._name_score(qtok, A._tokens(A.normalize(matched)), qn, A.normalize(matched))
            if score >= thr and (eid not in best or score > best[eid][0]):
                best[eid] = (round(score, 3), matched, source, etype, programs)
        if not best:
            continue
        top = max(v[0] for v in best.values())
        cur.execute("""INSERT INTO aml_screenings (subject_type, subject_id, name_screened, result, n_hits, top_score, screened_by)
                       VALUES ('client', %s, %s, 'hit', %s, %s, 'backfill') RETURNING id""",
                    (cid, disp, len(best), top))
        sid = cur.fetchone()[0]
        for eid, (sc, matched, source, etype, programs) in best.items():
            cur.execute("""INSERT INTO aml_hits (screening_id, subject_type, subject_id, entity_id, source,
                                 matched_name, entity_type, programs, score, status)
                           VALUES (%s,'client',%s,%s,%s,%s,%s,%s,%s,'pending')""",
                        (sid, cid, eid, source, matched, etype, programs, sc))
        hits += 1
    c.commit()

    print(f"\nDONE in {time.time()-t0:.0f}s: {hits:,} existing client name(s) matched a sanctions entity "
          f"-> queued for compliance review in the AML page.", flush=True)
    cur.execute("""SELECT h.score, s.name_screened, h.matched_name, h.source, h.subject_id
                   FROM aml_hits h JOIN aml_screenings s ON s.id=h.screening_id
                   WHERE h.subject_type='client' ORDER BY h.score DESC, s.name_screened LIMIT 15""")
    top = cur.fetchall()
    if top:
        print("top matches (review first):")
        for r in top:
            print(f"  {r[0]:.2f}  client:{str(r[1])[:26]:26} ~ {str(r[2])[:30]:30} [{r[3]}] (client_id {r[4]})")
    c.close()


if __name__ == "__main__":
    main()
