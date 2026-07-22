"""
Execute the remove_from_IB.xlsx removal (desk request, Jul 8 2026).

Anyone in the sheet (matched by EMAIL) is removed from the IB system PERMANENTLY, except:
  - staff (users-table email)          -> keep as IB
  - person group holds balance OR unpaid commission -> keep
Leads / clients records are NOT touched — removal is IB-side only.

Mechanics:
  - person group = all ibs rows sharing ext_ib_id (or the single row when ext is null), so a
    NULL-email MT4 sibling goes too.
  - full row snapshot -> ib_removed_backup (restorable)
  - blacklist -> ib_removed(agent_id) ; build_ibs.INSERT_SQL respects it so periodic rebuilds
    can NEVER re-create them (that is what makes the removal permanent).
  - DELETE FROM ibs.
"""
import openpyxl, sys
import db_config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

wb = openpyxl.load_workbook("C:/Broker-crm/IB setting/remove_from_IB.xlsx", read_only=True, data_only=True)
ws = wb[wb.sheetnames[0]]
emails = set()
for r in ws.iter_rows(min_row=2, values_only=True):
    e = str(r[1] or "").strip().lower()
    if e and "@" in e:
        emails.add(e)
wb.close()

con = db_config.connect(); cur = con.cursor()
cur.execute("SELECT LOWER(TRIM(email)) FROM users WHERE COALESCE(email,'')<>''")
staff = {r[0] for r in cur.fetchall()}

cur.execute("""SELECT id, ext_ib_id, LOWER(TRIM(COALESCE(email,''))), name, agent_id,
                      COALESCE(balance,0), COALESCE(unpaid_commission,0) FROM ibs""")
allrows = cur.fetchall()
groups = {}
for r in allrows:
    key = f"x{r[1]}" if r[1] is not None else f"i{r[0]}"
    groups.setdefault(key, []).append(r)

remove_ids, remove_agents, kept_staff, kept_balance, removed_persons = [], [], 0, 0, 0
for key, rs in groups.items():
    gmails = {r[2] for r in rs if r[2]}
    if not (gmails & emails):
        continue                              # nobody in this group is on the sheet
    if gmails & staff:
        kept_staff += 1; continue             # rule 3: staff stay IBs
    if sum(float(r[5]) for r in rs) > 0 or sum(float(r[6]) for r in rs) > 0.01:
        kept_balance += 1; continue           # rule 4: holds balance / unpaid commission
    removed_persons += 1
    for r in rs:
        remove_ids.append(r[0])
        if r[4] is not None:
            remove_agents.append((r[4], r[1], r[2], r[3]))

print(f"sheet emails: {len(emails):,}  |  keep staff: {kept_staff}  keep balance: {kept_balance}")
print(f"REMOVING {removed_persons} persons -> {len(remove_ids)} ibs rows")

# 1) snapshot for rollback
cur.execute("DROP TABLE IF EXISTS ib_removed_backup")
cur.execute("CREATE TABLE ib_removed_backup AS SELECT NOW() AS removed_at, * FROM ibs WHERE id = ANY(%s)",
            (remove_ids,))
# 2) permanent blacklist honoured by build_ibs
cur.execute("""CREATE TABLE IF NOT EXISTS ib_removed(
    agent_id BIGINT PRIMARY KEY, ext_ib_id BIGINT, email TEXT, name TEXT,
    reason TEXT DEFAULT 'remove_from_IB.xlsx (Jul 2026)', removed_at TIMESTAMPTZ DEFAULT NOW())""")
from psycopg2.extras import execute_values
execute_values(cur, """INSERT INTO ib_removed (agent_id, ext_ib_id, email, name) VALUES %s
                       ON CONFLICT (agent_id) DO NOTHING""", remove_agents)
# 3) detach / clean dependents (FKs). Client & lead RECORDS stay untouched — only their
#    ib_id link is cleared ("removal is IB-side only"). IB-side detail rows are deleted.
cur.execute("UPDATE clients SET ib_id = NULL WHERE ib_id = ANY(%s)", (remove_ids,))
print(f"clients ib-link cleared: {cur.rowcount}")
cur.execute("UPDATE leads SET ib_id = NULL WHERE ib_id = ANY(%s)", (remove_ids,))
print(f"leads ib-link cleared: {cur.rowcount}")
cur.execute("UPDATE ibs SET parent_ib_id = NULL WHERE parent_ib_id = ANY(%s)", (remove_ids,))
print(f"sub-IB parent pointers cleared: {cur.rowcount}")
for tbl in ("ib_commissions", "ib_challenge_progress", "ib_referral_clicks"):
    cur.execute(f"DELETE FROM {tbl} WHERE ib_id = ANY(%s)", (remove_ids,))
    print(f"{tbl} rows deleted: {cur.rowcount}")

# 4) delete from the IB system
cur.execute("DELETE FROM ibs WHERE id = ANY(%s)", (remove_ids,))
print(f"deleted ibs rows: {cur.rowcount}  |  blacklisted agents: {len(remove_agents)}")
con.commit()

cur.execute("SELECT COUNT(*) FROM ibs"); print("ibs rows remaining:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM ib_removed_backup"); print("backup rows:", cur.fetchone()[0])
con.close()
