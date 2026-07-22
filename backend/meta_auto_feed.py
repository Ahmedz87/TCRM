"""
meta_auto_feed.py — AUTOMATIC lead-quality feedback to Meta CAPI (replaces the manual
"Meta Quality" rating column, Jul 2026 desk rules):

  converted      : the lead deposited (matched/converted client with a real deposit)
  lost           : stage = 'Bad Data'
  not_qualified  : stage is a BAD outcome (Not Interested / Unreachable / Archived)
  qualified      : lead is verified (email OR phone OR KYC) OR stage is a GOOD outcome
  (nothing)      : New Lead / No Answer — no feed; No Answer waits for re-calls.

Precedence: converted > lost > not_qualified > qualified.
Only leads with a meta_lead_id can be fed. Sends via meta_capi_router.send_to_meta and
records the sent level in leads.meta_quality (so each level is sent once; upgrades re-send).
Capped per run — the 15-min loop catches up gradually.
Run standalone: python meta_auto_feed.py [--dry-run]
"""
import sys
import db_config
from meta_capi_router import send_to_meta, STAGE_MAP

DRY = "--dry-run" in sys.argv
CAP = 300

GOOD = ('Contacted', 'Demo Trading', 'Ask - Welcome Bonus', 'Contact Whatsapp', 'Won',
        'Interested in Training', 'Under Training', 'Training Completed')
BAD = ('Not Interested', 'Unreachable', 'Archived')

# rank so we never downgrade converted etc.
RANK = {'': 0, 'qualified': 1, 'not_qualified': 1, 'lost': 2, 'converted': 3}


def run():
    conn = db_config.connect(); cur = conn.cursor()
    cur.execute("""
      WITH ml AS (
        SELECT l.id, l.meta_lead_id, l.email, l.phone, COALESCE(l.meta_quality,'') sent, l.stage,
               l.customer_no, NULLIF(l.matched_login,0) m1, NULLIF(l.converted_login,0) m2,
               (COALESCE(l.email_verified,false) OR COALESCE(l.phone_verified,false)
                OR l.kyc_status='verified') AS verified
        FROM leads l WHERE l.meta_lead_id IS NOT NULL AND l.meta_lead_id <> ''),
      dep AS (   -- leads whose matched/converted login OR any same-customer account deposited
        SELECT DISTINCT ml.id FROM ml
        JOIN transactions t ON t.tx_type='deposit' AND (t.login=ml.m1 OR t.login=ml.m2)
        UNION
        SELECT DISTINCT ml.id FROM ml
        JOIN clients c ON ml.customer_no IS NOT NULL AND c.customer_no=ml.customer_no
        JOIN transactions t ON t.login=c.login AND t.tx_type='deposit')
      SELECT ml.id, ml.meta_lead_id, ml.email, ml.phone, ml.sent, ml.stage, ml.verified,
             (ml.id IN (SELECT id FROM dep)) AS deposited
      FROM ml
    """)
    rows = cur.fetchall()

    sent_n = 0
    for lid, mlid, email, phone, sent, stage, verified, deposited in rows:
        if sent_n >= CAP:
            break
        stage = stage or ''
        if deposited:
            want = 'converted'
        elif stage == 'Bad Data':
            want = 'lost'
        elif stage in BAD:
            want = 'not_qualified'
        elif verified or stage in GOOD:
            want = 'qualified'
        else:
            continue                      # New Lead / No Answer — wait
        if want == sent:
            continue
        if RANK.get(want, 0) < RANK.get(sent, 0):
            continue                      # never downgrade (e.g. converted stays converted)
        if DRY:
            print(f"  would send lead {lid}: {sent or '(none)'} -> {want}")
            sent_n += 1
            continue
        res = send_to_meta(mlid, STAGE_MAP[want], {"email": email or "", "phone": phone or ""})
        if res.get("sent"):
            cur.execute("UPDATE leads SET meta_quality=%s, meta_stage=%s WHERE id=%s",
                        (want, STAGE_MAP[want], lid))
            conn.commit()
            sent_n += 1
        else:
            # config missing / API error — stop this run, try again next cycle
            print(f"  send failed for lead {lid}: {str(res)[:150]}")
            break
    print(f"meta-auto-feed: {'planned' if DRY else 'sent'} {sent_n}")
    conn.close()


if __name__ == "__main__":
    run()
