"""
An IB person has TWO ibs records sharing ext_ib_id: an MT5 one (group IB\\IB-N, agent 335*)
that carries the COMMISSION, and an MT4 one (group TNFX-IB-N, agent 2100*) that the payoff
import happened to attach the PAYOFF to. That splits Commission and Payoff across two rows so
Net (= comm - payoff) looks wrong on each.

Fix: per ext_ib_id, move the WHOLE group's payoff onto the PRIMARY record (the one holding the
commission -> the MT5/IB record), zero the others. Sum of total_payoff is preserved, so KPI and
the $2.44M total are unchanged. Idempotent.
"""
import psycopg2
import db_config
con = db_config.connect(); cur = con.cursor()

# groups of ib records sharing an ext_ib_id that have any payoff
cur.execute("""
    SELECT ext_ib_id,
           SUM(COALESCE(total_payoff,0)) AS tot_payoff,
           ARRAY_AGG(id ORDER BY
               COALESCE(total_commission,0) DESC,          -- record with commission wins
               (CASE WHEN starts_with(COALESCE(group_name,''),'IB') THEN 0 ELSE 1 END),  -- else prefer MT5
               id) AS ids
    FROM ibs
    WHERE ext_ib_id IS NOT NULL
    GROUP BY ext_ib_id
    HAVING SUM(COALESCE(total_payoff,0)) > 0
""")
groups = cur.fetchall()
moved = 0; primaries = 0
for ext, tot, ids in groups:
    primary = ids[0]
    primaries += 1
    # zero everyone in the group, then set the whole payoff on the primary
    cur.execute("UPDATE ibs SET total_payoff = 0 WHERE ext_ib_id = %s", (ext,))
    cur.execute("UPDATE ibs SET total_payoff = %s WHERE id = %s", (float(tot), primary))
    if len(ids) > 1:
        moved += 1
    # keep ib_operations pointing at the primary too, so the profile Payouts tab shows them
    cur.execute("UPDATE ib_operations SET ib_id = %s WHERE ext_ib_id = %s", (primary, ext))
con.commit()

cur.execute("SELECT COUNT(*) FILTER (WHERE total_payoff>0), ROUND(SUM(total_payoff)::numeric,0) FROM ibs")
n, total = cur.fetchone()
print(f"consolidated {primaries} IB persons ({moved} were split across MT4+MT5 records)")
print(f"IBs with payoff now: {n}   total payoff: ${total:,.0f}  (should stay $2,445,082)")
# sanity: any remaining record with commission>0 AND a sibling holding payoff?
cur.execute("""
    SELECT COUNT(*) FROM (
      SELECT ext_ib_id FROM ibs WHERE ext_ib_id IS NOT NULL
      GROUP BY ext_ib_id
      HAVING SUM(CASE WHEN total_commission>0 AND COALESCE(total_payoff,0)=0 THEN 1 ELSE 0 END) > 0
         AND SUM(CASE WHEN COALESCE(total_payoff,0)>0 AND COALESCE(total_commission,0)=0 THEN 1 ELSE 0 END) > 0
    ) q
""")
print("still-split groups (comm on one, payoff on another):", cur.fetchone()[0])
con.close()
