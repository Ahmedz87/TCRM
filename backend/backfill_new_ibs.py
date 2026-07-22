"""
backfill_new_ibs.py — add NEW IBs that build_ibs.py misses.

build_ibs.py identifies an IB by clients.agent (an account that OTHER clients are
referred through). A freshly-created IB account — placed in an IB group on the MT
server but with no referred clients yet — is therefore INVISIBLE to build_ibs and
never lands in the `ibs` table (this is why "the latest IB was from 15/6").

This script closes that gap: it treats ANY trading account whose OWN group is an IB
group as an IB —
    MT5:  group_name  IB\\IB-*        (backslash groups)
    MT4:  group_name  TNFX-IB-*
— and inserts the ones registered after a cutoff that aren't in `ibs` yet.

  · ib_creation_date is set from the account's real reg_date, so the "IB since"
    column shows the true date instead of the stale Jun-15 import date.
  · sales agent is linked from the IB's own client account (clients.assigned_agent_id);
    get_ibs already derives sales_agent from there, and we also copy it onto ibs.
  · a candidate whose phone already belongs to a primary IB (the same person's other
    platform account) is inserted as is_primary=FALSE so the list never double-lists them.
  · permanently-removed IBs (ib_removed) are never re-created.

Idempotent — ON CONFLICT (agent_id) DO NOTHING; safe to re-run. Forward-looking: a
later run with the same cutoff picks up any newer IB accounts automatically.

Usage:
    python backfill_new_ibs.py                 # DRY RUN (shows what it would add)
    python backfill_new_ibs.py --commit        # actually insert
    python backfill_new_ibs.py --cutoff 2026-06-15 --commit
"""
import sys, io, re, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import psycopg2
import db_config

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME,
          user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# an account whose OWN group is an IB group  (MT5 IB\IB-*  or  MT4 TNFX-IB-*)
IB_GROUP = r"(cl.group_name ~* '(^|\\)IB[\\-]' OR cl.group_name ILIKE 'TNFX%IB%')"

# candidates = IB-group accounts registered after the cutoff, not already an IB, not removed.
# reg_date is a VARCHAR of ISO dates, so a string compare is a correct date compare.
def candidate_where(cutoff):
    return f"""
        WHERE {IB_GROUP}
          AND cl.reg_date > '{cutoff}'
          AND NOT EXISTS (SELECT 1 FROM ibs i       WHERE i.agent_id  = cl.login)
          AND NOT EXISTS (SELECT 1 FROM ib_removed r WHERE r.agent_id = cl.login)
    """

INSERT_SQL = """
INSERT INTO ibs (agent_id, ib_code, name, email, phone, country, city, group_name,
                 status, ib_level, total_clients, active_clients,
                 unpaid_commission, paid_commission, total_commission, total_volume, net_deposits,
                 assigned_agent_id, ib_creation_date, is_primary, created_at, updated_at)
SELECT
    cl.login,
    'IB' || cl.login::text,
    COALESCE(NULLIF(TRIM(cl.name), ''), 'IB #' || cl.login::text),
    cl.email, cl.phone, cl.country, cl.city, cl.group_name,
    'active',
    COALESCE((regexp_match(COALESCE(cl.group_name,''), 'IB[-\\\\]?[A-Za-z]*-?([0-9]+)'))[1]::int, 5),
    0, 0, 0, 0, 0, 0, 0,
    NULLIF(cl.assigned_agent_id, 0),
    -- real IB-since date from the account's registration (ISO-ish string -> timestamptz)
    CASE WHEN cl.reg_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN cl.reg_date::timestamptz ELSE NULL END,
    -- primary UNLESS this person already has a primary IB row (same phone, other platform)
    NOT EXISTS (SELECT 1 FROM ibs p
                WHERE NULLIF(TRIM(p.phone),'') = NULLIF(TRIM(cl.phone),'')
                  AND p.is_primary IS NOT FALSE),
    NOW(), NOW()
FROM clients cl
{where}
ON CONFLICT (agent_id) DO NOTHING
"""


def run(cutoff="2026-06-15"):
    """Insert new IB-group accounts (reg_date > cutoff) not yet in `ibs`, and commit.
    Returns the number of IBs inserted. Idempotent — safe to call every sync cycle.
    Used by tradesoft_sync.py (and the daily BrokerCRM-IBBackfill task)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cutoff):
        raise ValueError("cutoff must be YYYY-MM-DD")
    where = candidate_where(cutoff)
    conn = psycopg2.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ibs"); before = cur.fetchone()[0]
        cur.execute(INSERT_SQL.replace("{where}", where))
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM ibs"); after = cur.fetchone()[0]
        return after - before
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="2026-06-15",
                    help="only add IB accounts with reg_date AFTER this ISO date (default 2026-06-15)")
    ap.add_argument("--commit", action="store_true", help="actually insert (otherwise dry-run)")
    args = ap.parse_args()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.cutoff):
        sys.exit("cutoff must be YYYY-MM-DD")

    where = candidate_where(args.cutoff)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    cur.execute(f"""
        SELECT cl.login, cl.platform, cl.group_name, cl.name, cl.phone, cl.assigned_agent_id, cl.reg_date,
               NOT EXISTS (SELECT 1 FROM ibs p WHERE NULLIF(TRIM(p.phone),'')=NULLIF(TRIM(cl.phone),'')
                           AND p.is_primary IS NOT FALSE) AS is_primary
        FROM clients cl {where}
        ORDER BY cl.reg_date DESC
    """)
    cands = cur.fetchall()
    prim = sum(1 for r in cands if r[7])
    print(f"Cutoff reg_date > {args.cutoff}")
    print(f"Candidates to add: {len(cands)}  (primary/visible: {prim}, secondary/hidden: {len(cands)-prim})\n")
    print(f"  {'login':<12}{'plat':<5}{'group':<14}{'sales':<6}{'prim':<5}{'reg':<12}name")
    for lg, plat, grp, name, ph, sa, reg, isp in cands:
        print(f"  {lg:<12}{str(plat):<5}{str(grp):<14}{str(sa):<6}{('Y' if isp else 'n'):<5}{str(reg)[:10]:<12}{str(name)[:28]}")

    if not args.commit:
        print(f"\nDRY RUN — nothing written. Re-run with --commit to insert {len(cands)} IB(s).")
        conn.close(); return

    cur.execute("SELECT COUNT(*) FROM ibs"); before = cur.fetchone()[0]
    cur.execute(INSERT_SQL.replace("{where}", where))
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM ibs"); after = cur.fetchone()[0]
    print(f"\nInserted {after - before} IB(s).  ibs: {before} -> {after}")

    # show the freshly-added rows with their new IB-since dates
    cur.execute(f"""
        SELECT agent_id, name, ib_level, is_primary, ib_creation_date::date, assigned_agent_id
        FROM ibs WHERE ib_creation_date > '{args.cutoff}' AND created_at > NOW() - INTERVAL '10 minutes'
        ORDER BY ib_creation_date DESC""")
    print("\nNewly added (agent_id | IB since | lvl | primary | sales_agent_id | name):")
    for r in cur.fetchall():
        print(f"  {r[0]:<12} {str(r[4]):<12} L{r[2]} {'P' if r[3] else 'sec':<4} sa={r[5]}  {str(r[1])[:30]}")
    conn.close()


if __name__ == "__main__":
    main()
