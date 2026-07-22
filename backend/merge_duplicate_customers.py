"""
Join a SINGLE person's split customer_no records (Clients-list de-duplication).

Why: MT4 / newly-imported accounts were given their own customer_no (some were even dumped
into shared catch-all numbers like CUS400001 that hold many unrelated people). Because the
Clients list groups by customer_no, the same human shows up twice — MT4 row + MT5 row.

Fix (SAFE, login-scoped): group accounts by a STRONG identity key = (normalized email +
normalized phone), BOTH non-empty. Inside each group that spans >1 customer_no, choose a
canonical customer_no (the one used by the MOST logins in THIS group; tie -> smallest) and
repoint ONLY those specific logins to it. We update by LOGIN — never by `WHERE customer_no=x`
— because a loser number may be a catch-all shared by other, unrelated people who must NOT move.

Then delete a loser `customers` row ONLY if it is left with zero clients (else it would render
as an empty ghost row). Catch-all numbers that still hold other people are left intact.

Leaves LEADS untouched by design.

Usage:
  python merge_duplicate_customers.py            # DRY RUN
  python merge_duplicate_customers.py --apply     # apply (single transaction)
"""
import sys
import re
from collections import defaultdict
import db_config

APPLY = "--apply" in sys.argv


def norm_phone(p: str) -> str:
    return re.sub(r"\D", "", p or "")


def norm_email(e: str) -> str:
    return (e or "").strip().lower()


def main():
    conn = db_config.connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT c.login, c.customer_no, c.email, c.phone
        FROM clients c
        JOIN customers cu ON cu.customer_no = c.customer_no AND cu.kind = 'client'
        WHERE c.email IS NOT NULL AND c.email <> ''
          AND c.phone IS NOT NULL AND c.phone <> ''
    """)
    rows = cur.fetchall()

    # (email, phone) -> customer_no -> [logins]
    groups = defaultdict(lambda: defaultdict(list))
    for login, cno, email, phone in rows:
        e, p = norm_email(email), norm_phone(phone)
        if not e or len(p) < 6:
            continue
        groups[(e, p)][cno].append(login)

    plans = []            # (canonical, [logins_to_move])
    loser_nos = set()
    for key, cnos in groups.items():
        if len(cnos) < 2:
            continue
        canonical = sorted(cnos.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0][0]
        move_logins = [lg for cno, lgs in cnos.items() if cno != canonical for lg in lgs]
        if move_logins:
            plans.append((canonical, move_logins))
            loser_nos.update(cno for cno in cnos if cno != canonical)

    people_fixed = len(plans)
    logins_moved = sum(len(p[1]) for p in plans)
    print(f"people with split accounts : {people_fixed}")
    print(f"logins to repoint          : {logins_moved}")
    print(f"distinct loser customer_no : {len(loser_nos)}")
    print("examples:")
    for canonical, logins in plans[:12]:
        print(f"  -> {canonical}  logins {logins}")

    if not APPLY:
        print("\nDRY RUN — no writes. Re-run with --apply.")
        conn.close()
        return

    moved_c = moved_ta = 0
    for canonical, logins in plans:
        cur.execute("UPDATE clients SET customer_no=%s WHERE login = ANY(%s)", (canonical, logins))
        moved_c += cur.rowcount
        cur.execute("UPDATE trading_accounts SET customer_no=%s WHERE login = ANY(%s)", (canonical, logins))
        moved_ta += cur.rowcount

    # delete only customer rows now left with NO clients (never touch catch-alls still in use)
    deleted = 0
    for lno in loser_nos:
        cur.execute("DELETE FROM customers WHERE customer_no=%s "
                    "AND NOT EXISTS (SELECT 1 FROM clients WHERE customer_no=%s)", (lno, lno))
        deleted += cur.rowcount

    conn.commit()
    print(f"\nAPPLIED. clients repointed={moved_c}  trading_accounts repointed={moved_ta}  "
          f"emptied customers deleted={deleted}")
    conn.close()


if __name__ == "__main__":
    main()
