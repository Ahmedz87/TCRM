"""Tier the imported method-0 TradeSoft deposits by evidence of being real client money."""
import db_config

B = "t.method='TradeSoft' AND t.notes='TradeSoft import (no gateway recorded)' AND t.tx_type IN ('deposit','deposit_dup','deposit_unverified')"
CORR = ("EXISTS (SELECT 1 FROM transactions g WHERE g.login=t.login AND g.tx_type IN ('deposit','deposit_dup') "
        "AND g.method NOT IN ('TradeSoft','0') AND g.deal_id<>t.deal_id)")
T1 = f"((t.amount<=1000 AND mod(t.amount::numeric,1000)<>0) OR {CORR})"

conn = db_config.connect(); cur = conn.cursor()
cur.execute(f"""SELECT
  count(*) FILTER (WHERE {T1}), COALESCE(sum(t.amount) FILTER (WHERE {T1}),0),
  count(*) FILTER (WHERE NOT {T1} AND t.amount<=5000),
  COALESCE(sum(t.amount) FILTER (WHERE NOT {T1} AND t.amount<=5000),0),
  count(*) FILTER (WHERE NOT {T1} AND t.amount>5000),
  COALESCE(sum(t.amount) FILTER (WHERE NOT {T1} AND t.amount>5000),0)
  FROM transactions t WHERE {B}""")
r = cur.fetchone()
print(f"T1 likely-real (<=1k non-round OR gateway-corroborated): {r[0]:,}  ${r[1]:,.0f}")
print(f"T2 uncertain  (rest <=5k):                               {r[2]:,}  ${r[3]:,.0f}")
print(f"T3 likely-credit (rest >5k):                             {r[4]:,}  ${r[5]:,.0f}")
conn.close()
