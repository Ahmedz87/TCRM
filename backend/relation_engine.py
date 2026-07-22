"""
relation_engine.py — THE single source of "who is related to whom" for the whole CRM.

One engine feeds everything that used to compute relations on its own:
  • the Network/Connection page (the Related vs Unrelated tables + the x/10 badge + the popup),
  • NDA   (a depositor with NO relation is a genuinely-new deposit account),
  • the welcome-bonus check (a LEAD with a strong/family relation can't claim the $50 bonus),
  • (soon) the family engine feeds family_l1/l2 relations back into the SAME table.

ENTITY = one person on either side of the funnel:  ('C', customer_no) for a client, ('L', id) for a
lead. Leads live in the graph from day one, so a related lead is caught BEFORE it deposits.

SIGNAL TIERS (desk rule):
  DECISIVE  — same device (cid/mqid) or same payment wallet (Qi sender-name / ZainCash) or family L1.
              No discussion: the two are related, immediately, no 48h wait.
  EVALUATE  — similar-email (common-name-guarded), IP+timing (co-registration ±72h / co-deposit ±7d).
              Each already implies a real tie, so it stands alone.
  WEAK      — a bare shared IP, same city (not Baghdad), same IB. One alone means NOTHING; a pair is a
              relation only when 2+ of these fire together (e.g. IP + same city).
Bare IP alone, exact phone, common-name email alone → NOT a relation (all learned the hard way).

STATE MACHINE (per entity, recomputed each run; NDA stays REVOCABLE if a relative appears later):
  unfunded_clean  / unfunded_related        (a lead / a registered-but-not-funded client)
  on first deposit (FTD):
      decisive OR any relation     -> ftd_related        (NOT NDA)
      clean & FTD older than 48h   -> nda                (green — genuinely new)
      clean & FTD within 48h       -> ftd_pending        (yellow — still being checked)

Run:  python relation_engine.py            (compute + write everything; idempotent)
      python relation_engine.py --dry-run  (report only)
"""
import sys
from collections import defaultdict
import db_config
import connection_engine as CE
from build_network_scores import build_common_cores, _add_columns, FAN_DEVICE, FAN_IP, FAN_PAY, FAN_EMAIL

# POINTS model (desk rule Jul 2026). Every signal is worth points; a pair is a relation at >= 3
# points, OR on any DECISIVE signal. Built to keep genuine FTDs unless the evidence is real.
#   DECISIVE (instant): same device / MQID / payment wallet / direct family.
#   EMAIL by edit-distance of the name-part (email3/2/1 = 3/2/1 pts). Distinctive core: 0-2 letters
#     apart = 3 (same person), 3-4 = 2, 5 = 1. COMMON name core (ali/ahmad…): one tier weaker
#     (0-2 = 2, 3-4 = 1, 5+ = 0) — a common name barely differing is often a DIFFERENT person.
#   SHARED IP by COUNT (ip1/ip2/ip3 = 1/2/3 pts): sharing one IP is weak (mobile/NAT); sharing 3+
#     distinct IPs is a real connection on its own.
#   WEAK, 1 pt each: same city, same IB, same registration period, same first-deposit period.
DECISIVE_SIGNALS = {"cid", "mqid", "pay_sender", "family_l1"}
SIGNAL_POINTS = {
    "email3": 3, "email2": 2, "email1": 1, "family_l2": 3,
    "ip3": 3, "ip2": 2, "ip1": 1,
    "city": 1, "ib": 1, "reg_period": 1, "dep_period": 1,
}
RELATION_POINTS = 3
# IP-based ties (the validation-window carve-out below): a FRESH FTD linked to someone ONLY by these
# stays FTD (pending), not "related", for VALIDATION_HOURS — a shared IP in the first days is often
# coincidence. A non-IP tie (device/wallet/family/email/city) still flips it immediately.
IP_BASED = {"ip1", "ip2", "ip3", "reg_period", "dep_period"}
VALIDATION_HOURS = 48     # 2-DAY validation window (desk rule Jul 2026); the FTD-pending "yellow" duration
FTD_PENDING_HOURS = VALIDATION_HOURS
WEAK_IP_CLUSTER_MAX = 4   # city/IB corroborate an IP pair only in a household-sized cluster
# The weak "IP + same city / IP + same IB" link only makes sense for a HOUSEHOLD-sized IP cluster.
# A family shares one connection among 2-4 people; an IB office or an ISP/NAT pool has many, and
# "everyone in this Erbil office shares the IB" is NOT family — it would wrongly deny those genuinely
# new clients their NDA. So the city/IB boosters apply only when the IP is shared by <= this many.
# (The IP+timing signals are pairwise and stay regardless of cluster size.)
WEAK_IP_CLUSTER_MAX = 4


