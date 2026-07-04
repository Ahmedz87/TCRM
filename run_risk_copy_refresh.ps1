# Keep the RISK + COPY datasets LIVE (both were manual one-off rebuilds: abuse froze Jun 22,
# copy provider stats froze Jun 19).
#   - run_abuse.py   -> abuse_cases / abuse_account_flags (withdrawal HOLD flags, client + IB risk chips)
#   - copy_enrich.py -> copy_providers stats (leaderboard activity / earnings / integrity)
# DB-only (no MT bridge / interactive session). ~4 min/run. Scheduled every 6h.
# ErrorActionPreference=Continue so a failure in one engine still lets the other run.
$ErrorActionPreference = "Continue"
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$log = "C:\broker-crm\backend\risk_copy_refresh.log"
$env:PYTHONIOENCODING = "utf-8"
Set-Location C:\broker-crm\backend
"$(Get-Date -Format s)  === abuse start ===" | Add-Content $log
& $py C:\broker-crm\backend\run_abuse.py *>> $log
"$(Get-Date -Format s)  === abuse exit=$LASTEXITCODE ; copy_enrich start ===" | Add-Content $log
& $py C:\broker-crm\backend\copy_enrich.py *>> $log
"$(Get-Date -Format s)  === copy_enrich exit=$LASTEXITCODE ; done ===" | Add-Content $log
