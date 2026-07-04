# Weekly MT4/MT5 account-archival — runs archive_accounts.py --commit every Sunday.
# Safe: the job ABORTS itself if the MT sync looks unhealthy (<8000 accounts seen in 24h),
# so a down bridge / logged-out weekend never mass-archives. Logs to logs\archive_weekly.log.
Set-Location C:\broker-crm\backend
$env:PYTHONUTF8 = "1"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"==== archive run $ts ====" | Out-File -FilePath C:\broker-crm\backend\logs\archive_weekly.log -Append -Encoding utf8
& C:\broker-crm\backend\venv\Scripts\python.exe archive_accounts.py --commit *>> C:\broker-crm\backend\logs\archive_weekly.log
