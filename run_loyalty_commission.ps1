# Periodic refresh so Loyalty + Sales-commission inputs (ib_commissions) stay LIVE.
# Both used to be manual one-off rebuilds (froze at Jun 16/17). DB-only — no MT bridge needed,
# so this runs fine as SYSTEM. ~75s per run, atomic (no empty-data window). Scheduled every 3h.
$ErrorActionPreference = "Continue"
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$job = "C:\broker-crm\backend\refresh_loyalty_commission.py"
$log = "C:\broker-crm\backend\loyalty_commission_refresh.log"
$env:PYTHONIOENCODING = "utf-8"
Set-Location C:\broker-crm\backend
"$(Get-Date -Format s)  === scheduled refresh start ===" | Add-Content $log
& $py $job *>> $log
"$(Get-Date -Format s)  === scheduled refresh exit=$LASTEXITCODE ===" | Add-Content $log
