"""
ib_self_related.py — anti-abuse: an IB must not farm commission on their OWN trading accounts,
or on accounts 100%-related to them. Desk rule (user, Jul 2026):

  • SELF     = a trading account that is the SAME person as the IB (same clients.customer_no, or
               same email, as the IB's own agent login).
  • RELATED  = a trading account with a DECISIVE "10/10" link to the IB (entity_relations.decisive:
               shared device CID/MQID, family, or the same payment wallet).  See relation_engine.py.

While the IB is at LEVEL 5 or 6, trades on such accounts earn ZERO commission. Once promoted to
LEVEL 7 the account earns normally (the IB has proven to be a genuine IB).

FORWARD-ONLY (user, Jul 2026): only trades CLOSED on/after SELF_ZERO_START are zeroed — commission
already earned before go-live is untouched. Level 5 IBs also cannot withdraw/transfer until promoted
to level 6, so nothing was paid out on the pre-go-live self/related commission anyway.

`build(cur)` writes the persistent `ib_self_related(ib_id, login, kind, reason, ib_level)` table
(one row per self/related trading account under an L5-10 IB). ib_trades.main() calls it, then zeroes
the L5/L6 forward trades; get_ib reads it to badge accounts in the portal. Run this file directly for
a READ-ONLY impact report (builds into a temp table + rolls back — writes nothing).
"""
import sys, io

# go-live date for the forward-only rule (trades closed on/after this earn $0 on self/related accts at L5/L6)
SELF_ZERO_START = "2026-07-19"

# ── the ONE definition, shared by the impact report and the live build ──────────────────────────
# entity_relations entities are 'C'||customer_no (client) / 'L'||lead_id (lead); decisive = a 10/10 link.
_SQL_BODY = """
    WITH ibid AS (
        SELECT ib.id AS ib_id, ib.ib_level,
               LOWER(NULLIF(ib.email,''))  AS ib_email,
               cc.customer_no              AS ib_cust
        FROM ibs ib
        LEFT JOIN clients cc ON cc.login = ib.agent_id
        WHERE ib.ib_level BETWEEN 5 AND 10
    ),
    cand AS (   -- every trading account under each IB, with its own identity
        SELECT DISTINCT t.ib_id, t.login,
               c.customer_no             AS login_cust,
               LOWER(NULLIF(c.email,'')) AS login_email
        FROM ib_trades t
        JOIN clients c ON c.login = t.login
    )
    SELECT ca.ib_id, ca.login, ib.ib_level,
        CASE WHEN (ib.ib_cust  IS NOT NULL AND ca.login_cust  = ib.ib_cust)
               OR (ib.ib_email IS NOT NULL AND ca.login_email = ib.ib_email)
             THEN 'self' ELSE 'related' END AS kind,
        CASE WHEN (ib.ib_cust  IS NOT NULL AND ca.login_cust  = ib.ib_cust)  THEN 'Same customer as the IB'
             WHEN (ib.ib_email IS NOT NULL AND ca.login_email = ib.ib_email) THEN 'Same email as the IB'
             ELSE COALESCE((
                    SELECT er.top_reason FROM entity_relations er
                    WHERE er.decisive
                      AND ( (er.ent_a = 'C'||ib.ib_cust AND er.ent_b = 'C'||ca.login_cust)
                         OR (er.ent_b = 'C'||ib.ib_cust AND er.ent_a = 'C'||ca.login_cust) )
                    LIMIT 1), '100% related to the IB') END AS reason
    FROM cand ca
    JOIN ibid ib USING (ib_id)
    WHERE
        -- SELF: same person as the IB
        (ib.ib_cust  IS NOT NULL AND ca.login_cust  = ib.ib_cust)
     OR (ib.ib_email IS NOT NULL AND ca.login_email = ib.ib_email)
        -- RELATED: a decisive 10/10 link between the IB's customer and this account's customer
     OR ( ib.ib_cust IS NOT NULL AND ca.login_cust IS NOT NULL AND EXISTS (
            SELECT 1 FROM entity_relations er
            WHERE er.decisive
              AND ( (er.ent_a = 'C'||ib.ib_cust AND er.ent_b = 'C'||ca.login_cust)
                 OR (er.ent_b = 'C'||ib.ib_cust AND er.ent_a = 'C'||ca.login_cust) ) ) )
"""


