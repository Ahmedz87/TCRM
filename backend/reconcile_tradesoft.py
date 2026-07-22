"""
reconcile_tradesoft.py — bring the live CRM into line with TradeSoft (source of truth) and give
every person a CUS customer id. Run phase by phase:  python reconcile_tradesoft.py --phase N

  schema : customers table + customer_no on clients/leads/trading_accounts
  1 : CUS customer master (one per legacy person) + link existing clients/accounts; classify client/lead
  2 : trading accounts -> active (on MT) or archive (not on MT); set customer_no on all
  3 : TradeSoft leads -> our leads table
  4 : reconcile existing rows from TradeSoft (IB / sales agent / deposits / withdrawals)

Additive + idempotent (ON CONFLICT / IS NULL guards). Backup: backups/pre_reconcile.dump
"""
import sys, time
from sqlalchemy import text
from database import SessionLocal
L = "tradesoft_old"
# one legacy account row per login (latest), reused by several phases
ACCT = f"""(SELECT DISTINCT ON (account_number::bigint) account_number::bigint login, user_id,
            CASE WHEN agent ~ '^[0-9]+$' THEN agent::bigint END agent
            FROM {L}.fx_accounts_view WHERE account_number ~ '^[0-9]+$' AND user_id ~ '^[0-9]+$'
            ORDER BY account_number::bigint, updated_at DESC NULLS LAST)"""


