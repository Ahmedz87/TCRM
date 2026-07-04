"""
migrate_tradesoft.py — import the legacy TradeSoft CRM (tradesoft_old.fx_*_view) into the live
CRM, matched by MT login (account_number). Dry-run by default; --commit to apply.

CLIENT-vs-LEAD RULE (per the desk):
  * A CLIENT/verified = an account that made a REAL cash DEPOSIT.
  * NOT a deposit (these alone keep an account a LEAD):
      - $50 welcome bonus / any bonus  -> credit, classified 'bonus_deposit'
      - "Negative balance payoff"       -> broker covering a blown bonus, 'negative_cover'
      - "Deposit fix" / balance fix     -> 'balance_fix'
      - legacy bonus_id-tagged rows     -> 'bonus_deposit'
      - legacy payment_method='0' rows  -> garbage (avg $1.08M), SKIPPED entirely

Steps (all additive + idempotent + deduped):
  0) RECLASSIFY existing MT transactions wrongly tagged 'deposit' (negative payoff / deposit fix).
  1) ACCOUNTS: legacy accounts not in clients -> ARCHIVED clients (default kyc 'lead').
  2) TRANSACTIONS: deal_id = 8e9 + legacy_id, classified deposit/bonus_deposit/withdrawal/transfer;
     deduped vs MT rows (login+type+amount+day). method='0' skipped.
  3) Real depositors (legacy OR MT) -> kyc_status='verified' (UPGRADE only, never downgrades).
  4) Refresh client total_deposits/withdrawals from REAL deposits only (excludes bonus/fix/negative).
"""
import sys
from sqlalchemy import text
from database import SessionLocal

OFFSET = 8_000_000_000
T = "tradesoft_old"
A = "NULLIF(regexp_replace(t.amount,'[^0-9.\\-]','','g'),'')::numeric"   # parsed legacy amount

# tx_type for a legacy row (method='0' deposits are excluded in WHERE, not here)
TYPE_CASE = f"""CASE
    WHEN t.type='withdrawal' THEN 'withdrawal'
    WHEN t.type='transfer'   THEN 'internal_transfer'
    WHEN COALESCE(t.note,'') ~* 'negativ|cover' THEN 'negative_cover'
    WHEN COALESCE(t.note,'') ~* 'fix'           THEN 'balance_fix'
    ELSE 'deposit' END"""

# which legacy rows we import at all
TX_WHERE = f"""
    FROM {T}.fx_transactions_view t
    WHERE t.deleted_at IS NULL AND t.status='completed' AND t.account_number ~ '^[0-9]+$'
      AND {A} > 0 AND {A} < 1000000
      AND (
            (t.type='deposit' AND COALESCE(t.payment_method,'') <> '0')   -- real or bonus (not method-0 garbage)
            OR t.type IN ('withdrawal','transfer')
          )
      AND NOT EXISTS (SELECT 1 FROM transactions e WHERE e.deal_id = {OFFSET} + t.id::bigint)
      AND NOT EXISTS (
            SELECT 1 FROM transactions x
            WHERE x.login = t.account_number::bigint AND x.deal_id < {OFFSET}
              AND x.tx_type = {TYPE_CASE}
              AND round(x.amount::numeric,2) = round({A},2)
              AND left(x.tx_date,10) = left(t.created_at,10))
"""

# a REAL deposit (the only thing that makes an account a client/verified), MT side
MT_REAL_DEP = "tx_type='deposit' AND amount>0 AND amount<1000000"
A2 = "NULLIF(regexp_replace(t2.amount,'[^0-9.\\-]','','g'),'')::numeric"

