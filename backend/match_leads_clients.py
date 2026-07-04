"""
Lead <-> Client Matching Engine
Matches on email OR phone (last 9 digits). Uses first DEPOSIT date as 'became client'.

Rules:
  RECAPTURE:   funded client (deposited) THEN filled form again (lead after deposit)
               -> badge 'recapture' on client + lead, notify sales, keep top
  CONVERTED:   filled form first THEN deposited (lead before deposit)
               -> remove lead, badge 'from_lead' on client
  REG_NO_DEP:  matched an account that never deposited
               -> keep lead, badge 'registered_no_deposit', hot/top

Run:  python match_leads_clients.py            (preview only)
      python match_leads_clients.py --apply    (actually apply changes)
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text
from datetime import datetime

APPLY = "--apply" in sys.argv

db = SessionLocal()
db.rollback()

def run():
    print("=" * 55)
    print("LEAD <-> CLIENT MATCHING ENGINE")
    print("MODE:", "APPLY (writing changes)" if APPLY else "PREVIEW (no changes)")
    print("=" * 55)

    # Build the match set: lead matched to client by email OR phone,
    # with that client's first deposit date.
    matches = db.execute(text("""
        WITH first_dep AS (
            SELECT login, MIN(tx_date::timestamp) as first_deposit
            FROM transactions
            WHERE tx_type IN ('deposit','credit_in')
              AND tx_date IS NOT NULL AND tx_date != ''
            GROUP BY login
        ),
        matched AS (
            -- email match
            SELECT l.id as lead_id, l.created_at as lead_date, c.login,
                   fd.first_deposit, 'email' as via
            FROM leads l
            JOIN clients c ON LOWER(TRIM(l.email)) = LOWER(TRIM(c.email))
            LEFT JOIN first_dep fd ON fd.login = c.login
            WHERE l.email IS NOT NULL AND l.email != ''
              AND c.email IS NOT NULL AND c.email != ''
              AND l.match_checked_at IS NULL
            UNION
            -- phone match (last 9 digits)
            SELECT l.id as lead_id, l.created_at as lead_date, c.login,
                   fd.first_deposit, 'phone' as via
            FROM leads l
            JOIN clients c ON RIGHT(REGEXP_REPLACE(l.phone,'[^0-9]','','g'),9)
                            = RIGHT(REGEXP_REPLACE(c.phone,'[^0-9]','','g'),9)
            LEFT JOIN first_dep fd ON fd.login = c.login
            WHERE LENGTH(REGEXP_REPLACE(l.phone,'[^0-9]','','g')) >= 9
        )
        SELECT lead_id, lead_date, login, first_deposit,
               CASE
                 WHEN first_deposit IS NULL THEN 'registered_no_deposit'
                 WHEN lead_date::timestamp >= first_deposit THEN 'recapture'
                 ELSE 'converted'
               END as category
        FROM matched
    """)).fetchall()

    # Dedupe: one decision per lead (priority recapture > converted > reg_no_dep)
    priority = {'recapture': 3, 'converted': 2, 'registered_no_deposit': 1}
    best = {}  # lead_id -> (category, login, first_deposit)
    for m in matches:
        lid, ldate, login, fdep, cat = m
        if lid not in best or priority[cat] > priority[best[lid][0]]:
            best[lid] = (cat, login, fdep)

    counts = {'recapture': 0, 'converted': 0, 'registered_no_deposit': 0}
    for lid, (cat, login, fdep) in best.items():
        counts[cat] += 1

    print(f"\nUnique leads matched: {len(best)}")
    print(f"  RECAPTURE (was client, came back):     {counts['recapture']}")
    print(f"  CONVERTED (lead became client):        {counts['converted']}")
    print(f"  REGISTERED NO DEPOSIT (hot leads):     {counts['registered_no_deposit']}")

    if not APPLY:
        print("\n[PREVIEW] No changes made. Run with --apply to apply.")
        return

    # APPLY changes
    print("\nApplying changes...")
    recap = conv = regnd = 0
    for lid, (cat, login, fdep) in best.items():
        if cat == 'recapture':
            # badge lead + client, notify sales
            db.execute(text("""
                UPDATE leads SET match_badge='recapture', matched_login=:login,
                    match_checked_at=NOW(), updated_at=NOW() WHERE id=:lid
            """), {"login": login, "lid": lid})
            db.execute(text("""
                UPDATE clients SET lead_badge='recapture', matched_lead_id=:lid,
                    recapture_at=NOW() WHERE login=:login
            """), {"lid": lid, "login": login})
            recap += 1
        elif cat == 'converted':
            # mark client as from_lead, remove lead
            db.execute(text("""
                UPDATE clients SET lead_badge='from_lead', matched_lead_id=:lid
                WHERE login=:login
            """), {"lid": lid, "login": login})
            db.execute(text("DELETE FROM leads WHERE id=:lid"), {"lid": lid})
            conv += 1
        else:  # registered_no_deposit
            db.execute(text("""
                UPDATE leads SET match_badge='registered_no_deposit', matched_login=:login,
                    match_checked_at=NOW(), updated_at=NOW() WHERE id=:lid
            """), {"login": login, "lid": lid})
            regnd += 1

        if (recap+conv+regnd) % 100 == 0:
            db.commit()

    db.commit()
    print(f"\nDone!")
    print(f"  Recapture badged:          {recap}")
    print(f"  Converted (removed leads): {conv}")
    print(f"  Registered-no-deposit:     {regnd}")

try:
    run()
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