def build(cur, table="ib_self_related", temp=False):
    """(Re)build the self/related table with a psycopg2 cursor. Returns (total, n_self, n_related)."""
    kw = "TEMP TABLE" if temp else "TABLE"
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(f"CREATE {kw} {table} AS {_SQL_BODY}")
    cur.execute(f"CREATE INDEX ix_{table}_iblogin ON {table}(ib_id, login)")
    cur.execute(f"CREATE INDEX ix_{table}_login   ON {table}(login)")
    cur.execute(f"SELECT COUNT(*), COUNT(*) FILTER (WHERE kind='self'), COUNT(*) FILTER (WHERE kind='related') FROM {table}")
    return cur.fetchone()


def _report():
    """READ-ONLY: build into a temp table, print the impact, roll back. Writes nothing."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    import db_config
    cn = db_config.connect(); cn.autocommit = False; cur = cn.cursor()
    total, n_self, n_rel = build(cur, table="_ibsr_tmp", temp=True)
    print(f"self/related trading accounts under L5-10 IBs: {total:,}  (self {n_self:,}, related {n_rel:,})")

    # how many are under L5/L6 IBs (the pool the ZERO rule applies to)
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT ib_id) FROM _ibsr_tmp WHERE ib_level BETWEEN 5 AND 6")
    n_l56, ibs_l56 = cur.fetchone()
    print(f"  under LEVEL 5/6 IBs (rule applies): {n_l56:,} accounts across {ibs_l56:,} IBs")
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT ib_id) FROM _ibsr_tmp WHERE ib_level >= 7")
    n_l7, ibs_l7 = cur.fetchone()
    print(f"  under LEVEL 7+ IBs (exempt, still earn): {n_l7:,} accounts across {ibs_l7:,} IBs")

    # commission already earned on those accounts, split by era vs the forward window
    cur.execute(f"""
        SELECT
          ROUND(SUM(t.commission)::numeric,2)                                                       AS all_time,
          ROUND(SUM(t.commission) FILTER (WHERE t.close_time >= '{SELF_ZERO_START}')::numeric,2)     AS forward,
          ROUND(SUM(t.commission) FILTER (WHERE t.close_time <  '{SELF_ZERO_START}')::numeric,2)     AS pre_golive,
          ROUND(SUM(t.commission) FILTER (WHERE t.close_time >= (DATE '{SELF_ZERO_START}' - 30))::numeric,2) AS last_30d_illustration
        FROM ib_trades t
        JOIN _ibsr_tmp s ON s.ib_id = t.ib_id AND s.login = t.login
        WHERE t.eligible AND t.ib_level BETWEEN 5 AND 6
    """)
    at, fwd, pre, l30 = cur.fetchone()
    print("\nCOMMISSION on L5/L6 self/related eligible trades:")
    print(f"  all-time on these accounts .............. ${at or 0:,.2f}")
    print(f"  PRE go-live (KEPT, forward-only) ........ ${pre or 0:,.2f}")
    print(f"  FORWARD (>= {SELF_ZERO_START}, will be $0) .... ${fwd or 0:,.2f}   <-- zeroed now")
    print(f"  [illustration] last 30d rate ............ ${l30 or 0:,.2f}")

    # top affected IBs
    cur.execute("""
        SELECT s.ib_id, i.name, MIN(s.ib_level), COUNT(*) FILTER (WHERE s.kind='self') selfn,
               COUNT(*) FILTER (WHERE s.kind='related') reln
        FROM _ibsr_tmp s JOIN ibs i ON i.id = s.ib_id
        WHERE s.ib_level BETWEEN 5 AND 6
        GROUP BY s.ib_id, i.name ORDER BY COUNT(*) DESC LIMIT 15
    """)
    print("\nTop L5/L6 IBs by self/related account count:")
    print(f"  {'ib_id':>6} {'lvl':>3} {'self':>5} {'rel':>5}  name")
    for ibid, nm, lvl, sn, rn in cur.fetchall():
        print(f"  {ibid:>6} {lvl:>3} {sn:>5} {rn:>5}  {str(nm)[:34]}")
    cn.rollback(); cn.close()
    print("\n(read-only dry-run — nothing written)")


if __name__ == "__main__":
    _report()