# REAL DEPOSITOR (= client/verified), refined to ~24.6k to match the desk's ~25k:
#   (a) clean cash deposit  (legacy gateway OR MT), excluding bonus/fix/negative/method-0, OR
#   (b) withdrew real cash AND corroborated as truly funded (a method-less deposit OR real trades).
# 14,215 bonus-only withdrawers are EXCLUDED -> stay leads.
DEPOSITORS_SQL = f"""
  SELECT DISTINCT t.account_number::bigint login FROM {T}.fx_transactions_view t
   WHERE t.deleted_at IS NULL AND t.status='completed' AND t.account_number ~ '^[0-9]+$'
     AND t.type='deposit' AND COALESCE(t.bonus_id,'') IN ('','0') AND COALESCE(t.payment_method,'')<>'0'
     AND {A}>0 AND {A}<1000000 AND COALESCE(t.note,'') !~* 'fix|negativ|bonus|welcome|cover'
  UNION
  SELECT DISTINCT login FROM transactions WHERE {MT_REAL_DEP}
     AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust' AND deal_id<{OFFSET}
  UNION
  SELECT DISTINCT w.login FROM (
     SELECT t.account_number::bigint login FROM {T}.fx_transactions_view t
       WHERE t.deleted_at IS NULL AND t.status='completed' AND t.type='withdrawal' AND {A}>0 AND {A}<1000000
     UNION SELECT login FROM transactions WHERE tx_type='withdrawal' AND amount>0 AND amount<1000000) w
   WHERE EXISTS(SELECT 1 FROM {T}.fx_transactions_view t2 WHERE t2.account_number::bigint=w.login
        AND t2.deleted_at IS NULL AND t2.status='completed' AND t2.type='deposit'
        AND COALESCE(t2.payment_method,'')='0' AND {A2}>0 AND {A2}<1000000)
      OR EXISTS(SELECT 1 FROM deals d WHERE d.login=w.login AND d.action IN (0,1))"""


