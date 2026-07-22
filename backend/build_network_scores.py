"""
build_network_scores.py — THE single source of the network-risk score (x/10).

Every page (Clients, Leads, IB profile, Transactions, Neg-balance) and the detail popup show a
network-risk badge. They used to each compute their own number from a different formula on a
different 0-10 vs 0-100 scale, so the SAME person showed a different x/10 in different places.

This job computes ONE canonical 0-10 score per CUSTOMER (customer_no) from the connection engine's
signals, and writes it to clients.network_score (+ network_level / network_reason) for every one of
that customer's logins, and to leads.network_score for leads. All surfaces then just read that column.

Scoring (identical weighting to connection_engine._confidence, so the badge == the strongest link
in the detail popup):
  • DEVICE (cid/mqid) shared with a DIFFERENT customer  -> cid weight 1.0  -> score 10  -> RED
  • IP shared            (fan-out 2..25)                -> 0.30
  • SIMILAR email        (normalised local part, 2..25) -> 0.80   (also links leads)
  • SAME payment sender  (same Qi card/wallet, 2..6)    -> 0.85
  combined via noisy-OR. "Any CID = red" is automatic (cid -> 10 -> critical).
  IB / city are BOOSTERS in the live per-connection view only; they're too broad to raise a subject's
  standalone risk here (every client of an IB shares the IB), matching the engine's find-vs-boost split.

Run:   python build_network_scores.py            (compute + write; idempotent)
       python build_network_scores.py --dry-run  (report only)
"""
import sys
from collections import defaultdict
import db_config
import connection_engine as CE

FAN_DEVICE, FAN_IP, FAN_PAY, FAN_EMAIL = 25, 25, 6, 25

_NET_COLS = {"network_score": "INT", "network_level": "TEXT", "network_reason": "TEXT"}


