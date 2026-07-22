"""
Fix (Jul 2026, scooter8exo case): three related data problems found via a real client
(Mohammed Kadhim Fadhil, CUS160609) who "looked new" but wasn't.

1) MISSING REAL DEPOSITS: the TradeSoft transaction import excluded EVERY deposit with
   payment_method='0'. That correctly dropped demo/NDA seeds (300k/50k credits) but ALSO
   dropped real client money recorded without a gateway (his $98 first deposit, 2025-10-09).
   Import method-0 completed deposits using a CLEAN rule: account_type='Live', not NDA,
   not contest, amount 1..20,000. (>20k method-0 are internal credits — avg ~$300k.)

2) DEMO ACCOUNTS SHOWN AS REAL: 71k TradeSoft 'Demo' accounts imported as clients; ~2.2k
   still visible (e.g. his 50,000 "balance"). Archive them with reason 'demo account' and
   stamp trading_accounts.account_type='Demo'.

3) WRONGLY ARCHIVED/INACTIVE DEPOSIT ACCOUNTS: accounts with a REAL deposit in the last 30
   days must be visible+active (his 5011203 was is_archived=TRUE with no reason).

Then: same-day MT dedup on the new rows, totals recompute, client_tx_agg marked stale so the
Clients list (incl. the "Newest" first-deposit sort) rebuilds. Idempotent.
Run: python import_missing_ts_deposits.py [--dry-run]
"""
import sys
import db_config

DRY = "--dry-run" in sys.argv
OFF = 8_000_000_000
A = "NULLIF(regexp_replace(t.amount,'[^0-9.\\-]','','g'),'')::numeric"

conn = db_config.connect(); cur = conn.cursor()

# ---------- 1) import missing clean method-0 LIVE deposits ----------
cur.execute(f"""
  WITH ins AS (
    INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method, status, notes,
                              tx_date, tx_month, created_at, updated_at)
    SELECT {OFF}+t.id::bigint, t.account_number::bigint, 'deposit', {A},
           COALESCE(NULLIF(t.currency,''),'USD'), 'TradeSoft',
           'approved', 'TradeSoft import (no gateway recorded)', t.created_at, left(t.created_at,7),
           NULLIF(t.created_at,'')::timestamptz, NOW()
    FROM tradesoft_old.fx_transactions_view t
    JOIN tradesoft_old.fx_accounts_view a ON a.account_number=t.account_number
         AND a.account_type='Live' AND COALESCE(a.is_nda,'0')<>'1' AND a.contest_joined_date IS NULL
    WHERE t.type='deposit' AND t.status='completed' AND COALESCE(t.payment_method,'')='0'
      AND t.deleted_at IS NULL AND t.account_number ~ '^[0-9]+$'
      AND {A} BETWEEN 1 AND 20000
      AND NOT EXISTS (SELECT 1 FROM transactions e WHERE e.deal_id={OFF}+t.id::bigint)
    ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING
    RETURNING login)
  SELECT COALESCE(array_agg(DISTINCT login),'{{}}') FROM ins""")
affected = list(cur.fetchone()[0] or [])
print(f"imported missing deposits for {len(affected)} logins")
if DRY:
    conn.rollback(); print("DRY RUN — rolled back"); sys.exit(0)
conn.commit()

