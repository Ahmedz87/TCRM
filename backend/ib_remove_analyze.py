"""Analyze remove_from_IB.xlsx: which current IBs match by email, and classify:
   KEEP (staff) / KEEP (has balance / unpaid commission) / REMOVE. Read-only."""
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
print(f"distinct emails in sheet: {len(emails):,}")

con = db_config.connect(); cur = con.cursor()
# staff list = users table (the staff accounts previously imported)
cur.execute("SELECT LOWER(TRIM(email)) FROM users WHERE COALESCE(email,'')<>''")
staff = {r[0] for r in cur.fetchall()}

# current IBs matching the sheet by email (person = ext_ib_id group; include siblings)
cur.execute("""
    SELECT i.id, i.ext_ib_id, LOWER(TRIM(i.email)) AS email, i.name, i.agent_id,
           COALESCE(i.balance,0), COALESCE(i.unpaid_commission,0), COALESCE(i.total_commission,0),
           COALESCE(i.total_payoff,0), i.is_primary, i.total_clients
    FROM ibs i WHERE COALESCE(i.email,'') <> ''
""")
rows = cur.fetchall()
by_email = {}
for r in rows:
    by_email.setdefault(r[2], []).append(r)

matched = {e: rs for e, rs in by_email.items() if e in emails}
print(f"IB emails matched in current IB system: {len(matched):,} "
      f"({sum(len(v) for v in matched.values()):,} ibs rows)")

keep_staff, keep_balance, remove = [], [], []
for e, rs in sorted(matched.items()):
    tot_bal = sum(float(r[5]) for r in rs)
    tot_unpaid = sum(float(r[6]) for r in rs)
    if e in staff:
        keep_staff.append((e, rs, tot_bal, tot_unpaid))
    elif tot_bal > 0 or tot_unpaid > 0.01:
        keep_balance.append((e, rs, tot_bal, tot_unpaid))
    else:
        remove.append((e, rs, tot_bal, tot_unpaid))

print(f"\nKEEP — staff:          {len(keep_staff):3} persons")
for e, rs, b, u in keep_staff[:15]:
    print(f"    {e:40} {rs[0][3]}")
print(f"KEEP — balance/unpaid: {len(keep_balance):3} persons")
for e, rs, b, u in sorted(keep_balance, key=lambda x: -(x[2]+x[3]))[:15]:
    print(f"    {e:40} {str(rs[0][3])[:24]:24} bal=${b:,.0f} unpaid=${u:,.2f}")
print(f"REMOVE:                {len(remove):3} persons "
      f"({sum(len(rs) for _, rs, _, _ in remove)} ibs rows, "
      f"{sum(r[10] or 0 for _, rs, _, _ in remove for r in rs):,} linked clients)")
for e, rs, b, u in remove[:20]:
    print(f"    {e:40} {str(rs[0][3])[:26]:26} clients={sum(r[10] or 0 for r in rs)} comm=${sum(float(r[7]) for r in rs):,.0f} payoff=${sum(float(r[8]) for r in rs):,.0f}")
con.close()
