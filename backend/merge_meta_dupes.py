"""One-off: merge 'meta' (TradeSoft) leads that duplicate a facebook/instagram (Meta-direct) lead.
Keep the fb/ig lead (precise channel), enrich it with the meta dupe's customer_no + sales agent,
delete the meta dupe. Match by email, or phone last-9."""
import db_config

conn = db_config.connect(); cur = conn.cursor()
cur.execute("""
  SELECT t.id t_id, t.customer_no t_cust, t.legacy_sales_agent t_agent, m.id m_id
  FROM leads t
  JOIN leads m ON m.source IN ('facebook','instagram') AND m.id<>t.id AND (
      (COALESCE(TRIM(t.email),'')<>'' AND lower(TRIM(m.email))=lower(TRIM(t.email)))
      OR (length(regexp_replace(COALESCE(t.phone,''),'\\D','','g'))>=9
          AND right(regexp_replace(COALESCE(m.phone,''),'\\D','','g'),9)
              =right(regexp_replace(t.phone,'\\D','','g'),9)))
  WHERE t.source='meta'
""")
seen = {}
for t_id, t_cust, t_agent, m_id in cur.fetchall():
    if t_id not in seen:
        seen[t_id] = (t_cust, t_agent, m_id)

enrich = deleted = 0
for t_id, (t_cust, t_agent, m_id) in seen.items():
    cur.execute("""UPDATE leads SET customer_no=COALESCE(NULLIF(TRIM(customer_no),''),%s),
                     legacy_sales_agent=COALESCE(NULLIF(TRIM(legacy_sales_agent),''),%s) WHERE id=%s""",
                (t_cust, t_agent, m_id))
    enrich += cur.rowcount
    cur.execute("DELETE FROM leads WHERE id=%s", (t_id,))
    deleted += cur.rowcount
conn.commit()
print(f"meta dupes merged into fb/ig: enriched={enrich} deleted={deleted}")
cur.execute("SELECT count(*) FROM leads WHERE source='meta'")
print("meta leads now:", cur.fetchone()[0])
conn.close()
