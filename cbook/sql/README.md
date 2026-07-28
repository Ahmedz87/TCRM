# cbook SQL — how to run (read-only)

All SQL here is **read-only analysis**. Nothing writes to client data, accounts, or
transactions. The only DDL is one **additive, reversible VIEW** (`cbook_cash_movements`)
over the existing `deals` table.

## One-time setup (on the CRM server / DB box)

```powershell
# PG client on PATH (per CLAUDE.md)
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"
# creds: use backend/db_config.py values; ALWAYS the remote box 199.247.6.189, not localhost
psql "host=199.247.6.189 port=5432 dbname=broker_crm user=postgres" -f cbook/sql/views/01_cbook_cash_movements.sql
```

> psql v16 can query the v18 server for plain SELECT/CREATE VIEW (only dump/restore needs v18 tools).
> To remove: `DROP VIEW cbook_cash_movements;` — it holds no data.

## Run the §5 reconstruction (Table 1)

```powershell
psql "host=199.247.6.189 port=5432 dbname=broker_crm user=postgres" \
  -f cbook/sql/reports/s05_account_reconstruction.sql
```

Output = one row per account: opening/closing balance, net deposits, net withdrawals,
internal transfers, bonuses/credits, realized gross/net P&L, and **`balance_break`**
(reconstructed − MT-reported). Rows are sorted **largest break first** so you audit the
biggest discrepancies before trusting the numbers.

## Or from Python (also read-only)

```python
from cbook.lib.db import fetch_sql_file
rows = fetch_sql_file("cbook/sql/reports/s05_account_reconstruction.sql")
breaks = [r for r in rows if abs(r["balance_break"] or 0) > 0.01]
print(f"{len(rows)} accounts, {len(breaks)} with reconciliation breaks")
```

`cbook.lib.db` forces every query `READ ONLY` and refuses anything that isn't a single
SELECT/WITH — it structurally cannot write.

## Validate the calculation logic (no DB needed)

```bash
python3 cbook/tests/test_reconstruction.py   # 10/10 §31 scenarios
```
