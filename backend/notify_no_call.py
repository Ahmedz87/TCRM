"""
notify_no_call.py — nudge sales agents about deposits with NO call (item 5b).

A lead that DEPOSITED but was never called does NOT count as a win (see the sales funnel). This
script finds those, per sales agent, in a recent window and drops a de-duplicated notification
("You have a deposit with no call — call them") into the `notifications` bell so the agent acts.

Run:  python notify_no_call.py [--days 14]     (schedule daily)
"""
import sys, argparse
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from sqlalchemy import text
from database import SessionLocal


def run(db, days=14):
    # ensure the notifications table + dedupe index exist (shared schema)
    db.execute(text("""CREATE TABLE IF NOT EXISTS notifications (
        id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT, message TEXT,
        type TEXT, link TEXT, is_read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW(),
        dedupe_key TEXT)"""))
    db.execute(text("""CREATE UNIQUE INDEX IF NOT EXISTS ux_notif_user_dedupe
                       ON notifications(user_id, dedupe_key) WHERE dedupe_key IS NOT NULL"""))
    db.commit()
    rows = db.execute(text(f"""
        WITH dep AS (   -- leads whose customer made a FIRST deposit in the window
            SELECT DISTINCT ON (l.id) l.id AS lead_id, l.assigned_agent_id AS aid,
                   l.full_name, cl.login, NULLIF(cl.first_deposit_at,'') AS fda
            FROM leads l
            JOIN users u ON u.id = l.assigned_agent_id AND u.team_type = 'sales'
            JOIN clients cl ON cl.customer_no = l.customer_no
            WHERE l.customer_no IS NOT NULL AND cl.customer_no IS NOT NULL
              AND NULLIF(cl.first_deposit_at,'') >= (NOW() - (:days || ' days')::interval)::text
            ORDER BY l.id, cl.first_deposit_at)
        SELECT dep.aid, dep.lead_id, dep.full_name
        FROM dep
        WHERE NOT EXISTS (SELECT 1 FROM call_actions ca WHERE ca.login = dep.login AND ca.agent_id = dep.aid)
    """), {"days": days}).fetchall()

    n = 0
    for aid, lead_id, name in rows:
        db.execute(text("""
            INSERT INTO notifications (user_id, title, message, type, link, dedupe_key)
            VALUES (:u, 'Deposit with no call',
                    :m, 'no_call', 'leads', :dk)
            ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING"""),
            {"u": aid, "m": f"{name or 'A lead'} deposited but has no call yet — call them (not counted as won until you do).",
             "dk": f"nocall:{lead_id}"})
        n += 1
    db.commit()
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=14)
    a = ap.parse_args()
    db = SessionLocal()
    try:
        print(f"no-call nudges created/kept: {run(db, a.days)}")
    finally:
        db.close()
