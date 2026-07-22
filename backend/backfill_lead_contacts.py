"""Fill email/phone on TradeSoft-sourced leads from the FULL `fx_leads` table.

WHY: the sync builds leads from `fx_leads_view`, which the old-CRM team stripped of email/phone
(historically those were only ever loaded from a manual CSV export, so leads synced after the CSV
came in blank). The full `fx_leads` table is now accessible and HAS the contacts, so we map each
contactless lead (via customers.legacy_user_id = fx_leads.user_id) and fill them in.

Idempotent. Run standalone: `python backfill_lead_contacts.py`, or it runs each cycle from tradesoft_sync.
"""
import ts_mysql_config, pymysql


def run(db):
    # support both a raw psycopg2 connection and a SQLAlchemy session
    from sqlalchemy import text
    is_sa = hasattr(db, "execute") and not hasattr(db, "cursor")
    def q(sql, params=None):
        if is_sa:
            return db.execute(text(sql), params or {}).fetchall()
        cur = db.cursor(); cur.execute(sql, params or ()); return cur.fetchall()
    def x(sql, params):
        if is_sa:
            db.execute(text(sql), params)
        else:
            cur = db.cursor(); cur.execute(sql, params)

    # leads missing ANY of: email, phone, campaign_name  (campaign = fx_leads.lead_source).
    # Scope by TradeSoft LINKAGE (a numeric legacy_user_id on the customer), NOT source: leads
    # get reclassified away from 'tradesoft' to meta/google/MQL5/sales_agent, so filtering on
    # source='tradesoft' would silently skip them and leave their contacts blank forever.
    leads = q("""
        SELECT l.id, cu.legacy_user_id
        FROM leads l JOIN customers cu ON cu.customer_no = l.customer_no
        WHERE cu.legacy_user_id ~ '^[0-9]+$'
          AND (COALESCE(TRIM(l.email),'')='' OR COALESCE(TRIM(l.phone),'')=''
               OR COALESCE(TRIM(l.campaign_name),'')='')
    """)
    if not leads:
        print("  lead backfill: nothing to fill"); return 0

    m = ts_mysql_config.MYSQL_SRC
    my = pymysql.connect(host=m["host"], port=int(m["port"]), user=m["user"],
                         password=m["password"], database=m["database"], connect_timeout=15)
    mc = my.cursor()

    # Chunk so the MySQL IN(...) and the PG updates stay bounded (up to ~160k leads).
    upd = 0
    CHUNK = 1000
    for i in range(0, len(leads), CHUNK):
        batch = leads[i:i + CHUNK]
        uids = sorted({int(r[1]) for r in batch})
        fmt = ",".join(["%s"] * len(uids))
        mc.execute(f"""SELECT user_id, MAX(NULLIF(TRIM(email),'')),
                              MAX(COALESCE(NULLIF(TRIM(phone),''), NULLIF(TRIM(mobile),''))),
                              MAX(NULLIF(TRIM(lead_source),''))
                       FROM fx_leads WHERE user_id IN ({fmt}) GROUP BY user_id""", uids)
        contact = {str(r[0]): (r[1], r[2], r[3]) for r in mc.fetchall()}
        for lid, uid in batch:
            em, ph, camp = contact.get(str(uid), (None, None, None))
            if em or ph or camp:
                if is_sa:
                    x("""UPDATE leads SET email=COALESCE(NULLIF(TRIM(email),''),:em),
                           phone=COALESCE(NULLIF(TRIM(phone),''),:ph),
                           campaign_name=COALESCE(NULLIF(TRIM(campaign_name),''),:camp) WHERE id=:id""",
                      {"em": em, "ph": ph, "camp": camp, "id": lid})
                else:
                    x("""UPDATE leads SET email=COALESCE(NULLIF(TRIM(email),''),%s),
                           phone=COALESCE(NULLIF(TRIM(phone),''),%s),
                           campaign_name=COALESCE(NULLIF(TRIM(campaign_name),''),%s) WHERE id=%s""",
                      (em, ph, camp, lid))
                upd += 1
        db.commit()
    my.close()
    print(f"  lead backfill: filled {upd}/{len(leads)} (email/phone/campaign) from full fx_leads")
    return upd


if __name__ == "__main__":
    import db_config, sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    con = db_config.connect()
    run(con)
    con.close()
