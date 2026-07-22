"""
Reflect the REAL acquisition channel onto clients (and leads) from every signal we have.

Most clients sit on a generic source ('tradesoft' / 'none' / NULL) so filtering the Clients list
by facebook/google/etc. shows almost nothing. This derives the channel with a priority and fills
the generic ones (never overwrites an already-specific channel, except MQL5 which is authoritative
via the IB link).

Priority (highest first):
  1. MQL5      — client.agent is one of the country MQL5 IBs (Iraq-MQL5, Syria-MQL5, ...): leads/
                 clients that came from mql5.com via our per-country IB referral links. AUTHORITATIVE.
  2. Meta      — the person has a matched facebook/instagram lead (by customer_no) -> that exact channel.
  3. TradeSoft numeric source -> 95/97 = facebook, 102/93 = google.
  4. sales_agent / Webinar -> lead_source text.

GENERIC (fill-only) = source IS NULL OR source IN ('', 'none', 'tradesoft').

Usage:  python reclassify_sources.py            # DRY RUN
        python reclassify_sources.py --apply
"""
import sys
import db_config

APPLY = "--apply" in sys.argv
GEN = "(c.source IS NULL OR c.source IN ('','none','tradesoft'))"
GENL = "(l.source IS NULL OR l.source IN ('','none','tradesoft'))"


def main():
    conn = db_config.connect(); cur = conn.cursor()
    cur.execute("SELECT DISTINCT login FROM clients WHERE name ILIKE '%MQL5%'")
    mql5 = [r[0] for r in cur.fetchall()]
    print(f"MQL5 IB logins: {len(mql5)}")

    steps = []  # (label, sql, params)

    # ---- CLIENTS ----
    # 1. MQL5 by IB link (authoritative — overwrite any non-MQL5 source). The referring IB is
    #    stored as TEXT in customers.ib (e.g. 'Iraq-MQL5'); clients.agent only covers a fraction.
    steps.append(("clients MQL5", """
        UPDATE clients c SET source='MQL5'
        FROM customers cu WHERE cu.customer_no=c.customer_no AND cu.ib ILIKE '%%MQL5%%'
          AND COALESCE(c.source,'') <> 'MQL5'""", {}))

    # 2a. matched Meta lead by customer_no -> exact channel (facebook wins ties)
    steps.append(("clients Meta-matched (customer_no)", f"""
        UPDATE clients c SET source = ml.src
        FROM (SELECT customer_no, MIN(source) src FROM leads
              WHERE source IN ('facebook','instagram') AND customer_no IS NOT NULL
              GROUP BY customer_no) ml
        WHERE ml.customer_no = c.customer_no AND {GEN}""", {}))
    # 2b. converted Meta lead by matched_login/converted_login -> the client it became. Catches
    #     Meta leads that registered directly (no TradeSoft dupe, so no shared customer_no).
    steps.append(("clients Meta-matched (matched_login)", f"""
        UPDATE clients c SET source = ml.src
        FROM (SELECT c2.customer_no, MIN(m.source) src
              FROM leads m JOIN clients c2 ON c2.login = COALESCE(NULLIF(m.matched_login,0), m.converted_login)
              WHERE m.source IN ('facebook','instagram') AND c2.customer_no IS NOT NULL
              GROUP BY c2.customer_no) ml
        WHERE c.customer_no = ml.customer_no AND {GEN}""", {}))

    # 3. TradeSoft numeric source: 95/97 = Meta ads (3-yr history, platform unknown -> 'meta';
    #    the precise facebook/instagram from the Meta direct-fetch above already won). 102/93 google.
    steps.append(("clients Meta (TradeSoft 95/97)", f"""
        UPDATE clients c SET source='meta'
        FROM customers cu JOIN tradesoft_old.fx_leads_view v ON v.user_id::text=cu.legacy_user_id
        WHERE c.customer_no=cu.customer_no AND TRIM(v.source) IN ('95','97') AND {GEN}""", {}))
    steps.append(("clients TradeSoft google", f"""
        UPDATE clients c SET source='google'
        FROM customers cu JOIN tradesoft_old.fx_leads_view v ON v.user_id::text=cu.legacy_user_id
        WHERE c.customer_no=cu.customer_no AND TRIM(v.source) IN ('102','93') AND {GEN}""", {}))

    # 4. sales_agent / webinar text
    steps.append(("clients sales_agent", f"""
        UPDATE clients c SET source='sales_agent'
        FROM customers cu JOIN tradesoft_old.fx_leads_view v ON v.user_id::text=cu.legacy_user_id
        WHERE c.customer_no=cu.customer_no AND TRIM(v.lead_source)='sales_agent' AND {GEN}""", {}))
    steps.append(("clients webinar", f"""
        UPDATE clients c SET source='webinar'
        FROM customers cu JOIN tradesoft_old.fx_leads_view v ON v.user_id::text=cu.legacy_user_id
        WHERE c.customer_no=cu.customer_no AND TRIM(v.lead_source)='Webinar' AND {GEN}""", {}))

    # ---- LEADS ----
    # MQL5 leads (referred by a country MQL5 IB — customers.ib text)
    steps.append(("leads MQL5", """
        UPDATE leads l SET source='MQL5'
        FROM customers cu WHERE cu.customer_no=l.customer_no AND cu.ib ILIKE '%%MQL5%%'
          AND COALESCE(l.source,'') <> 'MQL5'""", {}))
    # Meta (TradeSoft 95/97) leads — the 3-year Meta history the direct fetch doesn't cover
    steps.append(("leads Meta (TradeSoft 95/97)", f"""
        UPDATE leads l SET source='meta'
        FROM customers cu JOIN tradesoft_old.fx_leads_view v ON v.user_id::text=cu.legacy_user_id
        WHERE l.customer_no=cu.customer_no AND TRIM(v.source) IN ('95','97') AND {GENL}""", {}))
    # sales_agent leads
    steps.append(("leads sales_agent", f"""
        UPDATE leads l SET source='sales_agent'
        FROM customers cu JOIN tradesoft_old.fx_leads_view v ON v.user_id::text=cu.legacy_user_id
        WHERE l.customer_no=cu.customer_no AND TRIM(v.lead_source)='sales_agent' AND {GENL}""", {}))

    for label, sql, params in steps:
        if APPLY:
            cur.execute(sql, params); print(f"  {label}: {cur.rowcount}")
        else:
            # count-only: wrap as SELECT count(*) by turning UPDATE into its WHERE — simplest is EXPLAIN-free dry
            print(f"  {label}: (dry — will run on --apply)")

    if APPLY:
        conn.commit()
        cur.execute("SELECT source, count(*) FROM clients WHERE source IN ('MQL5','facebook','instagram','google','sales_agent','webinar') GROUP BY 1 ORDER BY 2 DESC")
        print("clients by channel now:", cur.fetchall())
        cur.execute("SELECT source, count(*) FROM leads WHERE source IN ('MQL5','sales_agent') GROUP BY 1 ORDER BY 2 DESC")
        print("leads MQL5/sales_agent now:", cur.fetchall())
    else:
        print("\nDRY RUN — re-run with --apply.")
    conn.close()


if __name__ == "__main__":
    main()
