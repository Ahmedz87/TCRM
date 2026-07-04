"""enrich_contacts.py — recover email/phone for the TradeSoft CRM copy.

The legacy TradeSoft export stripped contact VALUES (only verified-flags survived).
But the live broker_crm holds email/phone for the same people, linked by the MT
trading-login number (the reliable cross-system key — NOT email/phone, NOT name).

This script joins TradeSoft accounts (account_number = MT login) to broker_crm.clients
(login) and writes the recovered contacts into a local `contact_enrichment` table in
the standalone tradesoft_crm DB. The CRM backend LEFT JOINs that table at read time.

This is a MAINTENANCE/sync step (the only place that touches broker_crm). The running
app itself never reads broker_crm. Idempotent — safe to re-run. Read-only on broker_crm.

Usage:  python enrich_contacts.py
"""
import os
import psycopg2
from psycopg2.extras import execute_values

try:
    import _secrets
    _b, _t = _secrets.BROKER_DSN, _secrets.TS_DSN
except Exception:
    _b = _t = ""  # no secret default; set _secrets.py or the env vars below
BROKER_DSN = os.getenv("BROKER_DSN", _b)
TS_DSN = os.getenv("TRADESOFT_DSN", _t)


def main():
    bc = psycopg2.connect(BROKER_DSN)
    ts = psycopg2.connect(TS_DSN)
    b, t = bc.cursor(), ts.cursor()

    # login -> (email, phone) from the live CRM
    print("Reading broker_crm contacts by login ...", flush=True)
    b.execute("SELECT login::text, NULLIF(email,''), NULLIF(phone,'') FROM clients WHERE login IS NOT NULL")
    login2c = {str(lg).strip(): (em, ph) for lg, em, ph in b.fetchall()}
    print(f"  {len(login2c):,} broker_crm logins with contact rows", flush=True)

    # tradesoft user_id -> first matched email/phone via any of its account logins
    print("Matching TradeSoft account logins ...", flush=True)
    t.execute("SELECT user_id, account_number FROM fx_accounts_view "
              "WHERE account_number IS NOT NULL AND account_number <> ''")
    user_email, user_phone = {}, {}
    for uid, acc in t.fetchall():
        c = login2c.get(str(acc).strip())
        if not c:
            continue
        em, ph = c
        if em and uid not in user_email:
            user_email[uid] = em
        if ph and uid not in user_phone:
            user_phone[uid] = ph

    uids = set(user_email) | set(user_phone)
    print(f"  {len(uids):,} TradeSoft people gain a contact "
          f"({len(user_email):,} email / {len(user_phone):,} phone)", flush=True)

    # build/replace the enrichment table
    t.execute("""
        CREATE TABLE IF NOT EXISTS contact_enrichment (
            user_id text PRIMARY KEY,
            email   text,
            phone   text,
            source  text DEFAULT 'broker_crm_login_match'
        )""")
    t.execute("TRUNCATE contact_enrichment")
    rows = [(uid, user_email.get(uid), user_phone.get(uid)) for uid in uids]
    execute_values(t,
        "INSERT INTO contact_enrichment (user_id, email, phone) VALUES %s", rows)
    ts.commit()
    print(f"Wrote {len(rows):,} rows into tradesoft_crm.contact_enrichment.", flush=True)

    bc.close()
    ts.close()


if __name__ == "__main__":
    main()