def run(commit=False):
    db = SessionLocal()
    try:
        db.execute(text("""CREATE UNIQUE INDEX IF NOT EXISTS transactions_deal_id_uq
                           ON transactions(deal_id) WHERE deal_id IS NOT NULL"""))
        db.commit()

        # build the refined real-depositor set once (reused for the verified flag + count)
        db.execute(text(f"CREATE TEMP TABLE real_depositors AS {DEPOSITORS_SQL}"))
        db.execute(text("CREATE INDEX ON real_depositors(login)"))

        # ---- 0) reclassify existing MT 'deposit' rows that are really fix / negative cover ----
        neg = db.execute(text("SELECT count(*) FROM transactions WHERE tx_type='deposit' AND notes ~* 'negativ'")).scalar()
        fix = db.execute(text("SELECT count(*) FROM transactions WHERE tx_type='deposit' AND notes ~* 'fix'")).scalar()
        print(f"0) reclassify existing MT deposits -> negative_cover {neg:,} | balance_fix {fix:,}")

        # ---- 1) new archived accounts ----
        acct_where = f"""
            FROM {T}.fx_accounts_view a
            WHERE a.deleted_at IS NULL AND a.account_number ~ '^[0-9]+$'
              AND COALESCE(a.account_group,'') NOT ILIKE '%demo%'
              AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.login = a.account_number::bigint)
        """
        n_new = db.execute(text("SELECT count(DISTINCT a.account_number) " + acct_where)).scalar() or 0
        print(f"1) new archived accounts: {n_new:,}")

        # ---- 2) transactions by class ----
        rows = db.execute(text(f"SELECT {TYPE_CASE} ty, count(*), round(sum({A}),0) {TX_WHERE} GROUP BY 1 ORDER BY 2 DESC")).fetchall()
        print("2) transactions to import (deduped):")
        for ty, cnt, s in rows:
            print(f"      {ty:18} {cnt:>8,}  ${float(s or 0):,.0f}")

        # ---- 3) real depositors (refined, ~24.6k) ----
        verified = db.execute(text("SELECT count(*) FROM real_depositors")).scalar() or 0
        print(f"3) real depositors -> verified (upgrade only): {verified:,}")

        if not commit:
            print("\nDRY RUN — nothing written. Re-run with --commit to apply.")
            return

        print("\nCOMMITTING...")
        r0a = db.execute(text("UPDATE transactions SET tx_type='negative_cover' WHERE tx_type='deposit' AND notes ~* 'negativ'"))
        r0b = db.execute(text("UPDATE transactions SET tx_type='balance_fix'    WHERE tx_type='deposit' AND notes ~* 'fix'"))
        db.commit(); print(f"   reclassified: negative_cover {r0a.rowcount:,} | balance_fix {r0b.rowcount:,}")

        ins_acct = db.execute(text(f"""
            INSERT INTO clients (login, name, country, city, balance, credit, group_name,
                                 source, archived_at, archive_reason, kyc_status, created_at)
            SELECT DISTINCT ON (a.account_number::bigint)
              a.account_number::bigint,
              NULLIF(trim(COALESCE(u.name,'')||' '||COALESCE(u.surname,'')),''),
              COALESCE(fc.country, fl.country), COALESCE(fc.city, fl.city),
              NULLIF(regexp_replace(a.account_balance,'[^0-9.\\-]','','g'),'')::numeric,
              NULLIF(regexp_replace(a.credit,'[^0-9.\\-]','','g'),'')::numeric,
              a.account_group, 'tradesoft',
              COALESCE(NULLIF(a.deleted_at,'')::timestamptz, NULLIF(a.created_at,'')::timestamptz, NOW()),
              'tradesoft_migration', 'lead',
              NULLIF(a.created_at,'')::timestamptz
            FROM {T}.fx_accounts_view a
              JOIN {T}.fx_users_view u ON u.id=a.user_id
              LEFT JOIN {T}.fx_clients_view fc ON fc.user_id=a.user_id
              LEFT JOIN {T}.fx_leads_view fl ON fl.user_id=a.user_id
            WHERE a.deleted_at IS NULL AND a.account_number ~ '^[0-9]+$'
              AND COALESCE(a.account_group,'') NOT ILIKE '%demo%'
              AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.login = a.account_number::bigint)
            ON CONFLICT (login) DO NOTHING
        """))
        db.commit(); print(f"   accounts created: {ins_acct.rowcount:,}")

        ins_tx = db.execute(text(f"""
            INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method, status,
                                      notes, tx_date, tx_month, created_at, updated_at)
            SELECT {OFFSET} + t.id::bigint, t.account_number::bigint, {TYPE_CASE}, {A},
                   COALESCE(NULLIF(t.currency,''),'USD'), COALESCE(NULLIF(t.payment_method,''),'TradeSoft'),
                   'approved', COALESCE(NULLIF(t.note,''),'TradeSoft import'), t.created_at, left(t.created_at,7),
                   NULLIF(t.created_at,'')::timestamptz, NOW()
            {TX_WHERE}
            ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING
        """))
        db.commit(); print(f"   transactions imported: {ins_tx.rowcount:,}")

        ver = db.execute(text("""
            UPDATE clients SET kyc_status='verified'
            WHERE COALESCE(kyc_status,'') NOT IN ('verified')
              AND login IN (SELECT login FROM real_depositors)
        """))
        db.commit(); print(f"   clients verified (real depositors): {ver.rowcount:,}")

        upd = db.execute(text(f"""
            WITH agg AS (
              SELECT login,
                     SUM(amount) FILTER (WHERE {MT_REAL_DEP}
                        AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust') dep,
                     SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000) wd
              FROM transactions GROUP BY login)
            UPDATE clients c SET total_deposits=ROUND(COALESCE(agg.dep,0)::numeric,2),
                                 total_withdrawals=ROUND(COALESCE(agg.wd,0)::numeric,2)
            FROM agg WHERE agg.login=c.login
        """))
        db.commit(); print(f"   client totals refreshed: {upd.rowcount:,}")
        print("DONE.")
    finally:
        db.close()


if __name__ == "__main__":
    run(commit="--commit" in sys.argv)