def schema(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS customers (
        customer_no TEXT PRIMARY KEY, legacy_user_id TEXT, name TEXT, email TEXT, phone TEXT,
        country TEXT, kind TEXT, kyc_status TEXT, source TEXT DEFAULT 'tradesoft',
        n_accounts INT DEFAULT 0, total_deposits NUMERIC DEFAULT 0, total_withdrawals NUMERIC DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_legacy ON customers(legacy_user_id)"))
    for t in ("clients", "leads", "trading_accounts"):
        # CATALOG-CHECK FIRST — never run the no-op ALTER on a hot table. Even ADD COLUMN IF NOT
        # EXISTS takes an ACCESS EXCLUSIVE lock, and under live traffic the DB's lock_timeout=5s
        # cancelled it, killing EVERY hourly sync at this line BEFORE the new-leads import ran
        # (#272 — "new leads only in the old CRM"). The column has existed for weeks; only ALTER
        # if it is genuinely missing.
        _has = db.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name='customer_no'"),
            {"t": t}).fetchone()
        if not _has:
            db.execute(text(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS customer_no TEXT"))
            db.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{t}_customer ON {t}(customer_no)"))
    db.commit()
    print("schema ready (customers + customer_no columns)")


def phase1(db):
    # email/phone come from the FULL fx_leads (the fx_*_view the old-CRM team granted us are
    # REDACTED of contacts; the full fx_leads table IS mirrored and HAS them). Pulling contacts
    # here means customers -> leads are born WITH email/phone; no separate backfill needed.
    n = db.execute(text(f"""
      INSERT INTO customers (customer_no, legacy_user_id, name, email, phone, country, kind, kyc_status)
      SELECT 'CUS'||lpad(u.id,6,'0'), u.id,
        NULLIF(trim(COALESCE(u.name,'')||' '||COALESCE(u.surname,'')),''),
        fl.email, fl.phone,
        COALESCE(cl.country, ll.country),
        CASE WHEN cl.user_id IS NOT NULL THEN 'client' ELSE 'lead' END,
        CASE WHEN u.is_kyc_verified='1' THEN 'verified' ELSE 'pending' END
      FROM {L}.fx_users_view u
      LEFT JOIN (SELECT DISTINCT ON(user_id) user_id,
                   NULLIF(TRIM(email),'') email,
                   COALESCE(NULLIF(TRIM(phone),''), NULLIF(TRIM(mobile),'')) phone
                 FROM {L}.fx_leads WHERE deleted_at IS NULL ORDER BY user_id) fl ON fl.user_id=u.id
      LEFT JOIN (SELECT DISTINCT ON(user_id) user_id,country FROM {L}.fx_clients_view
                 WHERE deleted_at IS NULL ORDER BY user_id) cl ON cl.user_id=u.id
      LEFT JOIN (SELECT DISTINCT ON(user_id) user_id,country FROM {L}.fx_leads_view
                 WHERE deleted_at IS NULL ORDER BY user_id) ll ON ll.user_id=u.id
      WHERE u.id ~ '^[0-9]+$'
        AND (cl.user_id IS NOT NULL OR ll.user_id IS NOT NULL
             OR EXISTS(SELECT 1 FROM {L}.fx_accounts_view a WHERE a.user_id=u.id AND a.account_number ~ '^[0-9]+$'))
      ON CONFLICT (customer_no) DO NOTHING
    """)).rowcount
    db.commit(); print(f"  customers created (legacy persons): {n:,}")

    # backfill contacts on EXISTING customers that were created before this (from the full fx_leads)
    bf = db.execute(text(f"""
      UPDATE customers cu SET
        email = COALESCE(NULLIF(TRIM(cu.email),''), fl.email),
        phone = COALESCE(NULLIF(TRIM(cu.phone),''), fl.phone)
      FROM (SELECT DISTINCT ON(user_id) user_id,
              NULLIF(TRIM(email),'') email,
              COALESCE(NULLIF(TRIM(phone),''), NULLIF(TRIM(mobile),'')) phone
            FROM {L}.fx_leads WHERE deleted_at IS NULL ORDER BY user_id) fl
      WHERE fl.user_id = cu.legacy_user_id
        AND (COALESCE(TRIM(cu.email),'')='' OR COALESCE(TRIM(cu.phone),'')='')
        AND (fl.email IS NOT NULL OR fl.phone IS NOT NULL)
    """)).rowcount
    db.commit(); print(f"  contacts backfilled on existing customers: {bf:,}")

    for tbl in ("clients", "trading_accounts"):
        n = db.execute(text(f"""
          UPDATE {tbl} x SET customer_no='CUS'||lpad(a.user_id,6,'0')
          FROM {ACCT} a WHERE a.login=x.login AND x.customer_no IS NULL""")).rowcount
        db.commit(); print(f"  {tbl} linked to CUS via login: {n:,}")

    # live-only clients (no legacy match): new CUS grouped by phone, then by login for no-phone
    db.execute(text("""
      WITH lo AS (SELECT DISTINCT phone FROM clients WHERE customer_no IS NULL AND COALESCE(phone,'')<>''),
      seq AS (SELECT phone,'CUS'||lpad((400000+row_number() OVER (ORDER BY phone))::int::text,6,'0') cus FROM lo)
      UPDATE clients c SET customer_no=seq.cus FROM seq WHERE c.phone=seq.phone AND c.customer_no IS NULL"""))
    db.commit()
    db.execute(text("""
      WITH lo AS (SELECT login FROM clients WHERE customer_no IS NULL),
      seq AS (SELECT login,'CUS'||lpad((500000+row_number() OVER (ORDER BY login))::int::text,6,'0') cus FROM lo)
      UPDATE clients c SET customer_no=seq.cus FROM seq WHERE c.login=seq.login AND c.customer_no IS NULL"""))
    db.commit()

    n = db.execute(text("""
      INSERT INTO customers (customer_no, name, email, phone, country, kind, source)
      SELECT DISTINCT ON (c.customer_no) c.customer_no, c.name, c.email, c.phone, c.country, 'client', 'live'
      FROM clients c WHERE c.customer_no ~ '^CUS[45]' ORDER BY c.customer_no
      ON CONFLICT (customer_no) DO NOTHING""")).rowcount
    db.commit(); print(f"  new live-only customers added: {n:,}")

    # propagate phone/email + account count up to the customer record
    db.execute(text("""
      WITH ct AS (SELECT customer_no, max(NULLIF(phone,'')) phone, max(NULLIF(email,'')) email, count(*) n
                  FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no)
      UPDATE customers cu SET phone=COALESCE(cu.phone, ct.phone), email=COALESCE(cu.email, ct.email),
                              n_accounts=ct.n
      FROM ct WHERE ct.customer_no=cu.customer_no"""))
    db.commit(); print("  phone/email propagated to customers")

    # report
    r = db.execute(text("""SELECT count(*),
        count(*) FILTER (WHERE kind='client'), count(*) FILTER (WHERE kind='lead'),
        count(*) FILTER (WHERE phone IS NOT NULL) FROM customers""")).fetchone()
    lc = db.execute(text("SELECT count(*) FILTER (WHERE customer_no IS NOT NULL), count(*) FROM clients")).fetchone()
    print(f"\n  customers total {r[0]:,} | client {r[1]:,} | lead {r[2]:,} | with phone {r[3]:,}")
    print(f"  live clients with CUS: {lc[0]:,}/{lc[1]:,}")


def phase2(db):
    # Import NEW TradeSoft accounts as ACTIVE/visible. TradeSoft is authoritative that the account
    # EXISTS; whether it's currently on THIS CRM's MT bridge is a separate status (many are ECN,
    # which the MT5 bridge doesn't cover). So a new account is shown in the main list and only gets
    # archived later IF an account we HAD seen on MT disappears (archive_accounts.reactivate/archive
    # cross-check drives that). WHERE a.deleted_at IS NULL means we only import live TradeSoft
    # accounts. The NOT EXISTS guard means this only ever touches genuinely-new logins — the
    # already-imported bulk (archived) is never re-touched here.
    n = db.execute(text(f"""
      INSERT INTO clients (login, name, country, balance, credit, group_name, platform,
          source, archived_at, archive_reason, kyc_status, customer_no, created_at)
      SELECT DISTINCT ON (a.account_number::bigint) a.account_number::bigint,
        cu.name, cu.country,
        -- cap the imported balance: TradeSoft has FAKE round-number balances ($1M-$10M) on test
        -- accounts, backed only by outlier "deposits" the deposit-import already rejects (>=$1M).
        -- Never import a balance >= $1M from TradeSoft; the real balance (if any) comes from MT.
        CASE WHEN NULLIF(regexp_replace(a.account_balance,'[^0-9.\\-]','','g'),'')::numeric >= 1000000
             THEN 0 ELSE NULLIF(regexp_replace(a.account_balance,'[^0-9.\\-]','','g'),'')::numeric END,
        NULLIF(regexp_replace(a.credit,'[^0-9.\\-]','','g'),'')::numeric,
        a.account_group,
        CASE WHEN a.account_group ILIKE '%mt4%' THEN 'MT4' ELSE 'MT5' END,
        'tradesoft', NULL, NULL, cu.kyc_status, cu.customer_no, NULLIF(a.created_at,'')::timestamptz
      FROM {L}.fx_accounts_view a
      JOIN customers cu ON cu.customer_no='CUS'||lpad(a.user_id,6,'0')
      WHERE a.deleted_at IS NULL AND a.account_number ~ '^[0-9]+$' AND a.user_id ~ '^[0-9]+$'
        AND COALESCE(a.account_group,'') NOT ILIKE '%demo%'
        AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.login=a.account_number::bigint)
      ORDER BY a.account_number::bigint, a.updated_at DESC NULLS LAST
      ON CONFLICT (login) DO NOTHING""")).rowcount
    db.commit(); print(f"  new active accounts -> clients: {n:,}")

    n = db.execute(text("""
      INSERT INTO trading_accounts (login, name, group_name, platform, balance, credit,
          is_active, customer_no, source, kyc_status, country)
      SELECT c.login, c.name, c.group_name, c.platform, c.balance, c.credit, TRUE,
             c.customer_no, 'tradesoft', c.kyc_status, c.country
      FROM clients c WHERE c.source='tradesoft' AND c.archived_at IS NULL
        AND NOT EXISTS (SELECT 1 FROM trading_accounts t WHERE t.login=c.login)
      ON CONFLICT (login) DO NOTHING""")).rowcount
    db.commit(); print(f"  new active accounts -> trading_accounts: {n:,}")

    # DEMO accounts (TradeSoft account_type='Demo', e.g. 300k/50k seeded balances) must never
    # show as real: archive them with an explicit reason + stamp trading_accounts.account_type.
    # GOTCHA: 20k account NUMBERS exist as BOTH Live and Demo rows in fx_accounts_view (TradeSoft
    # re-uses numbers) — Live wins, so only archive numbers that are Demo-ONLY.
    nd = db.execute(text(f"""UPDATE clients c SET is_archived=TRUE,
          archive_reason=COALESCE(c.archive_reason,'demo account (TradeSoft)')
      WHERE NOT COALESCE(c.is_archived,false)
        AND EXISTS (SELECT 1 FROM {L}.fx_accounts_view a
                    WHERE a.account_number=c.login::text AND a.account_type='Demo')
        AND NOT EXISTS (SELECT 1 FROM {L}.fx_accounts_view a2
                    WHERE a2.account_number=c.login::text AND a2.account_type='Live')""")).rowcount
    db.execute(text(f"""UPDATE trading_accounts ta SET account_type='Demo'
      WHERE COALESCE(ta.account_type,'')<>'Demo'
        AND EXISTS (SELECT 1 FROM {L}.fx_accounts_view a
                    WHERE a.account_number=ta.login::text AND a.account_type='Demo')
        AND NOT EXISTS (SELECT 1 FROM {L}.fx_accounts_view a2
                    WHERE a2.account_number=ta.login::text AND a2.account_type='Live')"""))
    db.commit(); print(f"  demo-only accounts archived: {nd:,}")

    r = db.execute(text("""SELECT
        count(*) FILTER (WHERE archive_reason='tradesoft_not_on_mt') archived,
        count(*) FILTER (WHERE customer_no IS NOT NULL) with_cus, count(*) total FROM clients""")).fetchone()
    print(f"  clients now: {r[2]:,} (archived {r[0]:,}, with CUS {r[1]:,})")


def phase3(db):
    # TradeSoft leads (persons classified lead) -> our leads table, carrying their CUS.
    # campaign_name is taken from fx_leads_view.lead_source (e.g. 'Facebook Lead Campaign',
    # 'Facebook Recaptured', 'Webinar', 'company'); source is 'google' when lead_source is a
    # Google campaign, else 'tradesoft'. backfill_lead_contacts fills contacts that arrive later.

    # (a) DE-DUP vs Meta: Meta ads feed BOTH TradeSoft AND my1 at the same time, and my1's Meta
    # direct-fetch (every 5 min) already created the precise facebook/instagram lead BEFORE this
    # hourly TradeSoft sync runs. So if this TradeSoft person already exists as a Meta lead
    # (match by email OR phone last-9), ENRICH that fb/ig lead with the TradeSoft golden-record id +
    # sales agent instead of creating a 'meta' duplicate. Once the fb/ig lead carries the customer_no,
    # the INSERT's NOT EXISTS guard below skips it automatically — the fb/ig source is preserved.
    enr = db.execute(text(f"""
      UPDATE leads m SET
        customer_no        = COALESCE(NULLIF(TRIM(m.customer_no),''), cu.customer_no),
        legacy_sales_agent = COALESCE(NULLIF(TRIM(m.legacy_sales_agent),''),
            -- sales_rep is often a TradeSoft STAFF USER ID (e.g. 227419) — resolve to the name
            (SELECT NULLIF(TRIM(COALESCE(su.name,'')||' '||COALESCE(su.surname,'')),'')
               FROM {L}.fx_users_view su WHERE su.id = TRIM(v.sales_rep)),
            NULLIF(TRIM(v.sales_rep),''))
      FROM customers cu
      LEFT JOIN {L}.fx_leads_view v ON v.user_id::text = cu.legacy_user_id
      WHERE cu.kind='lead' AND m.source IN ('facebook','instagram')
        AND COALESCE(TRIM(m.customer_no),'')=''
        AND (
          (COALESCE(TRIM(cu.email),'')<>'' AND lower(TRIM(m.email))=lower(TRIM(cu.email)))
          OR (length(regexp_replace(COALESCE(cu.phone,''),'[^0-9]','','g'))>=9
              AND right(regexp_replace(COALESCE(m.phone,''),'[^0-9]','','g'),9)
                  = right(regexp_replace(cu.phone,'[^0-9]','','g'),9))
        )""")).rowcount
    db.commit(); print(f"  Meta leads enriched from TradeSoft (no dupe created): {enr:,}")

    # (b) insert the genuinely-new TradeSoft leads (guarded by customer_no AND email so a Meta
    #     lead for the same person is never duplicated).
    n = db.execute(text(f"""
      INSERT INTO leads (full_name, country, phone, email, source, campaign_name, legacy_sales_agent,
                         customer_no, status, stage, created_at)
      SELECT cu.name, cu.country, cu.phone, cu.email,
             -- MQL5 = referred by a country MQL5 IB (customers.ib text, e.g. 'Iraq-MQL5') — leads
             -- from mql5.com via our per-country IB links; highest priority.
             -- Google campaigns are numeric source 102 (IQ-Google-LandingPage) + 93 (google);
             -- the lead_source TEXT mostly defaults to 'company', so classify by the number.
             -- sales_agent = lead manually added by a sales rep.
             CASE WHEN cu.ib ILIKE '%MQL5%' THEN 'MQL5'
                  WHEN TRIM(v.source) IN ('95','97') THEN 'meta'   -- Meta ads (fb/ig unknown from TradeSoft)
                  WHEN TRIM(v.source) IN ('102','93') THEN 'google'
                  WHEN TRIM(v.lead_source)='sales_agent' THEN 'sales_agent'
                  ELSE 'tradesoft' END,
             CASE WHEN TRIM(v.source)='102' THEN 'IQ-Google-LandingPage'
                  WHEN TRIM(v.source)='93'  THEN 'google'
                  ELSE NULLIF(TRIM(v.lead_source),'') END,
             COALESCE(
               (SELECT NULLIF(TRIM(COALESCE(su.name,'')||' '||COALESCE(su.surname,'')),'')
                  FROM {L}.fx_users_view su WHERE su.id = TRIM(v.sales_rep)),
               NULLIF(TRIM(v.sales_rep),'')),
             cu.customer_no, 'new', 'new', NOW()
      FROM customers cu
      LEFT JOIN {L}.fx_leads_view v ON v.user_id::text = cu.legacy_user_id
      WHERE cu.kind='lead'
        AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.customer_no=cu.customer_no)
        AND NOT EXISTS (SELECT 1 FROM leads l2 WHERE COALESCE(TRIM(cu.email),'')<>''
                        AND lower(TRIM(l2.email))=lower(TRIM(cu.email)))
        AND NOT EXISTS (SELECT 1 FROM leads l3 WHERE l3.source IN ('facebook','instagram')
                        AND length(regexp_replace(COALESCE(cu.phone,''),'[^0-9]','','g'))>=9
                        AND right(regexp_replace(COALESCE(l3.phone,''),'[^0-9]','','g'),9)
                            = right(regexp_replace(cu.phone,'[^0-9]','','g'),9))""")).rowcount
    db.commit(); print(f"  TradeSoft leads inserted: {n:,}")

    # (c) VERIFICATION SYNC — people verify phone/email/KYC OVER TIME (after the lead first arrives).
    # For every lead linked to a TradeSoft user (via customer_no -> legacy_user_id -> fx_users_view),
    # UPGRADE its verification from TradeSoft's live flags: mobile_verify='1' (phone),
    # email_verified_at set (email), is_kyc_verified='1' (KYC). Upgrade-only (never downgrade), runs
    # every sync so a Meta-direct lead that later verifies in TradeSoft gets marked verified here.
    vf = db.execute(text(f"""
      UPDATE leads l SET
        phone_verified = CASE WHEN TRIM(u.mobile_verify)='1' THEN TRUE ELSE l.phone_verified END,
        email_verified = CASE WHEN COALESCE(TRIM(u.email_verified_at),'')<>''
                               AND u.email_verified_at NOT ILIKE '%0000-00-00%' THEN TRUE ELSE l.email_verified END,
        kyc_status     = CASE WHEN TRIM(u.is_kyc_verified)='1' THEN 'verified' ELSE l.kyc_status END,
        is_verified    = CASE WHEN TRIM(u.mobile_verify)='1'
                               AND COALESCE(TRIM(u.email_verified_at),'')<>'' THEN TRUE ELSE l.is_verified END
      FROM customers cu
      JOIN {L}.fx_users_view u ON u.id = cu.legacy_user_id
      WHERE l.customer_no = cu.customer_no
        AND (TRIM(u.mobile_verify)='1' OR TRIM(u.is_kyc_verified)='1'
             OR (COALESCE(TRIM(u.email_verified_at),'')<>'' AND u.email_verified_at NOT ILIKE '%0000-00-00%'))
        AND NOT (COALESCE(l.phone_verified,FALSE) AND COALESCE(l.email_verified,FALSE) AND l.kyc_status='verified')
    """)).rowcount
    db.commit(); print(f"  lead verification synced from TradeSoft (phone/email/KYC): {vf:,}")

    r = db.execute(text("SELECT count(*) FILTER (WHERE customer_no IS NOT NULL), count(*) FROM leads")).fetchone()
    print(f"  leads now: {r[1]:,} (with CUS {r[0]:,})")


def _batched(db, sql, ids, chunk=3000, label=""):
    """run `sql` (uses :ids) over login chunks with short locks + deadlock retry — coexists w/ live sync."""
    done = 0
    for i in range(0, len(ids), chunk):
        batch = ids[i:i+chunk]
        for attempt in range(8):
            try:
                db.execute(text("SET lock_timeout='4s'"))
                done += db.execute(text(sql), {"ids": batch}).rowcount
                db.commit(); break
            except Exception:
                db.rollback()
                if attempt == 7: raise
                time.sleep(1.5 * (attempt + 1))
    if label: print(f"  {label}: {done:,}")
    return done


def phase4(db):
    OFF = 8_000_000_000
    A = "NULLIF(regexp_replace(t.amount,'[^0-9.\\-]','','g'),'')::numeric"
    TYPE = """CASE WHEN t.type='withdrawal' THEN 'withdrawal' WHEN t.type='transfer' THEN 'internal_transfer'
        WHEN COALESCE(t.note,'') ~* 'negativ|cover' THEN 'negative_cover'
        WHEN COALESCE(t.note,'') ~* 'fix' THEN 'balance_fix' ELSE 'deposit' END"""

    # 1) IB/agent authoritative — materialize fixes (read-only) then batched UPDATE
    db.execute(text(f"""CREATE TEMP TABLE agent_fix AS
        SELECT c.login, a.agent FROM clients c JOIN {ACCT} a ON a.login=c.login
        WHERE a.agent IS NOT NULL AND COALESCE(c.agent,0)<>a.agent"""))
    db.commit()
    ids = [r[0] for r in db.execute(text("SELECT login FROM agent_fix")).fetchall()]
    _batched(db, "UPDATE clients c SET agent=af.agent FROM agent_fix af WHERE c.login=af.login AND c.login=ANY(:ids)",
             ids, label="IB/agent reconciled from TradeSoft")

    # 2) deposits/withdrawals from TradeSoft (deduped) — retry wrapper (transactions table)
    for attempt in range(8):
        try:
            db.execute(text("SET lock_timeout='6s'"))
            n = db.execute(text(f"""
              INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method, status, notes,
                                        tx_date, tx_month, created_at, updated_at)
              SELECT {OFF}+t.id::bigint, t.account_number::bigint, {TYPE}, {A},
                COALESCE(NULLIF(t.currency,''),'USD'), COALESCE(NULLIF(t.payment_method,''),'TradeSoft'),
                'approved', COALESCE(NULLIF(t.note,''),'TradeSoft import'), t.created_at, left(t.created_at,7),
                NULLIF(t.created_at,'')::timestamptz, NOW()
              FROM {L}.fx_transactions_view t
              WHERE t.deleted_at IS NULL AND t.status='completed' AND t.account_number ~ '^[0-9]+$'
                AND {A}>0 AND {A}<1000000
                AND ((t.type='deposit' AND COALESCE(t.payment_method,'')<>'0') OR t.type IN ('withdrawal','transfer'))
                AND NOT EXISTS (SELECT 1 FROM transactions e WHERE e.deal_id={OFF}+t.id::bigint)
                AND NOT EXISTS (SELECT 1 FROM transactions x WHERE x.login=t.account_number::bigint AND x.deal_id<{OFF}
                    AND x.tx_type={TYPE} AND round(x.amount::numeric,2)=round({A},2) AND left(x.tx_date,10)=left(t.created_at,10))
              ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING""")).rowcount
            db.commit(); print(f"  TradeSoft transactions imported: {n:,}"); break
        except Exception:
            db.rollback()
            if attempt == 7: raise
            time.sleep(2 * (attempt + 1))

    # 3) client totals (real deposits only) — materialize then batched UPDATE
    db.execute(text("""CREATE TEMP TABLE tot AS SELECT login,
        ROUND(SUM(amount) FILTER (WHERE tx_type='deposit' AND amount<1000000
          AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust')::numeric,2) dep,
        ROUND(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000)::numeric,2) wd
        FROM transactions GROUP BY login"""))
    db.commit()
    ids = [r[0] for r in db.execute(text("SELECT login FROM tot")).fetchall()]
    _batched(db, """UPDATE clients c SET total_deposits=COALESCE(t.dep,0), total_withdrawals=COALESCE(t.wd,0)
             FROM tot t WHERE t.login=c.login AND c.login=ANY(:ids)""", ids, label="client totals updated")

    # 4) roll up to customers + verify depositors (customers table not touched by live sync -> one shot)
    db.execute(text("""WITH ct AS (SELECT customer_no, sum(total_deposits) dep, sum(total_withdrawals) wd
        FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no)
      UPDATE customers cu SET total_deposits=ROUND(COALESCE(ct.dep,0)::numeric,2),
                              total_withdrawals=ROUND(COALESCE(ct.wd,0)::numeric,2),
                              kind=CASE WHEN COALESCE(ct.dep,0)>0 THEN 'client' ELSE cu.kind END,
                              kyc_status=CASE WHEN COALESCE(ct.dep,0)>0 THEN 'verified' ELSE cu.kyc_status END
      FROM ct WHERE ct.customer_no=cu.customer_no"""))
    db.commit()
    r = db.execute(text("SELECT count(*) FILTER (WHERE total_deposits>0), round(sum(total_deposits)) FROM customers")).fetchone()
    print(f"  customers with real deposits: {r[0]:,}  total ${float(r[1] or 0):,.0f}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        ph = sys.argv[sys.argv.index("--phase")+1] if "--phase" in sys.argv else "1"
        schema(db)
        {"1": phase1, "2": phase2, "3": phase3, "4": phase4}[ph](db)
        print("DONE phase", ph)
    finally:
        db.close()