if affected:
    # same-day MT dedup (same rule as tradesoft_sync #2)
    cur.execute("""UPDATE transactions l SET tx_type=l.tx_type||'_dup'
        WHERE l.deal_id>=8000000000 AND l.tx_type IN ('deposit','withdrawal') AND l.login=ANY(%s)
          AND EXISTS (SELECT 1 FROM transactions m WHERE m.deal_id<8000000000 AND m.tx_type=l.tx_type
             AND m.login=l.login AND round(m.amount::numeric,2)=round(l.amount::numeric,2)
             AND left(m.tx_date,10)=left(l.tx_date,10))""", (affected,))
    print(f"  same-day MT dedup flagged: {cur.rowcount}")
    conn.commit()
    # recompute client + customer totals for affected logins (chunked)
    CH = 4000
    for i in range(0, len(affected), CH):
        lg = affected[i:i+CH]
        cur.execute("""WITH agg AS (SELECT login,
            ROUND(SUM(amount) FILTER (WHERE tx_type='deposit' AND amount<1000000
              AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust')::numeric,2) dep,
            ROUND(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000)::numeric,2) wd
            FROM transactions WHERE login = ANY(%s) GROUP BY login)
          UPDATE clients c SET total_deposits=COALESCE(agg.dep,0), total_withdrawals=COALESCE(agg.wd,0)
          FROM agg WHERE agg.login=c.login""", (lg,))
        cur.execute("""WITH ct AS (SELECT customer_no, sum(total_deposits) dep, sum(total_withdrawals) wd
            FROM clients WHERE customer_no IN (SELECT DISTINCT customer_no FROM clients WHERE login = ANY(%s))
            GROUP BY customer_no)
          UPDATE customers cu SET total_deposits=ROUND(COALESCE(ct.dep,0)::numeric,2),
            total_withdrawals=ROUND(COALESCE(ct.wd,0)::numeric,2),
            kind=CASE WHEN COALESCE(ct.dep,0)>0 THEN 'client' ELSE cu.kind END
          FROM ct WHERE ct.customer_no=cu.customer_no""", (lg,))
        conn.commit()
    print("  totals recomputed")

# ---------- 2) demo accounts: archive + stamp type ----------
# GOTCHA: ~20k account NUMBERS exist as BOTH Live and Demo rows in fx_accounts_view (TradeSoft
# re-uses numbers). Live wins — only Demo-ONLY numbers may be archived/stamped. A plain
# EXISTS(Demo) join once wrongly archived 1,605 live accounts (incl. an account that had just
# deposited). Keep the NOT EXISTS(Live) guard.
cur.execute("""UPDATE clients c SET is_archived=TRUE,
      archive_reason=COALESCE(c.archive_reason,'demo account (TradeSoft)')
  WHERE NOT COALESCE(c.is_archived,false)
    AND EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a
                WHERE a.account_number=c.login::text AND a.account_type='Demo')
    AND NOT EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a2
                WHERE a2.account_number=c.login::text AND a2.account_type='Live')""")
print(f"demo-only accounts archived: {cur.rowcount}")
cur.execute("""UPDATE trading_accounts ta SET account_type='Demo'
  WHERE COALESCE(ta.account_type,'')<>'Demo'
    AND EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a
                WHERE a.account_number=ta.login::text AND a.account_type='Demo')
    AND NOT EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a2
                WHERE a2.account_number=ta.login::text AND a2.account_type='Live')""")
print(f"trading_accounts stamped Demo: {cur.rowcount}")
conn.commit()

# ---------- 3) reactivate accounts with a real deposit in the last 30 days ----------
cur.execute("""UPDATE clients c SET is_archived=FALSE, archive_reason=NULL, is_active=TRUE
  WHERE COALESCE(c.is_archived,false)
    AND EXISTS (SELECT 1 FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit'
                AND left(t.tx_date,10) >= to_char(now()-interval '30 days','YYYY-MM-DD'))
    AND NOT (EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a
                     WHERE a.account_number=c.login::text AND a.account_type='Demo')
             AND NOT EXISTS (SELECT 1 FROM tradesoft_old.fx_accounts_view a2
                     WHERE a2.account_number=c.login::text AND a2.account_type='Live'))""")
print(f"recent-depositor accounts reactivated: {cur.rowcount}")
conn.commit()

# ---------- 4) force client_tx_agg rebuild (drives list numbers + 'Newest' sort) ----------
cur.execute("UPDATE client_tx_agg_meta SET refreshed_at = NOW() - interval '10 years' WHERE id=1")
conn.commit()
print("client_tx_agg marked stale (rebuilds on next list load)")
conn.close()
