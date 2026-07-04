"""
export_depositors_csv.py — CSV of the ~24.6k REAL depositor clients with full money + ownership detail.
Computes figures from BOTH sources (live MT transactions + non-duplicate legacy rows) so it is accurate
even before the legacy import is committed. Output: C:\\Broker-crm\\exports\\real_depositor_clients.csv
"""
import os, csv
from sqlalchemy import text
from database import SessionLocal

OFFSET = 8_000_000_000
T = "tradesoft_old"
A = "NULLIF(regexp_replace(t.amount,'[^0-9.\\-]','','g'),'')::numeric"
A2 = "NULLIF(regexp_replace(t2.amount,'[^0-9.\\-]','','g'),'')::numeric"
OUT = r"C:\Broker-crm\exports\real_depositor_clients.csv"

DEPOSITORS_SQL = f"""
  SELECT DISTINCT t.account_number::bigint login FROM {T}.fx_transactions_view t
   WHERE t.deleted_at IS NULL AND t.status='completed' AND t.account_number ~ '^[0-9]+$'
     AND t.type='deposit' AND COALESCE(t.bonus_id,'') IN ('','0') AND COALESCE(t.payment_method,'')<>'0'
     AND {A}>0 AND {A}<1000000 AND COALESCE(t.note,'') !~* 'fix|negativ|bonus|welcome|cover'
  UNION
  SELECT DISTINCT login FROM transactions WHERE tx_type='deposit' AND amount>0 AND amount<1000000
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


def run():
    db = SessionLocal()
    try:
        db.execute(text(f"CREATE TEMP TABLE rd AS {DEPOSITORS_SQL}"))
        db.execute(text("CREATE INDEX ON rd(login)"))
        n = db.execute(text("SELECT count(*) FROM rd")).scalar()
        print(f"real depositors: {n:,}")

        # small indexed key table of MT rows for fast dedup of legacy against MT
        db.execute(text(f"""CREATE TEMP TABLE mt_keys AS
          SELECT login, tx_type, round(amount::numeric,2) amt_r, left(tx_date,10) daystr
          FROM transactions WHERE deal_id<{OFFSET} AND tx_type IN ('deposit','withdrawal')
            AND amount>0 AND amount<1000000 AND login IN (SELECT login FROM rd)"""))
        db.execute(text("CREATE INDEX ON mt_keys(login, tx_type, amt_r, daystr)"))

        # unified deposit/withdraw events (MT real + non-dup legacy real), restricted to depositors
        db.execute(text(f"""CREATE TEMP TABLE utx AS
          SELECT login, 'dep' kind, amount amt, NULLIF(tx_date,'')::timestamptz dt FROM transactions
            WHERE deal_id<{OFFSET} AND tx_type='deposit' AND amount>0 AND amount<1000000
              AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust'
              AND login IN (SELECT login FROM rd)
          UNION ALL
          SELECT login,'wd', amount, NULLIF(tx_date,'')::timestamptz FROM transactions
            WHERE deal_id<{OFFSET} AND tx_type='withdrawal' AND amount>0 AND amount<1000000
              AND login IN (SELECT login FROM rd)
          UNION ALL
          SELECT t.account_number::bigint,'dep',{A},NULLIF(t.created_at,'')::timestamptz
            FROM {T}.fx_transactions_view t
            WHERE t.deleted_at IS NULL AND t.status='completed' AND t.type='deposit' AND t.account_number ~ '^[0-9]+$'
              AND COALESCE(t.bonus_id,'') IN ('','0') AND COALESCE(t.payment_method,'')<>'0'
              AND {A}>0 AND {A}<1000000
              AND COALESCE(t.note,'') !~* 'fix|negativ|bonus|welcome|cover'
              AND t.account_number::bigint IN (SELECT login FROM rd)
              AND NOT EXISTS (SELECT 1 FROM mt_keys k WHERE k.login=t.account_number::bigint
                AND k.tx_type='deposit' AND k.amt_r=round({A},2) AND k.daystr=left(t.created_at,10))
          UNION ALL
          SELECT t.account_number::bigint,'wd',{A},NULLIF(t.created_at,'')::timestamptz
            FROM {T}.fx_transactions_view t
            WHERE t.deleted_at IS NULL AND t.status='completed' AND t.type='withdrawal' AND t.account_number ~ '^[0-9]+$'
              AND {A}>0 AND {A}<1000000
              AND t.account_number::bigint IN (SELECT login FROM rd)
              AND NOT EXISTS (SELECT 1 FROM mt_keys k WHERE k.login=t.account_number::bigint
                AND k.tx_type='withdrawal' AND k.amt_r=round({A},2) AND k.daystr=left(t.created_at,10))
        """))
        db.execute(text("CREATE INDEX ON utx(login)"))

        # one legacy account row per login (for owner/agent), deduped
        db.execute(text(f"""CREATE TEMP TABLE la AS
          SELECT DISTINCT ON (account_number::bigint) account_number::bigint login, user_id,
                 CASE WHEN agent ~ '^[0-9]+$' THEN agent::bigint END agent
          FROM {T}.fx_accounts_view
          WHERE deleted_at IS NULL AND account_number ~ '^[0-9]+$'
          ORDER BY account_number::bigint, updated_at DESC NULLS LAST"""))
        db.execute(text("CREATE INDEX ON la(login)"))

        rows = db.execute(text(f"""
          WITH agg AS (
            SELECT login,
              ROUND(SUM(amt) FILTER (WHERE kind='dep')::numeric,2) tot_dep,
              COUNT(*)        FILTER (WHERE kind='dep') dep_cnt,
              MIN(dt)         FILTER (WHERE kind='dep') first_dep,
              MAX(dt)         FILTER (WHERE kind='dep') last_dep,
              ROUND(SUM(amt) FILTER (WHERE kind='wd')::numeric,2) tot_wd,
              COUNT(*)        FILTER (WHERE kind='wd') wd_cnt,
              MIN(dt)         FILTER (WHERE kind='wd') first_wd,
              MAX(dt)         FILTER (WHERE kind='wd') last_wd
            FROM utx GROUP BY login)
          SELECT rd.login,
            COALESCE(cl.name, NULLIF(trim(COALESCE(lu.name,'')||' '||COALESCE(lu.surname,'')),'')) name,
            COALESCE(cl.country, lc.country, ll.country) country,
            CASE WHEN COALESCE(cl.platform,'')='MT4' THEN 'MT4' ELSE 'MT5' END platform,
            cl.email, cl.phone,
            COALESCE(cl.kyc_status, CASE WHEN cl.login IS NULL THEN 'archived(new)' ELSE 'existing' END) status,
            CASE WHEN cl.login IS NULL THEN 'legacy' ELSE 'existing' END source,
            COALESCE(agg.tot_dep,0) tot_dep, COALESCE(agg.dep_cnt,0) dep_cnt,
            agg.first_dep, agg.last_dep,
            COALESCE(agg.tot_wd,0) tot_wd, COALESCE(agg.wd_cnt,0) wd_cnt,
            agg.first_wd, agg.last_wd,
            ROUND((COALESCE(agg.tot_dep,0)-COALESCE(agg.tot_wd,0))::numeric,2) net_dep,
            COALESCE(cl.agent, la.agent) ib_login,
            ib.name ib_name,
            sr.sales_rep sales_agent_id,
            NULLIF(trim(COALESCE(su.name,'')||' '||COALESCE(su.surname,'')),'') sales_agent
          FROM rd
          LEFT JOIN agg ON agg.login=rd.login
          LEFT JOIN clients cl ON cl.login=rd.login
          LEFT JOIN la ON la.login=rd.login
          LEFT JOIN (SELECT DISTINCT ON (id) id, name, surname FROM {T}.fx_users_view ORDER BY id) lu ON lu.id=la.user_id
          LEFT JOIN (SELECT DISTINCT ON (user_id) user_id, country FROM {T}.fx_clients_view ORDER BY user_id) lc ON lc.user_id=la.user_id
          LEFT JOIN (SELECT DISTINCT ON (user_id) user_id, country FROM {T}.fx_leads_view ORDER BY user_id) ll ON ll.user_id=la.user_id
          LEFT JOIN clients ib ON ib.login = COALESCE(cl.agent, la.agent)
          LEFT JOIN LATERAL (SELECT NULLIF(sales_rep,'0') sales_rep FROM {T}.fx_leads_view
                             WHERE user_id=la.user_id AND COALESCE(sales_rep,'') NOT IN ('','0') LIMIT 1) sr ON TRUE
          LEFT JOIN (SELECT DISTINCT ON (id) id, name, surname FROM {T}.fx_users_view ORDER BY id) su ON su.id::text = sr.sales_rep
          ORDER BY COALESCE(agg.tot_dep,0) DESC
        """)).fetchall()

        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        hdr = ["login","name","country","platform","email","phone","status","source",
               "total_deposit","deposit_count","first_deposit","last_deposit",
               "total_withdraw","withdraw_count","first_withdraw","last_withdraw","net_deposit",
               "ib_login","ib_name","sales_agent_id","sales_agent"]
        def d(x): return x.strftime("%Y-%m-%d") if x else ""
        with open(OUT,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(hdr)
            for r in rows:
                w.writerow([r.login, r.name or "", r.country or "", r.platform, r.email or "", r.phone or "",
                    r.status or "", r.source, r.tot_dep, r.dep_cnt, d(r.first_dep), d(r.last_dep),
                    r.tot_wd, r.wd_cnt, d(r.first_wd), d(r.last_wd), r.net_dep,
                    r.ib_login or "", r.ib_name or "", r.sales_agent_id or "", r.sales_agent or ""])
        print(f"wrote {len(rows):,} rows -> {OUT}")
        # quick sanity totals
        td = sum(float(r.tot_dep or 0) for r in rows); tw = sum(float(r.tot_wd or 0) for r in rows)
        print(f"sum deposits ${td:,.0f} | sum withdrawals ${tw:,.0f}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
