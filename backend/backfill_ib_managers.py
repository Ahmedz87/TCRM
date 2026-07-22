"""
backfill_ib_managers.py — assign an ACCOUNT MANAGER (reviewer) to pending IBs that don't have one.
Rule (desk, Jul 2026): existing client/lead -> keep their current account manager; brand-new -> the
RETENTION team, round-robin (balanced by current IB load, in id order). Signup does this going
forward (ib_portal_auth.register); this backfills the ones created before that. `--commit` to write.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import db_config


def digits9(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())[-9:]


def main(commit=False):
    c = db_config.connect(); c.autocommit = False; cur = c.cursor()
    # retention team + their CURRENT IB load (so we keep balancing "in order")
    cur.execute("""SELECT u.id, u.full_name, COUNT(i.id)
        FROM users u LEFT JOIN ibs i ON i.assigned_agent_id = u.id
        WHERE LOWER(COALESCE(u.team_type,''))='retention' AND COALESCE(u.is_active,TRUE)
        GROUP BY u.id, u.full_name ORDER BY u.id""")
    ret = [[r[0], r[1], int(r[2])] for r in cur.fetchall()]
    if not ret:
        print("no retention agents found — aborting."); c.close(); return
    load = {r[0]: r[2] for r in ret}
    names = {r[0]: r[1] for r in ret}

    cur.execute("""SELECT id, name, email, phone, status FROM ibs
        WHERE status='pending' AND assigned_agent_id IS NULL ORDER BY id""")
    pend = cur.fetchall()
    print(f"pending IBs without an account manager: {len(pend)}")
    plan = []
    for ib_id, nm, email, phone, status in pend:
        p9 = digits9(phone)
        mgr = cur.execute if False else None
        # 1) existing client's manager
        cur.execute("""SELECT assigned_agent_id FROM clients
            WHERE assigned_agent_id IS NOT NULL AND (lower(email)=lower(%s)
                  OR (%s<>'' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=%s)) LIMIT 1""",
            (email or "", p9, p9))
        r = cur.fetchone(); mgr = r[0] if r else None
        src = "client" if mgr else ""
        # 2) existing lead's manager
        if not mgr:
            cur.execute("""SELECT assigned_agent_id FROM leads
                WHERE assigned_agent_id IS NOT NULL AND (lower(email)=lower(%s)
                      OR (%s<>'' AND RIGHT(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9)=%s))
                ORDER BY assigned_at DESC NULLS LAST LIMIT 1""", (email or "", p9, p9))
            r = cur.fetchone(); mgr = r[0] if r else None
            src = "lead" if mgr else ""
        # 3) round-robin retention (least-loaded, id order)
        if not mgr:
            mgr = min(ret, key=lambda x: (load[x[0]], x[0]))[0]
            load[mgr] += 1
            src = "retention(rr)"
        plan.append((ib_id, nm, mgr, names.get(mgr, f"#{mgr}"), src))
        print(f"  IB {ib_id:>6} {str(nm)[:22]:<22} -> {names.get(mgr, mgr)}  ({src})")

    if not commit:
        print("\nDRY RUN — nothing written. Re-run with --commit to apply.")
        c.close(); return
    for ib_id, nm, mgr, mname, src in plan:
        cur.execute("UPDATE ibs SET assigned_agent_id=%s WHERE id=%s AND assigned_agent_id IS NULL", (mgr, ib_id))
    c.commit()
    print(f"\nApplied {len(plan)} account-manager assignments.")
    c.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
