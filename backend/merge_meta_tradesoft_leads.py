"""
Merge TradeSoft lead duplicates INTO the matching Meta (facebook/instagram) lead.

We fetch Meta leads directly from the Meta API AND import the old TradeSoft CRM, so the same
Facebook person exists twice: a rich Meta lead (meta_lead_id, form answers, ad/campaign) and a
TradeSoft copy that only uniquely adds customer_no (golden-record ID) + legacy_sales_agent.

Per the desk decision: keep ONE lead per person = the Meta lead (its details), enriched with the
TradeSoft ID + sales agent, then delete the TradeSoft duplicate.

Matching (TradeSoft T -> Meta M):
  - exact email (case-insensitive, both non-empty), OR
  - same phone last-9 digits AND at least one shared name token (guards family-shared phones).

Enrichment onto M (fill-if-missing only, never overwrite Meta data):
  customer_no, legacy_sales_agent, assigned_agent_id, country, city.
Then the matched TradeSoft rows are deleted. (No FKs reference leads; 0 clients point at these.)

Side effect: because the Meta lead now carries the customer_no, phase3's NOT EXISTS guard stops
re-creating the TradeSoft duplicate on the next sync.

Usage:
  python merge_meta_tradesoft_leads.py           # DRY RUN
  python merge_meta_tradesoft_leads.py --apply    # apply
"""
import sys, re
import db_config

APPLY = "--apply" in sys.argv


def phone9(p):
    d = re.sub(r"\D", "", p or "")
    return d[-9:] if len(d) >= 9 else ""


def toks(name):
    return {t for t in re.split(r"\s+", (name or "").lower()) if len(t) >= 3}


def main():
    conn = db_config.connect(); cur = conn.cursor()

    cur.execute("""SELECT id, lower(TRIM(email)), phone, full_name, customer_no,
                          legacy_sales_agent, assigned_agent_id, country, city
                   FROM leads WHERE source IN ('facebook','instagram')""")
    meta = cur.fetchall()
    by_email, by_phone = {}, {}
    meta_row = {}
    for r in meta:
        mid, em, ph, nm = r[0], r[1], r[2], r[3]
        meta_row[mid] = r
        if em:
            by_email.setdefault(em, mid)
        p9 = phone9(ph)
        if p9:
            by_phone.setdefault(p9, []).append((mid, toks(nm)))

    cur.execute("""SELECT id, lower(TRIM(email)), phone, full_name, customer_no,
                          legacy_sales_agent, assigned_agent_id, country, city
                   FROM leads WHERE source='tradesoft'""")
    ts = cur.fetchall()

    enrich = {}          # meta_id -> dict of fill-if-missing values
    to_delete = []       # tradesoft ids
    matched_email = matched_phone = 0

    def want(mid, field, idx, val):
        if not val:
            return
        m = meta_row[mid]
        cur_val = m[idx]
        if cur_val is None or (isinstance(cur_val, str) and cur_val.strip() == ""):
            enrich.setdefault(mid, {}).setdefault(field, val)

    for r in ts:
        tid, em, ph, nm, cno, sa, aa, co, ci = r
        mid = None
        if em and em in by_email:
            mid = by_email[em]; matched_email += 1
        else:
            p9 = phone9(ph)
            if p9 and p9 in by_phone:
                tt = toks(nm)
                for cand_id, cand_toks in by_phone[p9]:
                    if tt & cand_toks:
                        mid = cand_id; matched_phone += 1; break
        if mid is None:
            continue
        # Only the clearly-valuable TradeSoft-unique fields: the golden-record ID + sales agent.
        # Country/city on TradeSoft can be junk (e.g. '919') and Meta already has better values.
        want(mid, "customer_no", 4, cno)
        want(mid, "legacy_sales_agent", 5, sa)
        want(mid, "assigned_agent_id", 6, aa)
        to_delete.append(tid)

    print(f"tradesoft dupes matched by email : {matched_email}")
    print(f"tradesoft dupes matched by phone : {matched_phone}")
    print(f"tradesoft leads to delete        : {len(to_delete)}")
    print(f"meta leads to enrich             : {len(enrich)}")
    ex = list(enrich.items())[:5]
    for mid, vals in ex:
        print(f"  enrich meta #{mid}: {vals}")

    if not APPLY:
        print("\nDRY RUN — no writes. Re-run with --apply.")
        conn.close(); return

    # enrich meta leads (fill-if-missing)
    for mid, vals in enrich.items():
        sets, params = [], {"id": mid}
        for f, v in vals.items():
            sets.append(f"{f}=COALESCE(NULLIF(TRIM({f}::text),''), %({f})s)" if f != "assigned_agent_id"
                        else f"{f}=COALESCE({f}, %({f})s)")
            params[f] = v
        cur.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id=%(id)s", params)

    # delete tradesoft dupes in chunks
    CH = 5000
    for i in range(0, len(to_delete), CH):
        cur.execute("DELETE FROM leads WHERE id = ANY(%s)", (to_delete[i:i+CH],))
    conn.commit()
    print(f"\nAPPLIED. enriched {len(enrich)} meta leads, deleted {len(to_delete)} tradesoft dupes.")
    conn.close()


if __name__ == "__main__":
    main()
