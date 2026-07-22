# run_new_ib_backfill.ps1 — daily: add NEW IBs the base build_ibs misses.
# Runs backfill_new_ibs.py --commit, which inserts any account whose OWN MT group is an IB
# group (MT5 IB\IB-*, MT4 TNFX-IB-*) registered after the cutoff and not already in `ibs`,
# setting the real ib_creation_date ("IB since") + linking the sales agent. Idempotent
# (ON CONFLICT DO NOTHING), DB-only (no MT bridge / interactive session), so it runs fine
# under SYSTEM. Registered as the daily Task Scheduler job BrokerCRM-IBBackfill.
$ErrorActionPreference = "Continue"
$be  = "C:\broker-crm\backend"
$py  = "$be\venv\Scripts\python.exe"
$log = "$be\logs\new_ib_backfill.log"
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
Set-Location $be
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  === new-IB backfill start ===" | Add-Content $log
& $py "$be\backfill_new_ibs.py" --cutoff 2026-06-15 --commit *>> $log
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  === new-IB backfill exit=$LASTEXITCODE ===" | Add-Content $log
