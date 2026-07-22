"""
nda_engine.py — NDA = "New Deposit Account": a client who made a First-Time Deposit (FTD) and has NO
relation to any OTHER TNFX customer. It's a GENUINE new acquisition.

Why it matters: sales/IB get targets to bring X new deposit accounts (reward/commission), so some
cheat by opening accounts for their own FAMILY/FRIENDS. Those "new" accounts CONNECT to existing
customers (shared device / IP / phone / same funding card / similar email / same family). A real new
customer connects to NObody. So:

    NDA (genuine)   = deposited customer with NO strong cross-customer relation
    NOT NDA (suspect) = deposited customer that IS linked to another customer

IB and city do NOT disqualify — a new client is EXPECTED to share the IB/agent who introduced them,
and everyone shares a city. Only relationship signals count: device(cid/mqid), IP, phone, same
payment sender (Qi card/wallet), similar email, and family_code (once the family engine is committed).

KPI: total NDA + per-sales-agent / per-IB NDA rate. A low NDA% for an agent/IB = red flag (their
"new" accounts are mostly related = family/friends).

Run DRY (report only):   python nda_engine.py
Commit is_nda to clients: python nda_engine.py --commit
"""
import sys
import db_config

# fanout caps: a token shared by more customers than this is infrastructure (NAT/shared PC/exchanger),
# NOT a family link — so it does NOT mark people related.
FAN_DEVICE, FAN_IP, FAN_PHONE, FAN_PAY = 25, 8, 8, 6


def related_customers(cur):
    """Set of customer_no that share a STRONG relationship signal with a DIFFERENT customer."""
    related = set()

    def add(sql, params=None):
        try:
            cur.execute(sql, params or {})
            for (cn,) in cur.fetchall():
                if cn is not None:
                    related.add(cn)
        except Exception:
            cur.connection.rollback()   # optional signal missing (e.g. family_code) — skip cleanly

    # device (cid/mqid) + IP shared across DIFFERENT customers (fan-out capped)
    for typ, fan in (("cid", FAN_DEVICE), ("mqid", FAN_DEVICE), ("ip", FAN_IP)):
        add("""
            WITH tok AS (
                SELECT ai.identifier_value v, c.customer_no cn
                FROM account_identifiers ai JOIN clients c ON c.login=ai.login
                WHERE ai.identifier_type=%(t)s AND ai.identifier_value NOT IN ('0','')
                  AND c.customer_no IS NOT NULL),
            shared AS (SELECT v FROM tok GROUP BY v HAVING COUNT(DISTINCT cn) BETWEEN 2 AND %(f)s)
            SELECT DISTINCT tok.cn FROM tok JOIN shared USING (v)
        """, {"t": typ, "f": fan})

    # same phone across different customers
    add("""
        WITH tok AS (
            SELECT RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9) v, customer_no cn
            FROM clients WHERE customer_no IS NOT NULL
              AND length(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'))>=9),
        shared AS (SELECT v FROM tok GROUP BY v HAVING COUNT(DISTINCT cn) BETWEEN 2 AND %(f)s)
        SELECT DISTINCT tok.cn FROM tok JOIN shared USING (v)
    """, {"f": FAN_PHONE})

    # similar/normalized email across different customers (dots/+tags removed = same inbox family)
    add("""
        WITH tok AS (
            SELECT replace(regexp_replace(lower(split_part(email,'@',1)),'\\+.*$','','g'),'.','') v, customer_no cn
            FROM clients WHERE customer_no IS NOT NULL AND email IS NOT NULL AND email<>''),
        shared AS (SELECT v FROM tok WHERE length(v)>=4 GROUP BY v HAVING COUNT(DISTINCT cn) BETWEEN 2 AND %(f)s)
        SELECT DISTINCT tok.cn FROM tok JOIN shared USING (v)
    """, {"f": FAN_DEVICE})

    # same payment sender (same Qi card / wallet funded them) across different customers
    add("""
        WITH tok AS (
            SELECT ps.method||':'||ps.sender_key v, c.customer_no cn
            FROM client_payment_senders ps JOIN clients c ON c.login=ps.client_login
            WHERE c.customer_no IS NOT NULL),
        shared AS (SELECT v FROM tok GROUP BY v HAVING COUNT(DISTINCT cn) BETWEEN 2 AND %(f)s)
        SELECT DISTINCT tok.cn FROM tok JOIN shared USING (v)
    """, {"f": FAN_PAY})

    # family_code (once the family engine is committed) — same family = related
    add("SELECT customer_no FROM clients WHERE family_code IS NOT NULL AND customer_no IS NOT NULL")
    return related


