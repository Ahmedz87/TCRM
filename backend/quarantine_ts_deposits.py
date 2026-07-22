"""Quarantine the UNCERTAIN portion of the method-0 TradeSoft deposit import.
Keep T1 (likely real: <=1k non-round OR gateway-corroborated) as 'deposit'.
Flip T2/T3 to 'deposit_unverified' (excluded from deposit KPIs/lists; instantly reversible).
Also flag +-3day MT duplicates among the kept rows, then recompute affected totals."""
import db_config

B = "t.method='TradeSoft' AND t.notes='TradeSoft import (no gateway recorded)'"
CORR = ("EXISTS (SELECT 1 FROM transactions g WHERE g.login=t.login AND g.tx_type IN ('deposit','deposit_dup') "
        "AND g.method NOT IN ('TradeSoft','0') AND g.deal_id<>t.deal_id)")
T1 = f"((t.amount<=1000 AND mod(t.amount::numeric,1000)<>0) OR {CORR})"

conn = db_config.connect(); cur = conn.cursor()

# 1) quarantine T2+T3
cur.execute(f"""UPDATE transactions t SET tx_type='deposit_unverified'
  WHERE {B} AND t.tx_type IN ('deposit','deposit_dup') AND NOT {T1}""")
print(f"quarantined (deposit_unverified): {cur.rowcount}")
conn.commit()

# 2) +-3day MT dedup on kept rows (same-day dedup already ran; widen window)
cur.execute(f"""UPDATE transactions t SET tx_type='deposit_dup'
  WHERE {B} AND t.tx_type='deposit'
    AND EXISTS (SELECT 1 FROM transactions m WHERE m.deal_id<8000000000 AND m.tx_type IN ('deposit','deposit_dup')
       AND m.login=t.login AND round(m.amount::numeric,2)=round(t.amount::numeric,2)
       AND abs(left(m.tx_date,10)::date - left(t.tx_date,10)::date) <= 3)""")
print(f"+-3day MT dupes flagged: {cur.rowcount}")
conn.commit()

# 3) recompute totals for every login this import touched
cur.execute(f"SELECT array_agg(DISTINCT t.login) FROM transactions t WHERE {B}")
affected = list(cur.fetchone()[0] or [])
print(f"recomputing totals for {len(affected)} logins")
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
        total_withdrawals=ROUND(COALESCE(ct.wd,0)::numeric,2)
      FROM ct WHERE ct.customer_no=cu.customer_no""", (lg,))
    conn.commit()

# 4) list aggregates rebuild
cur.execute("UPDATE client_tx_agg_meta SET refreshed_at = NOW() - interval '10 years' WHERE id=1")
conn.commit()
print("done; client_tx_agg marked stale")

# summary
cur.execute(f"""SELECT t.tx_type, count(*), round(sum(t.amount)::numeric) FROM transactions t
  WHERE {B} GROUP BY 1 ORDER BY 2 DESC""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,} rows  ${r[2]:,.0f}")
conn.close()
