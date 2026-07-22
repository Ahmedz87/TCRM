"""Align customers.kind with TradeSoft's own client/lead classification (source of truth).
- kind='client'  <=> present in fx_clients_view (not deleted)  [live-only customers stay client]
- demotes the dep>0 auto-promotions that made the CRM show ~29.5k vs TradeSoft's ~26.3k.
Batched + retried so it coexists with the bridge/enrich loops."""
import time
import db_config

conn = db_config.connect(); cur = conn.cursor()

def batched(select_sql, update_sql, label):
    cur.execute(select_sql)
    ids = [r[0] for r in cur.fetchall()]
    done = 0
    for i in range(0, len(ids), 2000):
        b = ids[i:i+2000]
        for att in range(6):
            try:
                cur.execute("SET lock_timeout='10s'")
                cur.execute(update_sql, (b,))
                done += cur.rowcount
                conn.commit(); break
            except Exception:
                conn.rollback()
                if att == 5: raise
                time.sleep(2*(att+1))
    print(f"{label}: {done}", flush=True)

batched(
    """SELECT cu.customer_no FROM customers cu
       WHERE cu.kind='client' AND COALESCE(cu.source,'')<>'live'
         AND cu.legacy_user_id IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM tradesoft_old.fx_clients_view v
                         WHERE v.user_id=cu.legacy_user_id AND v.deleted_at IS NULL)""",
    "UPDATE customers SET kind='lead' WHERE customer_no = ANY(%s)",
    "demoted to lead (TradeSoft says lead)")

batched(
    """SELECT cu.customer_no FROM customers cu
       WHERE cu.kind='lead'
         AND EXISTS (SELECT 1 FROM tradesoft_old.fx_clients_view v
                     WHERE v.user_id=cu.legacy_user_id AND v.deleted_at IS NULL)""",
    "UPDATE customers SET kind='client' WHERE customer_no = ANY(%s)",
    "promoted to client (TradeSoft says client)")

cur.execute("SELECT count(*) FROM customers WHERE kind='client'")
print("kind=client now:", cur.fetchone()[0], flush=True)
cur.execute("""SELECT count(DISTINCT cu.customer_no)
  FROM customers cu LEFT JOIN clients c ON c.customer_no=cu.customer_no
  WHERE cu.kind='client' AND COALESCE(c.user_archived,FALSE)=FALSE
    AND (c.login IS NULL OR c.group_name IS NULL
         OR (c.group_name NOT ILIKE '%%retail%%' AND c.group_name NOT ILIKE '%%demo%%'))""")
print("CLIENTS LIST total now:", cur.fetchone()[0], flush=True)
conn.close()