def backfill_ftd(cur):
    """Set clients.first_deposit_at = each login's EARLIEST deposit tx_date (authoritative FTD date).
    The column was historically empty/stale; transactions.tx_date holds the real datetime. ISO text
    ('YYYY-MM-DD HH:MM:SS') so lexicographic period filters (>= :from AND < :to_next) work. Idempotent."""
    cur.execute("""
        UPDATE clients c
           SET first_deposit_at = t.fda
          FROM (SELECT login, MIN(tx_date) AS fda FROM transactions
                WHERE tx_type='deposit' AND COALESCE(tx_date,'') <> '' GROUP BY login) t
         WHERE t.login = c.login
           AND COALESCE(c.first_deposit_at,'') IS DISTINCT FROM t.fda
    """)
    return cur.rowcount


def main():
    # DEPRECATED: relation_engine.py is now the single source for is_nda (it uses the refined relation
    # rules — this module's older definition marked bare-IP/common-name matches as related and diverged
    # from the network page). Kept only for backfill_ftd(), which relation_engine imports. A manual
    # --commit here would overwrite the unified is_nda with the old logic, so it's gated behind --force.
    if "--commit" in sys.argv and "--force" not in sys.argv:
        print("nda_engine is DEPRECATED — use relation_engine.py. Re-run with --force to override.")
        return
    commit = "--commit" in sys.argv
    c = db_config.connect(); cur = c.cursor()

    if commit:
        n = backfill_ftd(cur); c.commit()
        print(f"backfilled first_deposit_at (FTD date) for {n} client rows from transactions")

    cur.execute("SELECT DISTINCT customer_no FROM clients WHERE customer_no IS NOT NULL AND total_deposits>0")
    deposited = {r[0] for r in cur.fetchall()}
    related = related_customers(cur)
    nda = deposited - related
    print(f"deposited customers: {len(deposited)} | related (linked to another customer): "
          f"{len(deposited & related)} | NDA (genuine new): {len(nda)} "
          f"({100*len(nda)/max(1,len(deposited)):.0f}%)")

    # KPI per sales agent (assigned_agent_id): deposited accts vs NDA rate — low NDA% = suspicious
    cur.execute("""
        SELECT u.full_name, c.assigned_agent_id, c.customer_no
        FROM clients c LEFT JOIN users u ON u.id=c.assigned_agent_id
        WHERE c.customer_no IS NOT NULL AND c.total_deposits>0 AND c.assigned_agent_id IS NOT NULL
    """)
    from collections import defaultdict
    per_agent = defaultdict(lambda: {"name": "", "custs": set(), "nda": set()})
    for name, aid, cn in cur.fetchall():
        pa = per_agent[aid]; pa["name"] = name or f"#{aid}"; pa["custs"].add(cn)
        if cn in nda:
            pa["nda"].add(cn)
    rows = [(v["name"], len(v["custs"]), len(v["nda"])) for v in per_agent.values() if len(v["custs"]) >= 10]
    rows.sort(key=lambda r: (r[2] / r[1]))   # worst NDA% first
    print("\nSales agents with the LOWEST NDA% (most family/friend accounts — investigate):")
    for name, tot, n in rows[:8]:
        print(f"  {name[:24]:24} deposited={tot:4}  NDA={n:4}  NDA%={100*n/tot:3.0f}%")

    if not commit:
        print("\nDRY-RUN — nothing written. Re-run with --commit to tag clients.is_nda.")
        c.close(); return

    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_nda BOOLEAN")
    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS nda_at TIMESTAMPTZ")
    cur.execute("UPDATE clients SET is_nda=NULL WHERE total_deposits IS NULL OR total_deposits<=0")
    cur.execute("UPDATE clients SET is_nda=FALSE, nda_at=NOW() WHERE customer_no = ANY(%s)",
                (list(deposited & related),))
    cur.execute("UPDATE clients SET is_nda=TRUE, nda_at=NOW() WHERE customer_no = ANY(%s)",
                (list(nda),))
    c.commit(); c.close()
    print(f"\nCOMMITTED: tagged {len(nda)} NDA customers (is_nda=TRUE) and "
          f"{len(deposited & related)} related (is_nda=FALSE).")


if __name__ == "__main__":
    main()
