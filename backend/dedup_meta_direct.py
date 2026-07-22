"""Fast dedup: a TradeSoft lead (source 'tradesoft' or 'meta') that duplicates a Meta-DIRECT
lead (facebook/instagram) by EMAIL is a duplicate — we already have it split fb/ig from the
direct fetch. Enrich the fb/ig lead with the dupe's customer_no + sales agent, then delete the
dupe. Email-indexed (ix_leads_lower_email) so it's cheap; safe to run every loop cycle."""
import db_config

conn = db_config.connect(); conn.autocommit = True; cur = conn.cursor()

# 1) enrich the fb/ig lead with the dupe's golden-record id + sales agent (fill-if-missing)
cur.execute("""
  UPDATE leads m SET
    customer_no        = COALESCE(NULLIF(TRIM(m.customer_no),''), t.customer_no),
    legacy_sales_agent = COALESCE(NULLIF(TRIM(m.legacy_sales_agent),''), t.legacy_sales_agent)
  FROM (SELECT DISTINCT ON (lower(TRIM(email))) lower(TRIM(email)) e, customer_no, legacy_sales_agent
        FROM leads WHERE source IN ('meta','tradesoft') AND COALESCE(TRIM(email),'')<>''
        ORDER BY lower(TRIM(email))) t
  WHERE m.source IN ('facebook','instagram') AND lower(TRIM(m.email))=t.e
    AND COALESCE(TRIM(m.customer_no),'')=''
""")
enr = cur.rowcount

# 2) delete the tradesoft/meta duplicate
cur.execute("""
  DELETE FROM leads t WHERE t.source IN ('meta','tradesoft') AND COALESCE(TRIM(t.email),'')<>''
    AND EXISTS (SELECT 1 FROM leads m WHERE m.source IN ('facebook','instagram')
                AND lower(TRIM(m.email))=lower(TRIM(t.email)))
""")
dele = cur.rowcount
if enr or dele:
    print(f"dedup-meta-direct: enriched {enr} fb/ig, deleted {dele} dupes")
conn.close()
