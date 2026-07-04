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
        db.execute(text(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS customer_no TEXT"))
        db.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{t}_customer ON {t}(customer_no)"))
    db.commit()
    print("schema ready (customers + customer_no columns)")


def phase1(db):
    n = db.execute(text(f"""
      INSERT INTO customers (customer_no, legacy_user_id, name, country, kind, kyc_status)
      SELECT 'CUS'||lpad(u.id,6,'0'), u.id,
        NULLIF(trim(COALESCE(u.name,'')||' '||COALESCE(u.surname,'')),''),
        COALESCE(cl.country, ll.country),
        CASE WHEN cl.user_id IS NOT NULL THEN 'client' ELSE 'lead' END,
        CASE WHEN u.is_kyc_verified='1' THEN 'verified' ELSE 'pending' END
      FROM {L}.fx_users_view u
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
    # archived = TradeSoft real accounts NOT on MT (not already in clients)
    n = db.execute(text(f"""
      INSERT INTO clients (login, name, country, balance, credit, group_name, platform,
          source, archived_at, archive_reason, kyc_status, customer_no, created_at)
      SELECT DISTINCT ON (a.account_number::bigint) a.account_number::bigint,
        cu.name, cu.country,
        NULLIF(regexp_replace(a.account_balance,'[^0-9.\\-]','','g'),'')::numeric,
        NULLIF(regexp_replace(a.credit,'[^0-9.\\-]','','g'),'')::numeric,
        a.account_group,
        CASE WHEN a.account_group ILIKE '%mt4%' THEN 'MT4' ELSE 'MT5' END,
        'tradesoft', COALESCE(NULLIF(a.deleted_at,'')::timestamptz, NULLIF(a.created_at,'')::timestamptz, NOW()),
        'tradesoft_not_on_mt', cu.kyc_status, cu.customer_no, NULLIF(a.created_at,'')::timestamptz
      FROM {L}.fx_accounts_view a
      JOIN customers cu ON cu.customer_no='CUS'||lpad(a.user_id,6,'0')
      WHERE a.deleted_at IS NULL AND a.account_number ~ '^[0-9]+$' AND a.user_id ~ '^[0-9]+$'
        AND COALESCE(a.account_group,'') NOT ILIKE '%demo%'
        AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.login=a.account_number::bigint)
      ORDER BY a.account_number::bigint, a.updated_at DESC NULLS LAST
      ON CONFLICT (login) DO NOTHING""")).rowcount
    db.commit(); print(f"  archived accounts -> clients: {n:,}")

    n = db.execute(text("""
      INSERT INTO trading_accounts (login, name, group_name, platform, balance, credit,
          is_active, customer_no, source, kyc_status, country)
      SELECT c.login, c.name, c.group_name, c.platform, c.balance, c.credit, FALSE,
             c.customer_no, 'tradesoft', c.kyc_status, c.country
      FROM clients c WHERE c.archive_reason='tradesoft_not_on_mt'
        AND NOT EXISTS (SELECT 1 FROM trading_accounts t WHERE t.login=c.login)
      ON CONFLICT (login) DO NOTHING""")).rowcount
    db.commit(); print(f"  archived accounts -> trading_accounts: {n:,}")

    r = db.execute(text("""SELECT
        count(*) FILTER (WHERE archive_reason='tradesoft_not_on_mt') archived,
        count(*) FILTER (WHERE customer_no IS NOT NULL) with_cus, count(*) total FROM clients""")).fetchone()
    print(f"  clients now: {r[2]:,} (archived {r[0]:,}, with CUS {r[1]:,})")


def phase3(db):
    # TradeSoft leads (persons classified lead) -> our leads table, carrying their CUS
    n = db.execute(text("""
      INSERT INTO leads (full_name, country, phone, email, source, customer_no, status, stage, created_at)
      SELECT cu.name, cu.country, cu.phone, cu.email, 'tradesoft', cu.customer_no, 'new', 'new', NOW()
      FROM customers cu WHERE cu.kind='lead'
        AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.customer_no=cu.customer_no)""")).rowcount
    db.commit(); print(f"  TradeSoft leads inserted: {n:,}")
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