def _ek(kind, val):
    return f"{kind}{val}"


def _pair(a, b):
    return (a, b) if a < b else (b, a)


def signal_points(sigs):
    """Total relation points for a set of signal keys (decisive -> huge)."""
    s = set(sigs)
    if s & DECISIVE_SIGNALS:
        return 999
    return sum(SIGNAL_POINTS.get(x, 0) for x in s)


def edge_is_relation(sigs):
    """A pair is a real relation on any decisive signal, or once it reaches RELATION_POINTS."""
    return signal_points(sigs) >= RELATION_POINTS


# IB NDA GRANDFATHER (desk rule Jul 17 2026): an IB's NDA credit already earned shouldn't be clawed
# back by a rule change. So for IB-referred customers whose FTD is BEFORE this cutoff, the NDA decision
# ignores the shared-IP WEIGHTING (ip2/ip3 count as just 1, the pre-shared-IP "3-factor" rule) — the
# ~155 that shared-IP demoted keep their NDA, restoring IB NDA to 833. FTDs from the cutoff onward get
# the full rule. Non-IB NDA is unaffected. Grandfathered customers still SHOW as related on the network;
# only clients.is_nda is preserved.
import datetime as _dt_gf
IB_NDA_CUTOFF = _dt_gf.datetime(2026, 7, 17)

def edge_is_relation_capped(sigs):
    """Relation test with the shared-IP WEIGHTING removed (ip2/ip3 -> 1) — the pre-shared-IP rule."""
    s = set(sigs)
    if s & DECISIVE_SIGNALS:
        return True
    return sum((1 if x in ("ip2", "ip3") else SIGNAL_POINTS.get(x, 0)) for x in s) >= RELATION_POINTS