def _add_columns(cur, spec):
    """ALTER only the columns that are actually missing. An unconditional ADD COLUMN IF NOT EXISTS
    still grabs an AccessExclusiveLock on a live table and can block every reader (API freeze)."""
    for tbl, cols in spec.items():
        cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name=%s""", (tbl,))
        have = {r[0] for r in cur.fetchall()}
        for col, typ in cols.items():
            if col not in have:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")


def build_common_cores(cur):
    """Rebuild common_email_cores = email letter-cores shared by >= COMMON_CORE_MIN_PEOPLE DIFFERENT
    people. Purely data-driven (no hardcoded name list), so it catches common Arabic first names
    (ali/ahmed/ahmad/mohammed/mustafa/hussein…) AND generic tokens (souriahost/iraqx/tnfx/aaa) alike.
    A similar-email hit on one of these is meaningless on its own — see the guard in connection_engine."""
    core = CE._norm_email_core_sql("email")
    cur.execute("CREATE TABLE IF NOT EXISTS common_email_cores(core TEXT PRIMARY KEY, n_people INT)")
    # DELETE (RowExclusive), not TRUNCATE (AccessExclusive): the live API reads this table on every
    # connections popup, and TRUNCATE deadlocks against those readers.
    cur.execute("DELETE FROM common_email_cores")
    cur.execute(f"""
        INSERT INTO common_email_cores(core, n_people)
        SELECT core, COUNT(DISTINCT ent) FROM (
            SELECT {core} AS core, 'C'||customer_no AS ent FROM clients
             WHERE customer_no IS NOT NULL AND email IS NOT NULL AND email <> ''
            UNION
            SELECT {core} AS core, 'L'||id AS ent FROM leads
             WHERE email IS NOT NULL AND email <> ''
        ) t
        WHERE length(core) >= 3
        GROUP BY core HAVING COUNT(DISTINCT ent) >= %s
    """, (CE.COMMON_CORE_MIN_PEOPLE,))
    cur.execute("SELECT core FROM common_email_cores")
    return {r[0] for r in cur.fetchall()}


def compute(cur, common_cores=frozenset()):
    """Return (cust_sigs: {customer_no:set}, lead_sigs: {lead_id:set})."""
    cust = defaultdict(set)
    leads = defaultdict(set)

    # device (cid/mqid) — clients only (leads have no account_identifiers)
    for typ, fan, sig in (("cid", FAN_DEVICE, "cid"), ("mqid", FAN_DEVICE, "mqid")):
        cur.execute("""
            SELECT array_agg(DISTINCT c.customer_no)
            FROM account_identifiers ai JOIN clients c ON c.login = ai.login
            WHERE ai.identifier_type = %s AND ai.identifier_value NOT IN ('0','')
              AND c.customer_no IS NOT NULL
            GROUP BY ai.identifier_value
            HAVING COUNT(DISTINCT c.customer_no) BETWEEN 2 AND %s
        """, (typ, fan))
        for (arr,) in cur.fetchall():
            for cn in arr:
                cust[cn].add(sig)

    # IP — recorded, but NEVER a link on its own (score_signals drops an ip-only subject to 0). It
    # counts next to another factor, or via TIMING: same IP + registered within IP_COREG_HOURS, or
    # same IP + first deposit within IP_CODEP_HOURS = one person/desk at one connection.
    # per-CUSTOMER facts (earliest reg / first deposit, canonical city, IB) — customer grain, exactly
    # what score_connections uses, so the popup and the stored badge never disagree.
    cur.execute("""
        SELECT customer_no, MIN(NULLIF(reg_date,'')), MIN(NULLIF(first_deposit_at,'')),
               MIN(NULLIF(lower(city_canon),'')), MIN(NULLIF(agent,0))
        FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no
    """)
    cfact = {}
    for cn, r, f, city, ib in cur.fetchall():
        cfact[cn] = (CE._ts(r), CE._ts(f), city, ib)
    cur.execute("""
        WITH tok AS (
            SELECT DISTINCT ai.identifier_value v, c.customer_no cn
            FROM account_identifiers ai JOIN clients c ON c.login = ai.login
            WHERE ai.identifier_type = 'ip' AND ai.identifier_value NOT IN ('0','')
              AND c.customer_no IS NOT NULL
        ), sh AS (SELECT v FROM tok GROUP BY v HAVING COUNT(DISTINCT cn) BETWEEN 2 AND %s)
        SELECT t.v, t.cn FROM tok t JOIN sh USING (v)
    """, (FAN_IP,))
    ipg = defaultdict(list)
    for v, cn in cur.fetchall():
        ipg[v].append(cn)
    n_coreg = n_codep = 0
    REG_S, DEP_S = CE.IP_COREG_HOURS * 3600, CE.IP_CODEP_HOURS * 3600
    _NONE = (None, None, None, None)
    for v, members in ipg.items():
        for cn in members:
            cust[cn].add("ip")
        for i in range(len(members)):                     # groups are capped at FAN_IP -> cheap
            for j in range(i + 1, len(members)):
                ca, cb = members[i], members[j]
                if ca == cb:
                    continue
                ra, da, cia, iba = cfact.get(ca, _NONE)
                rb, dbb, cib, ibb = cfact.get(cb, _NONE)
                if ra and rb and abs((ra - rb).total_seconds()) <= REG_S:
                    cust[ca].add("ip_coreg"); cust[cb].add("ip_coreg"); n_coreg += 1
                if da and dbb and abs((da - dbb).total_seconds()) <= DEP_S:
                    cust[ca].add("ip_codep"); cust[cb].add("ip_codep"); n_codep += 1
                # boosters on an IP-linked pair — this is what makes "IP + same city" a real (weak)
                # link instead of nothing, matching the popup. Baghdad is excluded (WEAK_CITIES).
                if cia and cia == cib and cia not in CE.WEAK_CITIES:
                    cust[ca].add("city"); cust[cb].add("city")
                if iba and iba == ibb:
                    cust[ca].add("ib"); cust[cb].add("ib")
    print(f"IP+timing: {n_coreg:,} same-IP co-registration pairs | {n_codep:,} same-IP co-deposit pairs")

    # same payment sender (same physical Qi card / wallet funding two different customers)
    cur.execute("""
        SELECT array_agg(DISTINCT c.customer_no)
        FROM client_payment_senders a JOIN clients c ON c.login = a.client_login
        WHERE c.customer_no IS NOT NULL
        GROUP BY a.method, a.sender_key
        HAVING COUNT(DISTINCT c.customer_no) BETWEEN 2 AND %s
    """, (FAN_PAY,))
    for (arr,) in cur.fetchall():
        for cn in arr:
            cust[cn].add("pay_sender")

    # similar email across clients + leads (normalised local part: dots/+tags removed), WITH the
    # COMMON-NAME GUARD: if the group's core is a common name / generic token, only the members that
    # ALSO share a city or an IB are linked — a bare ali1990/ali2005 match links nobody.
    nemail = CE._norm_email_sql("email")
    ecore = CE._norm_email_core_sql("email")
    cur.execute(f"""
        WITH ent AS (
            -- city = CANONICAL (build_city_canon.py) so Erbil/Arbil/Irbil are one place; Baghdad is
            -- blanked here because a mega-city can't corroborate a common name (see WEAK_CITIES).
            SELECT {nemail} AS nemail, {ecore} AS core, 'C'||customer_no AS ent,
                   customer_no AS cn, NULL::bigint AS lid,
                   lower(COALESCE(NULLIF(city_canon,''),'')) AS city, COALESCE(agent,0) AS ib
            FROM clients WHERE customer_no IS NOT NULL AND email IS NOT NULL AND email <> ''
            UNION ALL
            SELECT {nemail}, {ecore}, 'L'||id, NULL, id,
                   lower(COALESCE(NULLIF(city_canon,''),'')), 0
            FROM leads WHERE email IS NOT NULL AND email <> ''
        ), g AS (
            -- group on the CORE (digits stripped) so ahmedzaman1 / ahmedzaman2 are one family — the
            -- same rule score_connections uses, so the badge and the popup see the same email links.
            SELECT core FROM ent WHERE length(core) >= 4
            GROUP BY core HAVING COUNT(DISTINCT ent) BETWEEN 2 AND {FAN_EMAIL}
        )
        SELECT e.core, e.core, e.cn, e.lid, e.city, e.ib FROM ent e JOIN g USING (core)
    """)
    groups = defaultdict(list)
    for nem, core, cn, lid, city, ib in cur.fetchall():
        groups[nem].append((core, cn, lid, city, ib))

    guarded = 0
    for nem, members in groups.items():
        core = members[0][0]
        if CE.core_is_common(core, common_cores):
            # COMMON name -> require corroboration: keep only members sharing a city or an IB
            keep = set()
            for idx in (3, 4):                       # 3 = city (canonical), 4 = ib
                buckets = defaultdict(set)
                for m in members:
                    v = m[idx]
                    if not v:
                        continue
                    if idx == 3 and str(v).strip().lower() in CE.WEAK_CITIES:
                        continue                     # Baghdad is too big to corroborate a common name
                    buckets[v].add(("C", m[1]) if m[1] else ("L", m[2]))
                for ents in buckets.values():
                    if len(ents) >= 2:               # >=2 different people share email-core AND city/IB
                        keep |= ents
            if not keep:
                guarded += 1
            targets = keep
        else:
            targets = {(("C", m[1]) if m[1] else ("L", m[2])) for m in members}
        for kind, val in targets:
            if kind == "C":
                cust[val].add("similar_email")
            else:
                leads[val].add("similar_email")
    print(f"common-name guard: {len(common_cores):,} common cores | "
          f"{guarded:,} email groups dropped (common name, no city/IB corroboration)")
    return cust, leads


def main():
    # DEPRECATED: relation_engine.py is now the single source for network_score (plus is_nda, the
    # relation ledger and the state machine). This module lives on only as a library — relation_engine
    # imports build_common_cores / _add_columns / compute from it. A manual write here would clobber
    # the unified output, so it's gated behind --force.
    if "--dry-run" not in sys.argv and "--force" not in sys.argv:
        print("build_network_scores is DEPRECATED — use relation_engine.py. Re-run with --force to override.")
        return
    dry = "--dry-run" in sys.argv
    c = db_config.connect(); cur = c.cursor()
    # the common-name lookup is a derived cache the API also reads — always refresh it first
    common_cores = build_common_cores(cur); c.commit()
    cust, leads = compute(cur, common_cores)

    # score every customer / lead
    cust_rows = []
    dist = defaultdict(int)
    for cn, sigs in cust.items():
        s10, lvl, _, reason = CE.score_signals(sigs)
        cust_rows.append((cn, s10, lvl, reason)); dist[lvl] += 1
    lead_rows = []
    for lid, sigs in leads.items():
        s10, lvl, _, reason = CE.score_signals(sigs)
        lead_rows.append((lid, s10, lvl, reason))

    print(f"customers linked: {len(cust_rows)}  leads linked: {len(lead_rows)}")
    print("level distribution (customers):", dict(dist))

    if dry:
        print("\nDRY-RUN — nothing written.")
        c.close(); return

    # Only ALTER when a column is genuinely missing. `ADD COLUMN IF NOT EXISTS` is NOT free: it still
    # takes an AccessExclusiveLock, and queued behind the live TradeSoft sync's open transactions it
    # blocks every reader — i.e. this nightly job could freeze the whole API.
    _add_columns(cur, {"clients": _NET_COLS, "leads": _NET_COLS})

    # reset everyone to 0/none, then stamp the linked ones (so cleared links drop back to 0)
    cur.execute("UPDATE clients SET network_score=0, network_level='none', network_reason=NULL "
                "WHERE COALESCE(network_score,0) <> 0 OR network_level IS DISTINCT FROM 'none'")
    cur.execute("UPDATE leads SET network_score=0, network_level='none', network_reason=NULL "
                "WHERE COALESCE(network_score,0) <> 0 OR network_level IS DISTINCT FROM 'none'")

    # bulk write via a temp table joined back (customer -> all their logins)
    from psycopg2.extras import execute_values
    if cust_rows:
        cur.execute("CREATE TEMP TABLE _ns(cn TEXT, s10 INT, lvl TEXT, reason TEXT) ON COMMIT DROP")
        execute_values(cur, "INSERT INTO _ns(cn,s10,lvl,reason) VALUES %s",
                       [(str(cn), s10, lvl, reason) for cn, s10, lvl, reason in cust_rows])
        cur.execute("""UPDATE clients c SET network_score=_ns.s10, network_level=_ns.lvl,
                              network_reason=_ns.reason
                       FROM _ns WHERE c.customer_no = _ns.cn""")
    if lead_rows:
        cur.execute("CREATE TEMP TABLE _nl(lid BIGINT, s10 INT, lvl TEXT, reason TEXT) ON COMMIT DROP")
        execute_values(cur, "INSERT INTO _nl(lid,s10,lvl,reason) VALUES %s", lead_rows)
        cur.execute("""UPDATE leads l SET network_score=_nl.s10, network_level=_nl.lvl,
                              network_reason=_nl.reason
                       FROM _nl WHERE l.id = _nl.lid""")
    c.commit()
    # report
    cur.execute("SELECT COUNT(*) FROM clients WHERE COALESCE(network_score,0)>0")
    nc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM clients WHERE network_level='critical'")
    ncrit = cur.fetchone()[0]
    print(f"\nCOMMITTED: {nc} client rows scored >0 ({ncrit} critical/red), "
          f"{len(lead_rows)} leads. Every page now reads clients.network_score / leads.network_score.")
    c.close()


if __name__ == "__main__":
    main()
