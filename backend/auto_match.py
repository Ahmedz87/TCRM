"""
auto_match.py — Match leads <-> clients, tag badges, fill Network + Score columns.

DEPOSIT TRUTH = deals (action=2 balance ops, profit>0).
  The transactions table is empty and clients.first_deposit_at is unreliable
  (only ~20 populated), so first-deposit time is derived from deals:
     to_timestamp(MIN(deal_time)) WHERE action=2 AND profit>0  per login.

MATCH = lead.email == client.email (lower/trim)  OR  last 9 phone digits equal.

CATEGORY per matched lead (priority recapture > converted > registered_no_deposit):
  recapture             - matched a client who deposited BEFORE this lead arrived
                          (a past depositor filled the form again -> win-back).
  registered_no_deposit - matched a client who never deposited (hot: push 1st deposit).
  converted             - the lead arrived BEFORE the client's first deposit (this
                          lead became a funded client). We ARCHIVE the lead's full
                          history (notes/call log/comments) into lead_archive + copy
                          it onto the client, then DELETE the lead row.

ALSO each run:
  Network - for matched leads, copy ip/cid from account_identifiers and count how
            many OTHER logins share them -> ip_count / cid_count (Network column).
  Score   - blended 0-100 priority for EVERY lead:
              +50 matched (recapture/registered_no_deposit)
              +15 phone_verified, +15 email_verified
              +10 both phone AND email present
              +10 created <=7d ago  (or +5 if <=30d)

RUN:   python auto_match.py            (one pass)
       python auto_match.py --loop     (every 3 min)
"""
import sys, time
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
from datetime import datetime


def ensure_schema(db):
    """Idempotent: tracking column on leads, history columns on clients, archive table."""
    db.execute(text("""
        ALTER TABLE leads   ADD COLUMN IF NOT EXISTS match_checked_at   TIMESTAMPTZ;
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS lead_notes         TEXT;
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS lead_call_attempts INT;
        ALTER TABLE clients ADD COLUMN IF NOT EXISTS lead_last_call_at  TIMESTAMPTZ;
        CREATE TABLE IF NOT EXISTS lead_archive (
            id SERIAL PRIMARY KEY,
            lead_id INT, login BIGINT,
            full_name TEXT, phone TEXT, email TEXT, country TEXT, city TEXT,
            source TEXT, campaign_name TEXT, status TEXT,
            notes TEXT, call_attempts INT, last_call_at TIMESTAMPTZ,
            assigned_agent_id INT, created_at TIMESTAMPTZ,
            converted_reason TEXT, archived_at TIMESTAMPTZ DEFAULT NOW(),
            full_row JSONB
        );
    """))
    db.commit()


def populate_network(db):
    """Fill ip_address/ip_count + cid/cid_count for matched leads from account_identifiers.
    *_count = number of OTHER logins sharing that value (the UI shows the count + 1)."""
    db.execute(text("""
        WITH ip AS (
          SELECT DISTINCT ON (a.login) a.login, a.identifier_value AS ip,
                 (SELECT COUNT(DISTINCT b.login) FROM account_identifiers b
                   WHERE b.identifier_type='ip' AND b.identifier_value=a.identifier_value) - 1 AS cnt
          FROM account_identifiers a WHERE a.identifier_type='ip'
          ORDER BY a.login, a.id DESC
        )
        UPDATE leads l SET ip_address = ip.ip, ip_count = GREATEST(ip.cnt,0)
        FROM ip WHERE l.matched_login = ip.login
    """))
    db.execute(text("""
        WITH cd AS (
          SELECT DISTINCT ON (a.login) a.login, a.identifier_value AS cid,
                 (SELECT COUNT(DISTINCT b.login) FROM account_identifiers b
                   WHERE b.identifier_type='cid' AND b.identifier_value=a.identifier_value) - 1 AS cnt
          FROM account_identifiers a WHERE a.identifier_type='cid'
          ORDER BY a.login, a.id DESC
        )
        UPDATE leads l SET cid = cd.cid, cid_count = GREATEST(cd.cnt,0)
        FROM cd WHERE l.matched_login = cd.login
    """))
    db.commit()


def compute_score(db):
    """Blended priority score (0-100) for EVERY lead."""
    db.execute(text("""
        UPDATE leads SET score = LEAST(100,
              (CASE WHEN match_badge IN ('recapture','registered_no_deposit') THEN 50 ELSE 0 END)
            + (CASE WHEN phone_verified THEN 15 ELSE 0 END)
            + (CASE WHEN email_verified THEN 15 ELSE 0 END)
            + (CASE WHEN COALESCE(phone,'')<>'' AND COALESCE(email,'')<>'' THEN 10 ELSE 0 END)
            + (CASE WHEN COALESCE(meta_created, created_at) >= NOW() - INTERVAL '48 hours' THEN 30
                    WHEN COALESCE(meta_created, created_at) >= NOW() - INTERVAL '7 days'  THEN 10
                    WHEN COALESCE(meta_created, created_at) >= NOW() - INTERVAL '30 days' THEN 5 ELSE 0 END)
        )
    """))
    db.commit()


