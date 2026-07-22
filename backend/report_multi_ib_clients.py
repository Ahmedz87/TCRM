"""
REPORT: clients (persons) whose ACTIVE trading accounts sit under DIFFERENT IBs.

Rules (per desk request, Jul 2026):
  - ACTIVE accounts only: clients rows with is_archived=FALSE AND user_archived=FALSE.
  - Person identity = phone (accounts sharing a phone are one client; blank/0 phones can't be
    grouped so they are excluded).
  - IB identity = the PERSON IB (ext_ib_id groups the IB's MT4+MT5 agent accounts — an account
    under Marwan's MT4 agent and another under his MT5 agent is the SAME IB, not two).
  - An account's own IB row (login = agent) is excluded.
  - 'First IB' = the IB of the person's earliest-opened account (clients.reg_date, fallback created_at).

Output: 'C:/Broker-crm/IB setting/Clients under multiple IBs.xlsx'
  Sheet 'Summary'  — one row per client: accounts, IBs, first IB + date, later IBs.
  Sheet 'Accounts' — one row per account: client, phone, login, platform, opened, IB, first-IB flag.
"""
import sys
import db_config
import openpyxl
from openpyxl.styles import Font, PatternFill
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = "C:/Broker-crm/IB setting/Clients under multiple IBs.xlsx"

con = db_config.connect(); cur = con.cursor()
cur.execute("""
    SELECT c.phone, c.name, c.login, COALESCE(c.platform,'MT5') AS platform,
           -- REAL account-open date chain: clients.reg_date -> bridge MT registration
           -- (trading_accounts.reg_date) -> TradeSoft account creation (fx_accounts_view).
           -- NO clients.created_at fallback — that's just the Jun-15 CRM import date and
           -- would falsify 'first IB'. Unknown stays blank and never claims 'first'.
           COALESCE(NULLIF(c.reg_date,''), NULLIF(ta.reg_date::text,''), NULLIF(left(av.created_at,10),''), '') AS opened,
           COALESCE(i.ext_ib_id::text, 'ib'||i.id) AS ib_key,
           COALESCE(i.ext_ib_id::text, '')         AS ib_ext,
           i.name AS ib_name
    FROM clients c
    JOIN ibs i ON i.agent_id = c.agent
    LEFT JOIN trading_accounts ta ON ta.login = c.login
    LEFT JOIN (SELECT DISTINCT ON (account_number) account_number, created_at
               FROM tradesoft_old.fx_accounts_view ORDER BY account_number, created_at) av
           ON av.account_number = c.login::text
    WHERE COALESCE(c.is_archived, FALSE) = FALSE
      AND COALESCE(c.user_archived, FALSE) = FALSE
      AND COALESCE(c.phone,'') NOT IN ('', '0')
      AND c.login <> c.agent
""")
rows = cur.fetchall()
print(f"active IB-linked accounts with a phone: {len(rows):,}")

# group by person (phone); keep persons with >1 distinct IB
persons = defaultdict(list)
for ph, nm, login, plat, opened, ibk, ibext, ibname in rows:
    persons[ph].append((opened or "", login, plat, nm, ibk, ibext, ibname))
# sort each person's accounts by date; UNKNOWN dates sort LAST so they never claim 'first IB'
multi = {ph: sorted(a, key=lambda x: (x[0] or "9999-12-31", x[1]))
         for ph, a in persons.items() if len({x[4] for x in a}) > 1}
print(f"clients with active accounts under >1 IB: {len(multi):,} "
      f"({sum(len(a) for a in multi.values()):,} accounts)")

wb = openpyxl.Workbook()
bold = Font(bold=True); first_fill = PatternFill("solid", fgColor="D9F2E5")

# ---- Summary sheet: one row per client -----------------------------------
ws = wb.active; ws.title = "Summary"
ws.append(["Client", "Phone", "Accounts", "IBs", "First account date", "First IB", "First IB ID",
           "Later IBs (in date order)"])
for c in ws[1]: c.font = bold
for ph, accts in sorted(multi.items(), key=lambda kv: kv[1][0][3] or ""):
    first = accts[0]
    seen, later = {first[4]}, []
    for a in accts[1:]:
        if a[4] not in seen:
            seen.add(a[4]); later.append(f"{a[6]} ({a[0] or 'no date'})")
    ws.append([first[3], ph, len(accts), len(seen), first[0], first[6], first[5], " → ".join(later)])
ws.freeze_panes = "A2"
for col, w in zip("ABCDEFGH", (28, 16, 9, 6, 14, 28, 11, 60)):
    ws.column_dimensions[col].width = w

# ---- Accounts sheet: one row per account ---------------------------------
wa = wb.create_sheet("Accounts")
wa.append(["Client", "Phone", "Login", "Platform", "Account opened", "IB", "IB ID", "First IB?"])
for c in wa[1]: c.font = bold
r = 2
for ph, accts in sorted(multi.items(), key=lambda kv: kv[1][0][3] or ""):
    first_ib = accts[0][4]
    for opened, login, plat, nm, ibk, ibext, ibname in accts:
        wa.append([nm, ph, login, plat, opened, ibname, ibext, "FIRST IB" if ibk == first_ib else ""])
        if ibk == first_ib:
            for cell in wa[r]: cell.fill = first_fill
        r += 1
wa.freeze_panes = "A2"
for col, w in zip("ABCDEFGH", (28, 16, 12, 9, 14, 28, 11, 10)):
    wa.column_dimensions[col].width = w

wb.save(OUT)
print(f"saved: {OUT}")

# console preview
print("\nsample (first 8 clients):")
for ph, accts in list(sorted(multi.items(), key=lambda kv: kv[1][0][3] or ""))[:8]:
    print(f"  {accts[0][3]}  ({ph})  {len(accts)} accounts / {len({x[4] for x in accts})} IBs")
    for opened, login, plat, nm, ibk, ibext, ibname in accts:
        print(f"     {opened or '—':10}  #{login} {plat:4}  -> {ibname} ({ibext})")
con.close()