def compute_edges(cur, common_cores):
    """Return (ent_sigs, edges):
       ent_sigs : entity-key -> set(signal)        (drives the x/10 badge, same as before)
       edges    : {(a,b): {signal: value}}         (only pairs that ARE relations; the ledger)"""
    ent_sigs = defaultdict(set)
    edges = defaultdict(dict)

    def add_edge(a, b, sig, val):
        p = _pair(a, b)
        edges[p][sig] = str(val)[:60]

    def add_group(members, sig, valfn=lambda m: ""):
        """members: list of entity-keys sharing this signal -> mark each + connect every pair."""
        for e in members:
            ent_sigs[e].add(sig)
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                add_edge(members[i], members[j], sig, valfn(members[i]))

    # ── DECISIVE: device cid/mqid (clients only) ──
    for typ, fan in (("cid", FAN_DEVICE), ("mqid", FAN_DEVICE)):
        cur.execute("""
            SELECT ai.identifier_value, array_agg(DISTINCT c.customer_no)
            FROM account_identifiers ai JOIN clients c ON c.login = ai.login
            WHERE ai.identifier_type=%s AND ai.identifier_value NOT IN ('0','') AND c.customer_no IS NOT NULL
            GROUP BY ai.identifier_value HAVING COUNT(DISTINCT c.customer_no) BETWEEN 2 AND %s
        """, (typ, fan))
        for val, arr in cur.fetchall():
            members = [_ek("C", cn) for cn in arr]
            for e in members:
                ent_sigs[e].add(typ)
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    add_edge(members[i], members[j], typ, val)

    # ── DECISIVE: same payment wallet (Qi sender-name / ZainCash), fan-out capped ──
    cur.execute("""
        SELECT a.method, a.sender_key, array_agg(DISTINCT c.customer_no)
        FROM client_payment_senders a JOIN clients c ON c.login = a.client_login
        WHERE c.customer_no IS NOT NULL
        GROUP BY a.method, a.sender_key HAVING COUNT(DISTINCT c.customer_no) BETWEEN 2 AND %s
    """, (FAN_PAY,))
    for method, key, arr in cur.fetchall():
        members = [_ek("C", cn) for cn in arr]
        add_group(members, "pay_sender", lambda m, v=f"{method}:{key}": v)

    # ── EVALUATE: IP with TIMING / city / IB corroboration (bare IP is NOT stored) ──
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
            WHERE ai.identifier_type='ip' AND ai.identifier_value NOT IN ('0','') AND c.customer_no IS NOT NULL
        ), sh AS (SELECT v FROM tok GROUP BY v HAVING COUNT(DISTINCT cn) BETWEEN 2 AND %s)
        SELECT t.v, t.cn FROM tok t JOIN sh USING (v)
    """, (FAN_IP,))
    ipg = defaultdict(list)
    for v, cn in cur.fetchall():
        ipg[v].append(cn)
    REG_S, DEP_S = CE.IP_COREG_HOURS * 3600, CE.IP_CODEP_HOURS * 3600
    _NONE = (None, None, None, None)
    # count DISTINCT shared IPs per customer pair (ip1/ip2/ip3) + whether any shared IP is a
    # household-sized cluster (only then may same city / same IB corroborate the pair).
    pair_ips = defaultdict(set)
    pair_small = set()
    for v, members in ipg.items():
        small = len(members) <= WEAK_IP_CLUSTER_MAX
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                ca, cb = members[i], members[j]
                if ca == cb:
                    continue
                key = (ca, cb) if ca < cb else (cb, ca)
                pair_ips[key].add(v)
                if small:
                    pair_small.add(key)
    n_reg = n_dep = 0
    for (ca, cb), ipset in pair_ips.items():
        cnt = len(ipset)
        ra, da, cia, iba = cfact.get(ca, _NONE)
        rb, dbb, cib, ibb = cfact.get(cb, _NONE)
        sigs = {("ip%d" % min(3, cnt)): (f"{cnt} shared IPs" if cnt > 1 else next(iter(ipset)))}
        if ra and rb and abs((ra - rb).total_seconds()) <= REG_S:
            sigs["reg_period"] = str(ra)[:16]; n_reg += 1
        if da and dbb and abs((da - dbb).total_seconds()) <= DEP_S:
            sigs["dep_period"] = str(da)[:16]; n_dep += 1
        if (ca, cb) in pair_small and cia and cia == cib and cia not in CE.WEAK_CITIES:
            sigs["city"] = cia
        if (ca, cb) in pair_small and iba and iba == ibb:
            sigs["ib"] = str(iba)
        # record only if it reaches RELATION_POINTS (3): 1 shared IP + one other is NOT enough;
        # 3+ shared IPs, or 2 IPs + one factor, or IP + city + period, is.
        if edge_is_relation(sigs.keys()):
            ea, eb = _ek("C", ca), _ek("C", cb)
            for cn in (ca, cb):
                for s in sigs:
                    ent_sigs[_ek("C", cn)].add(s)
            for s, val in sigs.items():
                add_edge(ea, eb, s, val)

    # ── EMAIL: distance-tiered similar email (see SIGNAL_POINTS: email3/email2/email1) ──
    # letters-different tier -> points.  Distinctive core: 0-2=3, 3-4=2, 5=1.  Common core (one tier
    # weaker): 0-2=2, 3-4=1, 5+=0.  A common name barely differing is often a DIFFERENT person.
    def email_sig(dist, common):
        d = 0 if dist <= 2 else (3 if dist <= 4 else 5)
        pts = {0: 3, 3: 2, 5: 1}[d] - (1 if common else 0)
        return ("email%d" % pts) if pts >= 1 else None

    nemail = CE._norm_email_sql("email")
    ecore = CE._norm_email_core_sql("email")
    # entity -> core + city + ib (one representative row per entity)
    cur.execute(f"""
        SELECT 'C'||customer_no, {ecore}, lower(COALESCE(NULLIF(city_canon,''),'')), COALESCE(agent,0)
        FROM clients WHERE customer_no IS NOT NULL AND email IS NOT NULL AND email <> ''
        UNION ALL
        SELECT 'L'||id, {ecore}, lower(COALESCE(NULLIF(city_canon,''),'')), 0
        FROM leads WHERE email IS NOT NULL AND email <> ''
    """)
    core_ents = defaultdict(list)     # core -> [(ent, city, ib)]
    for ent, core, city, ib in cur.fetchall():
        if core and len(core) >= 4:
            core_ents[core].append((ent, city, ib))

    def link_group(a_list, b_list, dist, common, same_core):
        """emit the email edge for every entity in a_list × b_list at this distance tier."""
        sig = email_sig(dist, common)
        if not sig:
            return 0
        n = 0
        for ea, cia, iba in a_list:
            for eb, cib, ibb in (a_list if same_core else b_list):
                if same_core and eb <= ea:
                    continue
                if ea == eb:
                    continue
                sigs = {sig: ""}
                # a common-name email still needs corroboration; give it the city/ib if they match
                if cia and cia == cib and cia not in CE.WEAK_CITIES:
                    sigs["city"] = cia
                if iba and iba == ibb:
                    sigs["ib"] = str(iba)
                if edge_is_relation(sigs.keys()):
                    for e in (ea, eb):
                        for s in sigs:
                            ent_sigs[e].add(s)
                    for s, val in sigs.items():
                        add_edge(ea, eb, s, val)
                    n += 1
        return n

    # (A) EXACT core (distance 0), fan-out capped like before
    n_email = 0
    for core, members in core_ents.items():
        if not (2 <= len(members) <= FAN_EMAIL):
            continue
        n_email += link_group(members, None, 0, CE.core_is_common(core, common_cores), True)

    # (B) FUZZY cross-core matching is DISABLED. On this data it false-matched different people whose
    # emails merely share a common NAME STEM (ahmed…/mustafa…/apple…) — the levenshtein distance is
    # small because the common prefix dominates, and those stems aren't caught by the exact-name
    # common-core guard. It produced ~184k bogus email edges and crashed NDA. Needs a stem-aware
    # approach (compare only the DISTINCTIVE remainder) before it can be turned back on.
    n_fuzzy = 0

    print(f"IP+timing: {n_reg:,} co-registration | {n_dep:,} co-deposit pairs | "
          f"email edges: exact {n_email:,} (fuzzy disabled)")

    # ── FAMILY (level 1/2) — read from the families table if the family engine committed it ──
    try:
        cur.execute("SELECT to_regclass('public.entity_family')")
        if cur.fetchone()[0]:
            cur.execute("SELECT ent_a, ent_b, level, value FROM entity_family")
            for a, b, lvl, val in cur.fetchall():
                sig = "family_l1" if lvl == 1 else "family_l2"
                ent_sigs[a].add(sig); ent_sigs[b].add(sig)
                add_edge(a, b, sig, val or "")
    except Exception:
        cur.connection.rollback()

    # keep only edges that qualify as a real relation
    edges = {p: s for p, s in edges.items() if edge_is_relation(s)}
    return ent_sigs, edges


_ES_COLS = {"clients": {"network_score": "INT", "network_level": "TEXT", "network_reason": "TEXT",
                        "relation_state": "TEXT", "is_nda": "BOOLEAN", "nda_at": "TIMESTAMPTZ"},
            "leads":   {"network_score": "INT", "network_level": "TEXT", "network_reason": "TEXT",
                        "relation_state": "TEXT"}}


# ── NDA lot qualification (desk rule Jul 2026) ──────────────────────────────────────────────────
# A genuine NDA must not only be a relation-free unique FTD — the client must actually TRADE at least
# NDA_MIN_LOTS standard lots on GOLD (XAU) or FX (currency pairs), summed across ALL their accounts.
# Below the minimum they are a YELLOW "pending NDA" (relation_state='nda_pending'): shown + nudged,
# but is_nda=FALSE so they are NOT counted for promotion until they reach the floor. Crypto, indices,
# oil, silver (XAG) and single stocks do NOT count toward the lot minimum.
NDA_MIN_LOTS = 1.0
GOLD_FX_WHERE = (
    "(UPPER(d.symbol) LIKE 'XAU%' OR UPPER(d.symbol) ~ "
    "'^(AUD|CAD|CHF|CNH|DKK|EUR|GBP|HKD|JPY|MXN|NOK|NZD|PLN|SEK|SGD|TRY|USD|ZAR)"
    "(AUD|CAD|CHF|CNH|DKK|EUR|GBP|HKD|JPY|MXN|NOK|NZD|PLN|SEK|SGD|TRY|USD|ZAR)')"
)


def gold_fx_lots(cur):
    """Per-customer total GOLD+FX lots (MT4 volume is already lots; MT5 lots = volume/10000)."""
    cur.execute(f"""
        SELECT c.customer_no,
               SUM(CASE WHEN d.platform='MT4' THEN d.volume ELSE d.volume/10000.0 END)
        FROM deals d JOIN clients c ON c.login = d.login
        WHERE d.action IN (0,1) AND d.volume > 0 AND c.customer_no IS NOT NULL AND {GOLD_FX_WHERE}
        GROUP BY c.customer_no""")
    return {str(cn): float(l or 0) for cn, l in cur.fetchall()}


def _state_and_bonus(sigs, related, funded, ftd_ts, now):
    """Return (relation_state, is_nda, bonus_status) for one entity."""
    has_decisive = bool(sigs & DECISIVE_SIGNALS)
    has_family = bool(sigs & {"family_l1", "family_l2"})
    if not funded:
        state = "unfunded_related" if related else "unfunded_clean"
        is_nda = None
        bonus = "blocked" if (has_decisive or has_family) else ("review" if related else "eligible")
        return state, is_nda, bonus
    # funded (has an FTD)
    fresh = ftd_ts and (now - ftd_ts).total_seconds() <= VALIDATION_HOURS * 3600
    if related:
        # VALIDATION-WINDOW carve-out: a FRESH FTD whose ONLY tie is IP-based (shared IP / same
        # period) is held as FTD-pending, NOT flipped to related — a shared IP in the first days is
        # often coincidence. A non-IP tie (device/wallet/family/email/city) still flips immediately.
        if fresh and sigs and sigs <= IP_BASED:
            return "ftd_pending", False, "funded"
        return "ftd_related", False, "funded"
    if fresh:
        return "ftd_pending", False, "funded"      # yellow — still inside the validation window
    return "nda", True, "funded"                    # green — genuinely new deposit account


def main():
    import datetime as _dt
    dry = "--dry-run" in sys.argv
    now = _dt.datetime.utcnow()
    c = db_config.connect(); cur = c.cursor()

    # keep the FTD date current first (drives the NDA state machine) — was inside nda_engine
    if not dry:
        try:
            import nda_engine
            n = nda_engine.backfill_ftd(cur); c.commit()
            print(f"backfilled first_deposit_at for {n} client rows")
        except Exception:
            c.rollback()

    common_cores = build_common_cores(cur); c.commit()
    ent_sigs, edges = compute_edges(cur, common_cores)

    # effective per-entity signals + related-set come ONLY from kept edges (so a bare-IP entity with
    # no qualifying edge is NOT related and scores 0 — badge, is_related and ledger all agree).
    ent_eff = defaultdict(set)
    n_related = defaultdict(int)
    for (a, b), sigs in edges.items():
        for s in sigs:
            ent_eff[a].add(s); ent_eff[b].add(s)
        n_related[a] += 1; n_related[b] += 1

    # IB NDA grandfather inputs: which entities are still related under the CAPPED (pre-shared-IP)
    # rule, plus each customer's referring agent + the IB agent set.
    capped_related = set()
    for (a, b), sigs in edges.items():
        if edge_is_relation_capped(sigs):
            capped_related.add(a); capped_related.add(b)
    cur.execute("SELECT agent_id FROM ibs WHERE agent_id IS NOT NULL")
    ib_set = {r[0] for r in cur.fetchall()}
    # attribute each customer to their FTD-ACCOUNT's agent — the SAME rule the IB NDA count uses,
    # so the grandfather restores exactly the IB customers the shared-IP rule demoted.
    cur.execute("""SELECT DISTINCT ON (customer_no) customer_no, COALESCE(agent,0)
                   FROM clients WHERE customer_no IS NOT NULL
                   ORDER BY customer_no, NULLIF(first_deposit_at,'') ASC NULLS LAST""")
    cagent = {cn: ag for cn, ag in cur.fetchall()}
    n_grandfathered = 0

    # funded / FTD facts per client customer_no + a display name per customer
    cur.execute("""SELECT customer_no, BOOL_OR(COALESCE(total_deposits,0)>0),
                          MIN(NULLIF(first_deposit_at,''))
                   FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no""")
    cfund = {}
    for cn, dep, fda in cur.fetchall():
        cfund[cn] = (bool(dep), CE._ts(fda))
    clut = gold_fx_lots(cur)   # per-customer Gold+FX lots -> the NDA 1.0-lot qualification gate
    cur.execute("""SELECT DISTINCT ON (customer_no) customer_no, name FROM clients
                   WHERE customer_no IS NOT NULL AND name IS NOT NULL
                   ORDER BY customer_no, length(name) DESC NULLS LAST""")
    cname = {("C" + str(cn)): nm for cn, nm in cur.fetchall()}
    cur.execute("SELECT id, full_name FROM leads WHERE full_name IS NOT NULL")
    for lid, nm in cur.fetchall():
        cname["L" + str(lid)] = nm

    def _nameof(ent):
        return cname.get(ent) or ent

    # build per-entity status rows
    status = []        # (ent, kind, related, decisive, n_rel, score, level, reason, state, is_nda, bonus)
    dist = defaultdict(int)
    cust_net = []      # (customer_no, score, level, reason, state, is_nda)
    lead_net = []      # (lead_id, score, level, reason, state)
    for ent, sigs in ent_eff.items():
        is_client, val = ent[0] == "C", ent[1:]
        kind = "client" if is_client else "lead"
        s10, lvl, _, reason = CE.score_signals(sigs)
        related = True
        funded, ftd_ts = cfund.get(val, (False, None)) if is_client else (False, None)
        state, is_nda, bonus = _state_and_bonus(sigs, related, funded, ftd_ts, now)
        # IB NDA GRANDFATHER: a pre-cutoff IB FTD that is related ONLY because of the shared-IP
        # weighting (related in full, but NOT under the capped/3-factor rule) keeps its NDA credit.
        if (is_client and state == "ftd_related" and funded and ftd_ts and ftd_ts < IB_NDA_CUTOFF
                and cagent.get(val) in ib_set and ent not in capped_related):
            is_nda = True; n_grandfathered += 1
        # NDA 1.0-lot gate: a would-be green NDA that hasn't traded the Gold+FX lot minimum is held
        # as a YELLOW 'nda_pending' (not counted) until the client trades enough.
        if is_client and is_nda and clut.get(str(val), 0.0) < NDA_MIN_LOTS:
            state, is_nda = "nda_pending", False
        dist[state] += 1
        status.append((ent, _nameof(ent), kind, related, bool(sigs & DECISIVE_SIGNALS), n_related[ent],
                       s10, lvl, reason, state, is_nda, bonus))
        if is_client:
            cust_net.append((val, s10, lvl, reason, state, is_nda, clut.get(str(val), 0.0)))
        else:
            lead_net.append((int(val), s10, lvl, reason, state))

    # UNRELATED entities that are funded still need an NDA/state — a clean depositor IS the NDA case.
    # We compute their state directly from cfund (no edges).
    related_custs = {e[1:] for e in ent_eff if e[0] == "C"}
    nda_clean = ftd_pending_clean = 0
    for cn, (funded, ftd_ts) in cfund.items():
        if cn in related_custs or not funded:
            continue
        state, is_nda, _ = _state_and_bonus(set(), False, True, ftd_ts, now)
        # NDA 1.0-lot gate (same as above): clean depositor below the Gold+FX lot floor = pending.
        if is_nda and clut.get(str(cn), 0.0) < NDA_MIN_LOTS:
            state, is_nda = "nda_pending", False
        dist[state] += 1
        cust_net.append((cn, 0, "none", None, state, is_nda, clut.get(str(cn), 0.0)))
        if state == "nda": nda_clean += 1
        else: ftd_pending_clean += 1

    print(f"entities in a relation: {len(ent_eff):,} | relation edges: {len(edges):,}")
    print(f"state distribution: {dict(dist)} | IB grandfathered back to NDA: {n_grandfathered:,}")

    if dry:
        # PREVIEW: compare the NEW rule against what's committed now, and show the FTDs that flip
        # back to NDA (were 'related' under the old 2-factor rule, are clean under the new one).
        new_ftd_related = {e[1:] for (e, nm, k, rel, dec, nr, sc, lv, rs, st, nd, bo) in status
                           if k == "client" and st == "ftd_related"}
        new_nda = {e[1:] for (e, nm, k, rel, dec, nr, sc, lv, rs, st, nd, bo) in status
                   if k == "client" and st == "nda"} | \
                  {cn for cn, (f, t) in cfund.items() if f and cn not in
                   {e[1:] for e in ent_eff if e[0] == "C"}}
        cur.execute("""SELECT ent, name, top_reason FROM entity_status
                       WHERE kind='client' AND relation_state='ftd_related'""")
        cur_related = {r[0][1:]: (r[1], r[2]) for r in cur.fetchall()}
        cur_nda = cur.execute if False else None
        cur.execute("SELECT COUNT(DISTINCT customer_no) FROM clients WHERE is_nda")
        cur_nda_n = cur.fetchone()[0]
        flips = [cn for cn in cur_related if cn not in new_ftd_related]
        print("\n" + "=" * 70)
        print("PREVIEW — 3-factor rule vs the current live data")
        print(f"  FTD-related (not NDA):   now {len(cur_related):,}  ->  after {len(new_ftd_related):,}"
              f"   ({len(flips):,} move back to NDA)")
        print(f"  NDA (green):             now {cur_nda_n:,}  ->  after ~{cur_nda_n + len(flips):,}")
        print(f"\n  10 example FTDs that FLIP back to NDA (were related only by 2 weak factors):")
        for cn in flips[:10]:
            nm, reason = cur_related[cn]
            print(f"    {(nm or cn)[:34]:34}  was: {reason}")
        print("=" * 70)
        print("\nDRY-RUN — nothing written. Re-run without --dry-run to APPLY the 3-factor rule.")
        c.close(); return

    # The clients table is written concurrently by the live TradeSoft sync, so our big UPDATEs can
    # deadlock against it. Fail fast (lock_timeout) and retry the whole atomic write a few times.
    import time as _time
    for attempt in range(1, 6):
        try:
            cur.execute("SET lock_timeout = '20s'")
            _write(c, cur, edges, status, cust_net, lead_net)
            break
        except Exception as e:
            c.rollback()
            cls = e.__class__.__name__
            if cls in ("DeadlockDetected", "LockNotAvailable") and attempt < 5:
                print(f"  write attempt {attempt} hit {cls}; retrying in {attempt*3}s…")
                _time.sleep(attempt * 3); continue
            raise

    # ── Auto-resolve stale NDA disputes (desk rule Jul 2026) ────────────────────────────────────
    # A "Review?" an IB raised resolves ONCE the engine reaches a FINAL answer: relation_state 'nda'
    # (genuinely new) → approved; 'ftd_related' (linked to an existing client) → rejected. Reviews on
    # accounts still inside the 2-day validation window ('ftd_pending') or waiting on the 1.0-lot floor
    # ('nda_pending') stay pending. Fixes disputes that lingered "under review" forever (e.g. 5007752).
    cur.execute("SELECT to_regclass('public.ib_nda_reviews')")
    if cur.fetchone()[0]:
        cur.execute("""
            UPDATE ib_nda_reviews r
            SET status = CASE WHEN c.is_nda THEN 'approved' ELSE 'rejected' END,
                reviewed_by = 'auto', reviewed_at = NOW()
            FROM clients c
            WHERE r.status = 'pending' AND c.login = r.login
              AND c.relation_state IN ('nda', 'ftd_related')
        """)
        n_rev = cur.rowcount
        c.commit()
        print(f"NDA disputes auto-resolved (final relation state reached): {n_rev:,}")

    cur.execute("SELECT COUNT(*) FROM entity_status WHERE is_related")
    rel = cur.fetchone()[0]
    cur.execute("SELECT relation_state, COUNT(*) FROM entity_status GROUP BY 1 ORDER BY 2 DESC")
    print(f"\nCOMMITTED. entity_status: {rel:,} related | states:", dict(cur.fetchall()))
    print(f"NDA (clean depositors): {nda_clean:,} | FTD-pending (<48h): {ftd_pending_clean:,}")
    c.close()


def _write(c, cur, edges, status, cust_net, lead_net):
    # ── schema (ALTER only if missing — see _add_columns) ──
    _add_columns(cur, _ES_COLS)
    cur.execute("""CREATE TABLE IF NOT EXISTS entity_relations(
        ent_a TEXT, ent_b TEXT, signals TEXT[], decisive BOOLEAN, strength TEXT,
        top_reason TEXT, n_signals INT, first_seen TIMESTAMPTZ DEFAULT NOW(),
        last_seen TIMESTAMPTZ DEFAULT NOW(), PRIMARY KEY(ent_a, ent_b))""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_er_a ON entity_relations(ent_a)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_er_b ON entity_relations(ent_b)")
    cur.execute("""CREATE TABLE IF NOT EXISTS entity_status(
        ent TEXT PRIMARY KEY, name TEXT, kind TEXT, is_related BOOLEAN, has_decisive BOOLEAN, n_related INT,
        network_score INT, network_level TEXT, top_reason TEXT, relation_state TEXT,
        is_nda BOOLEAN, bonus_status TEXT, updated_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("ALTER TABLE entity_status ADD COLUMN IF NOT EXISTS name TEXT")
    cur.execute("ALTER TABLE entity_status ADD COLUMN IF NOT EXISTS latest_at TIMESTAMPTZ")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_es_state ON entity_status(relation_state)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_es_related ON entity_status(is_related)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_es_latest ON entity_status(latest_at DESC NULLS LAST)")
    c.commit()

    from psycopg2.extras import execute_values
    # entity_relations: upsert current edges (preserve first_seen), then delete the stale ones
    er_rows = []
    for (a, b), sigs in edges.items():
        keys = list(sigs.keys())
        dec = bool(set(keys) & DECISIVE_SIGNALS)
        er_rows.append((a, b, keys, dec, "decisive" if dec else "evaluate",
                        CE.top_reason(set(keys)), len(keys)))
    cur.execute("""CREATE TEMP TABLE _er(ent_a TEXT, ent_b TEXT, signals TEXT[], decisive BOOL,
                   strength TEXT, top_reason TEXT, n_signals INT) ON COMMIT DROP""")
    execute_values(cur, "INSERT INTO _er VALUES %s", er_rows, page_size=2000)
    cur.execute("""INSERT INTO entity_relations(ent_a,ent_b,signals,decisive,strength,top_reason,n_signals)
                   SELECT ent_a,ent_b,signals,decisive,strength,top_reason,n_signals FROM _er
                   ON CONFLICT (ent_a,ent_b) DO UPDATE SET signals=EXCLUDED.signals,
                     decisive=EXCLUDED.decisive, strength=EXCLUDED.strength,
                     top_reason=EXCLUDED.top_reason, n_signals=EXCLUDED.n_signals, last_seen=NOW()""")
    cur.execute("""DELETE FROM entity_relations er
                   WHERE NOT EXISTS (SELECT 1 FROM _er t WHERE t.ent_a=er.ent_a AND t.ent_b=er.ent_b)""")

    # entity_status: full rebuild (current snapshot)
    cur.execute("TRUNCATE entity_status")
    execute_values(cur, """INSERT INTO entity_status
        (ent,name,kind,is_related,has_decisive,n_related,network_score,network_level,top_reason,
         relation_state,is_nda,bonus_status) VALUES %s""",
        list(status), page_size=2000)
    # latest_at = when this entity's MOST-RECENT relation was first caught (drives "newest first" sort;
    # first_seen is preserved by the upsert above, so a freshly-caught tie floats to the top of the table)
    cur.execute("""UPDATE entity_status es SET latest_at = sub.mx FROM (
                       SELECT ent, MAX(first_seen) mx FROM (
                           SELECT ent_a AS ent, first_seen FROM entity_relations
                           UNION ALL SELECT ent_b, first_seen FROM entity_relations) u
                       GROUP BY ent) sub WHERE es.ent = sub.ent""")

    # ── back-compat: keep clients/leads.network_score + is_nda so every existing page still works ──
    cur.execute("UPDATE clients SET network_score=0, network_level='none', network_reason=NULL, "
                "relation_state=NULL, is_nda=NULL "
                "WHERE COALESCE(network_score,0)<>0 OR network_level IS DISTINCT FROM 'none' "
                "OR relation_state IS NOT NULL OR is_nda IS NOT NULL")
    cur.execute("UPDATE leads SET network_score=0, network_level='none', network_reason=NULL, "
                "relation_state=NULL WHERE COALESCE(network_score,0)<>0 "
                "OR network_level IS DISTINCT FROM 'none' OR relation_state IS NOT NULL")
    if cust_net:
        cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS nda_lots DOUBLE PRECISION")
        cur.execute("""CREATE TEMP TABLE _cn(cn TEXT, s INT, lv TEXT, rs TEXT, st TEXT, nd BOOLEAN,
                       lt DOUBLE PRECISION) ON COMMIT DROP""")
        execute_values(cur, "INSERT INTO _cn VALUES %s",
                       [(str(cn), s, lv, rs, st, nd, lt) for cn, s, lv, rs, st, nd, lt in cust_net], page_size=2000)
        cur.execute("""UPDATE clients c SET network_score=_cn.s, network_level=_cn.lv,
                          network_reason=_cn.rs, relation_state=_cn.st, is_nda=_cn.nd, nda_lots=_cn.lt,
                          nda_at=CASE WHEN _cn.nd THEN NOW() ELSE nda_at END
                       FROM _cn WHERE c.customer_no=_cn.cn""")
    if lead_net:
        cur.execute("CREATE TEMP TABLE _ln(lid BIGINT, s INT, lv TEXT, rs TEXT, st TEXT) ON COMMIT DROP")
        execute_values(cur, "INSERT INTO _ln VALUES %s", lead_net, page_size=2000)
        cur.execute("""UPDATE leads l SET network_score=_ln.s, network_level=_ln.lv,
                          network_reason=_ln.rs, relation_state=_ln.st
                       FROM _ln WHERE l.id=_ln.lid""")
    c.commit()


if __name__ == "__main__":
    main()
