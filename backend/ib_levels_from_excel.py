"""
Set each IB's CURRENT level = the LATEST level from the excel promotion/demotion history
(commission_report_result.json level_history, built by promotions_all_years.py).

Desk rule (Jul 9 2026): the excel is authoritative for its era — the profile keeps the latest
promotion/demotion level. RECENCY GUARD: the excel staircase only updates when the IB trades
enough volume, so if an IB's last excel observation is OLD (before 2026), the Plugit profile
export (Jul 2026 pips) is NEWER evidence and their current level is kept.
Idempotent.
"""
import json, sys
import db_config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RECENT = "2026-01"      # staircase must reach this month to override the Plugit level

hist = json.load(open("commission_report_result.json", encoding="utf-8"))["level_history"]
con = db_config.connect(); cur = con.cursor()
cur.execute("SELECT ext_ib_id, id, ib_level, name, is_primary FROM ibs WHERE ext_ib_id IS NOT NULL")
rows = cur.fetchall()

changed, kept_old_evidence, same = 0, 0, 0
for ext, ibid, cur_level, name, is_primary in rows:
    h = hist.get(str(ext))
    if not h:
        continue
    last = h[-1]
    if last["date"] < RECENT:
        kept_old_evidence += 1
        continue                      # excel evidence is stale — Plugit's Jul-2026 level stands
    lv = int(last["level"])
    if lv == (cur_level or 0):
        same += 1
        continue
    cur.execute("UPDATE ibs SET ib_level=%s, last_promotion_level=%s WHERE id=%s", (lv, lv, ibid))
    changed += 1
    if is_primary:
        print(f"  {str(name)[:30]:30} (IB {ext}): level {cur_level} -> {lv}  (excel {last['date']})")
con.commit()
print(f"\nlevels updated: {changed}  |  already matching: {same}  |  kept (excel evidence pre-{RECENT}): {kept_old_evidence}")
con.close()
