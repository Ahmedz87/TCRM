"""
Split CATCH-ALL customer buckets (one customer_no wrongly holding SEVERAL different people —
e.g. CUS400001 held 13+ unrelated registrants), the yasamen.aldaghir case (Jul 2026).

Rule: inside a bucket, people are grouped by phone (last-9; blank phone => own group per login,
same-email rows stay together). If a bucket holds >1 group, the largest group keeps the original
customer_no; every other group gets a fresh CUS7xxxxx customer with:
  kind = 'client' if the group has any real deposit,
         'lead'   if no deposit but a lead row exists for the person (they show on Leads only),
         'client' otherwise (so nobody becomes invisible).
Also links matching lead rows (converted/matched login) to the new customer_no.
Login-scoped updates only. Usage: python split_catchall_customers.py [--dry-run]
"""
import sys
import re
from collections import defaultdict
import db_config

DRY = "--dry-run" in sys.argv


def p9(p):
    d = re.sub(r"\D", "", p or "")
    return d[-9:] if len(d) >= 9 else ""


def main():
    conn = db_config.connect(); cur = conn.cursor()

    # buckets with >1 distinct email among their client rows
    cur.execute("""
      SELECT customer_no FROM clients
      WHERE customer_no IS NOT NULL AND COALESCE(TRIM(email),'')<>''
      GROUP BY customer_no HAVING count(DISTINCT lower(TRIM(email))) > 1""")
    buckets = [r[0] for r in cur.fetchall()]
    print(f"multi-email buckets: {len(buckets)}")

    # next free CUS7 sequence
    cur.execute("SELECT COALESCE(max(substring(customer_no from 4)::int),700000) FROM customers WHERE customer_no ~ '^CUS7[0-9]{5}$'")
    seq = max(700000, (cur.fetchone()[0] or 700000)) + 1

    moved_groups = moved_logins = linked_leads = 0
    for cno in buckets:
        cur.execute("""SELECT login, lower(TRIM(email)), phone, name FROM clients
                       WHERE customer_no=%s ORDER BY login""", (cno,))
        rows = cur.fetchall()
        groups = defaultdict(list)   # key -> [(login,email,phone,name)]
        for lg, em, ph, nm in rows:
            key = p9(ph) or (em or f"login{lg}")
            groups[key].append((lg, em, ph, nm))
        if len(groups) < 2:
            continue   # multi-email but single phone-person (same human, two emails) — leave
        # keep the original customer_no on the LARGEST group
        keys = sorted(groups, key=lambda k: -len(groups[k]))
        for key in keys[1:]:
            members = groups[key]
            logins = [m[0] for m in members]
            em = next((m[1] for m in members if m[1]), None)
            ph = next((m[2] for m in members if m[2]), None)
            nm = next((m[3] for m in members if m[3]), None)
            # kind by deposits / lead presence
            cur.execute("""SELECT EXISTS (SELECT 1 FROM transactions t
                             WHERE t.login = ANY(%s) AND t.tx_type='deposit')""", (logins,))
            has_dep = cur.fetchone()[0]
            cur.execute("""SELECT id FROM leads
                           WHERE COALESCE(NULLIF(converted_login,0), NULLIF(matched_login,0)) = ANY(%s)
                              OR (%s IS NOT NULL AND lower(TRIM(email)) = %s) LIMIT 5""",
                        (logins, em, em))
            lead_ids = [r[0] for r in cur.fetchall()]
            kind = 'client' if has_dep else ('lead' if lead_ids else 'client')
            new_cno = f"CUS{seq:06d}"; seq += 1
            moved_groups += 1; moved_logins += len(logins)
            if DRY:
                continue
            cur.execute("""INSERT INTO customers (customer_no, name, email, phone, kind, source, n_accounts)
                           VALUES (%s,%s,%s,%s,%s,'split',%s) ON CONFLICT (customer_no) DO NOTHING""",
                        (new_cno, nm, em, ph, kind, len(logins)))
            cur.execute("UPDATE clients SET customer_no=%s WHERE login = ANY(%s)", (new_cno, logins))
            cur.execute("UPDATE trading_accounts SET customer_no=%s WHERE login = ANY(%s)", (new_cno, logins))
            cur.execute("UPDATE leads SET customer_no=%s WHERE id = ANY(%s)", (new_cno, lead_ids))
            linked_leads += len(lead_ids)
            conn.commit()

    print(f"groups split out: {moved_groups} | logins moved: {moved_logins} | leads linked: {linked_leads}")
    if DRY:
        conn.rollback(); print("DRY RUN — nothing written")
    conn.close()


if __name__ == "__main__":
    main()