def run_match_and_notify(verbose=True):
    db = SessionLocal(); db.rollback()
    try:
        ensure_schema(db)

        # Match only UNCHECKED leads (incremental — avoids re-notifying every pass).
        matches = db.execute(text("""
            WITH first_dep AS (
                SELECT login, to_timestamp(MIN(deal_time)) AT TIME ZONE 'UTC' AS fdep
                FROM deals WHERE action=2 AND profit>0 GROUP BY login
            ),
            matched AS (
                SELECT l.id AS lead_id, l.created_at::timestamp AS lead_date,
                       l.full_name, l.assigned_agent_id, c.login, fd.fdep
                FROM leads l
                JOIN clients c ON LOWER(TRIM(l.email))=LOWER(TRIM(c.email))
                LEFT JOIN first_dep fd ON fd.login=c.login
                WHERE l.email IS NOT NULL AND l.email<>'' AND c.email IS NOT NULL AND c.email<>''
                  AND l.match_checked_at IS NULL
                UNION
                SELECT l.id, l.created_at::timestamp, l.full_name, l.assigned_agent_id, c.login, fd.fdep
                FROM leads l
                JOIN clients c ON RIGHT(REGEXP_REPLACE(l.phone,'[^0-9]','','g'),9)
                                = RIGHT(REGEXP_REPLACE(c.phone,'[^0-9]','','g'),9)
                LEFT JOIN first_dep fd ON fd.login=c.login
                WHERE LENGTH(REGEXP_REPLACE(l.phone,'[^0-9]','','g'))>=9
                  AND l.match_checked_at IS NULL
            )
            SELECT lead_id, lead_date, full_name, assigned_agent_id, login, fdep,
                   CASE WHEN fdep IS NULL THEN 'registered_no_deposit'
                        WHEN lead_date >= fdep THEN 'recapture'
                        ELSE 'converted' END AS category
            FROM matched
        """)).fetchall()

        priority = {"recapture": 3, "converted": 2, "registered_no_deposit": 1}
        best = {}
        for lid, ldate, name, agent, login, fdep, cat in matches:
            if lid not in best or priority[cat] > priority[best[lid][0]]:
                best[lid] = (cat, login, name, agent)

        recap = conv = regnd = notif = 0
        for lid, (cat, login, name, agent) in best.items():
            if cat == "recapture":
                db.execute(text("""UPDATE leads SET match_badge='recapture', matched_login=:lg,
                                   match_checked_at=NOW() WHERE id=:l"""), {"lg": login, "l": lid})
                db.execute(text("UPDATE clients SET lead_badge='recapture', matched_lead_id=:l WHERE login=:lg"),
                           {"l": lid, "lg": login})
                if agent:
                    db.execute(text("""
                        INSERT INTO notifications (user_id, title, message, type, link, is_read, created_at)
                        VALUES (:uid, :title, :msg, 'recapture', :link, FALSE, NOW())
                    """), {"uid": agent, "title": "♻ Recapture lead!",
                           "msg": f"{name or 'A lead'} was a client (#{login}) and filled the ad form again — still interested!",
                           "link": f"/leads?highlight={lid}"})
                    notif += 1
                recap += 1

            elif cat == "converted":
                # preserve the full history, then remove from leads (it's a funded client now)
                db.execute(text("""
                    INSERT INTO lead_archive (lead_id, login, full_name, phone, email, country, city,
                        source, campaign_name, status, notes, call_attempts, last_call_at,
                        assigned_agent_id, created_at, converted_reason, full_row)
                    SELECT id, :lg, full_name, phone, email, country, city, source, campaign_name, status,
                        notes, call_attempts, last_call_at, assigned_agent_id, created_at,
                        'deposited after lead', to_jsonb(leads.*)
                    FROM leads WHERE id=:l
                """), {"lg": login, "l": lid})
                db.execute(text("""
                    UPDATE clients c SET lead_badge='from_lead', matched_lead_id=:l,
                        lead_notes        = COALESCE((SELECT notes        FROM leads WHERE id=:l), c.lead_notes),
                        lead_call_attempts= (SELECT call_attempts FROM leads WHERE id=:l),
                        lead_last_call_at = (SELECT last_call_at  FROM leads WHERE id=:l)
                    WHERE c.login=:lg
                """), {"l": lid, "lg": login})
                db.execute(text("DELETE FROM leads WHERE id=:l"), {"l": lid})
                conv += 1

            else:  # registered_no_deposit
                db.execute(text("""UPDATE leads SET match_badge='registered_no_deposit', matched_login=:lg,
                                   match_checked_at=NOW() WHERE id=:l"""), {"lg": login, "l": lid})
                regnd += 1

        # everything left unchecked this pass found no match
        db.execute(text("UPDATE leads SET match_checked_at=NOW() WHERE match_checked_at IS NULL"))
        db.commit()

        # network + score refreshed every pass (idempotent, covers all leads)
        populate_network(db)
        compute_score(db)

        if verbose or (recap + conv + regnd):
            print(f"[{datetime.now():%H:%M:%S}] Matched: recapture {recap}, "
                  f"converted {conv} (archived+removed), no-deposit {regnd}, notifications {notif}")
    except Exception as e:
        db.rollback(); print(f"Match error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    if "--loop" in sys.argv:
        print("Auto-match service running. Checks every 3 min. Ctrl+C to stop.")
        while True:
            run_match_and_notify()
            time.sleep(180)
    else:
        run_match_and_notify()
