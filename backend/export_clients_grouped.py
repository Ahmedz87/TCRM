"""
export_clients_grouped.py — ONE ROW PER CLIENT (person = legacy user_id), rolling up ALL of that
person's trading accounts. Answers "clients have many accounts; show the client with all accounts".
Identity = user_id + name (legacy has no email/phone values; email/phone shown only where an account
is already live in our CRM). Output: C:\\Broker-crm\\exports\\real_depositor_clients_grouped.csv
"""
import os, csv
from sqlalchemy import text
from database import SessionLocal

OFFSET = 8_000_000_000
T = "tradesoft_old"
A = "NULLIF(regexp_replace(t.amount,'[^0-9.\\-]','','g'),'')::numeric"
A2 = "NULLIF(regexp_replace(t2.amount,'[^0-9.\\-]','','g'),'')::numeric"
OUT = r"C:\Broker-crm\exports\real_depositor_clients_grouped.csv"

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

        # persons who own >=1 depositor account
        db.execute(text(f"""CREATE TEMP TABLE dusers AS
          SELECT DISTINCT user_id FROM {T}.fx_accounts_view
          WHERE account_number ~ '^[0-9]+$' AND account_number::bigint IN (SELECT login FROM rd) AND user_id IS NOT NULL"""))
        db.execute(text("CREATE INDEX ON dusers(user_id)"))

        # person->account map: ALL accounts of those persons, + standalone depositor logins not in legacy
        db.execute(text(f"""CREATE TEMP TABLE pa AS
          SELECT login, user_id, person_key FROM (
            SELECT DISTINCT ON (a.account_number::bigint) a.account_number::bigint login,
                   a.user_id, a.user_id::text person_key
            FROM {T}.fx_accounts_view a
            WHERE a.account_number ~ '^[0-9]+$' AND a.user_id IN (SELECT user_id FROM dusers)
            ORDER BY a.account_number::bigint, a.updated_at DESC NULLS LAST) q
          UNION ALL
          SELECT rd.login, NULL::text, 'L'||rd.login
          FROM rd WHERE NOT EXISTS (SELECT 1 FROM {T}.fx_accounts_view a
             WHERE a.account_number ~ '^[0-9]+$' AND a.account_number::bigint=rd.login)"""))
        db.execute(text("CREATE INDEX ON pa(login)"))
        db.execute(text("CREATE INDEX ON pa(person_key)"))
        npa = db.execute(text("SELECT count(*) FROM pa")).scalar()
        npp = db.execute(text("SELECT count(DISTINCT person_key) FROM pa")).scalar()
        print(f"persons: {npp:,}   accounts rolled up: {npa:,}")

        # MT key table (dedup) for the person accounts
        db.execute(text(f"""CREATE TEMP TABLE mt_keys AS
          SELECT login, tx_type, round(amount::numeric,2) amt_r, left(tx_date,10) daystr
          FROM transactions WHERE deal_id<{OFFSET} AND tx_type IN ('deposit','withdrawal')
            AND amount>0 AND amount<1000000 AND login IN (SELECT login FROM pa)"""))
        db.execute(text("CREATE INDEX ON mt_keys(login, tx_type, amt_r, daystr)"))

        # unified REAL deposit/withdraw events across all person accounts
        db.execute(text(f"""CREATE TEMP TABLE utx AS
          SELECT login,'dep' kind, amount amt, NULLIF(tx_date,'')::timestamptz dt FROM transactions
            WHERE deal_id<{OFFSET} AND tx_type='deposit' AND amount>0 AND amount<1000000
              AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust'
              AND login IN (SELECT login FROM pa)
          UNION ALL
          SELECT login,'wd', amount, NULLIF(tx_date,'')::timestamptz FROM transactions
            WHERE deal_id<{OFFSET} AND tx_type='withdrawal' AND amount>0 AND amount<1000000
              AND login IN (SELECT login FROM pa)
          UNION ALL
          SELECT t.account_number::bigint,'dep',{A},NULLIF(t.created_at,'')::timestamptz
            FROM {T}.fx_transactions_view t
            WHERE t.deleted_at IS NULL AND t.status='completed' AND t.type='deposit' AND t.account_number ~ '^[0-9]+$'
              AND COALESCE(t.bonus_id,'') IN ('','0') AND COALESCE(t.payment_method,'')<>'0'
              AND {A}>0 AND {A}<1000000
              AND COALESCE(t.note,'') !~* 'fix|negativ|bonus|welcome|cover'
              AND t.account_number::bigint IN (SELECT login FROM pa)
              AND NOT EXISTS (SELECT 1 FROM mt_keys k WHERE k.login=t.account_number::bigint
                AND k.tx_type='deposit' AND k.amt_r=round({A},2) AND k.daystr=left(t.created_at,10))
          UNION ALL
          SELECT t.account_number::bigint,'wd',{A},NULLIF(t.created_at,'')::timestamptz
            FROM {T}.fx_transactions_view t
            WHERE t.deleted_at IS NULL AND t.status='completed' AND t.type='withdrawal' AND t.account_number ~ '^[0-9]+$'
              AND {A}>0 AND {A}<1000000 AND t.account_number::bigint IN (SELECT login FROM pa)
              AND NOT EXISTS (SELECT 1 FROM mt_keys k WHERE k.login=t.account_number::bigint
                AND k.tx_type='withdrawal' AND k.amt_r=round({A},2) AND k.daystr=left(t.created_at,10))"""))
        db.execute(text("CREATE INDEX ON utx(login)"))

        rows = db.execute(text(f"""
          WITH ev AS (  -- attach person_key to each money event
            SELECT pa.person_key, u.kind, u.amt, u.dt FROM utx u JOIN pa ON pa.login=u.login),
          money AS (
            SELECT person_key,
              ROUND(SUM(amt) FILTER (WHERE kind='dep')::numeric,2) tot_dep,
              COUNT(*)        FILTER (WHERE kind='dep') dep_cnt,
              MIN(dt)         FILTER (WHERE kind='dep') first_dep,
              MAX(dt)         FILTER (WHERE kind='dep') last_dep,
              ROUND(SUM(amt) FILTER (WHERE kind='wd')::numeric,2) tot_wd,
              COUNT(*)        FILTER (WHERE kind='wd') wd_cnt,
              MAX(dt)         FILTER (WHERE kind='wd') last_wd
            FROM ev GROUP BY person_key),
          accts AS (  -- account list per person + which are live in our CRM
            SELECT pa.person_key,
              count(*) n_acct,
              count(*) FILTER (WHERE c.login IS NOT NULL) n_existing,
              string_agg(pa.login::text, ' | ' ORDER BY pa.login) account_logins,
              string_agg(DISTINCT CASE WHEN COALESCE(c.platform,'')='MT4' THEN 'MT4' ELSE 'MT5' END, '/') platforms,
              max(c.email) email, max(c.phone) phone, max(c.country) cl_country,
              max(c.agent) ib_login
            FROM pa LEFT JOIN clients c ON c.login=pa.login GROUP BY pa.person_key)
          SELECT a.person_key,
            COALESCE(NULLIF(trim(COALESCE(lu.name,'')||' '||COALESCE(lu.surname,'')),''),
                     'login '||a.person_key) name,
            COALESCE(a.cl_country, lc.country, ll.country) country,
            a.email, a.phone, a.n_acct, a.n_existing, a.account_logins, a.platforms,
            COALESCE(m.tot_dep,0) tot_dep, COALESCE(m.dep_cnt,0) dep_cnt, m.first_dep, m.last_dep,
            COALESCE(m.tot_wd,0) tot_wd, COALESCE(m.wd_cnt,0) wd_cnt, m.last_wd,
            ROUND((COALESCE(m.tot_dep,0)-COALESCE(m.tot_wd,0))::numeric,2) net_dep,
            ib.name ib_name,
            NULLIF(trim(COALESCE(su.name,'')||' '||COALESCE(su.surname,'')),'') sales_agent
          FROM accts a
          LEFT JOIN money m ON m.person_key=a.person_key
          LEFT JOIN (SELECT DISTINCT ON (id) id, name, surname FROM {T}.fx_users_view ORDER BY id) lu
                 ON a.person_key ~ '^[0-9]+$' AND lu.id=a.person_key
          LEFT JOIN (SELECT DISTINCT ON (user_id) user_id, country FROM {T}.fx_clients_view ORDER BY user_id) lc
                 ON a.person_key ~ '^[0-9]+$' AND lc.user_id=a.person_key
          LEFT JOIN (SELECT DISTINCT ON (user_id) user_id, country FROM {T}.fx_leads_view ORDER BY user_id) ll
                 ON a.person_key ~ '^[0-9]+$' AND ll.user_id=a.person_key
          LEFT JOIN clients ib ON ib.login=a.ib_login
          LEFT JOIN LATERAL (SELECT NULLIF(sales_rep,'0') sales_rep FROM {T}.fx_leads_view
                 WHERE a.person_key ~ '^[0-9]+$' AND user_id=a.person_key
                   AND COALESCE(sales_rep,'') NOT IN ('','0') LIMIT 1) sr ON TRUE
          LEFT JOIN (SELECT DISTINCT ON (id) id, name, surname FROM {T}.fx_users_view ORDER BY id) su
                 ON su.id::text=sr.sales_rep
          ORDER BY COALESCE(m.tot_dep,0) DESC
        """)).fetchall()

        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        hdr = ["client_id","name","country","email","phone","num_accounts","num_live_accounts",
               "account_logins","platforms","total_deposit","deposit_count","first_deposit","last_deposit",
               "total_withdraw","withdraw_count","last_withdraw","net_deposit","ib_name","sales_agent"]
        def d(x): return x.strftime("%Y-%m-%d") if x else ""
        with open(OUT,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(hdr)
            for r in rows:
                w.writerow([r.person_key, r.name or "", r.country or "", r.email or "", r.phone or "",
                    r.n_acct, r.n_existing, r.account_logins or "", r.platforms or "",
                    r.tot_dep, r.dep_cnt, d(r.first_dep), d(r.last_dep),
                    r.tot_wd, r.wd_cnt, d(r.last_wd), r.net_dep, r.ib_name or "", r.sales_agent or ""])
        print(f"wrote {len(rows):,} CLIENTS -> {OUT}")
        td=sum(float(r.tot_dep or 0) for r in rows); na=sum(r.n_acct for r in rows)
        print(f"sum deposits ${td:,.0f} across {na:,} accounts")
    finally:
        db.close()


if __name__ == "__main__":
    run()
