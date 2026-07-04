# Broker CRM MT bridges — bridge.py (MT5) + mt4_loop.py (MT4). These load the native
# MT manager DLL, which ONLY works in an interactive desktop session (it fails under
# SYSTEM/session-0). So this runs at LOGON (Task: BrokerCRM-Bridges).
$ErrorActionPreference = 'SilentlyContinue'
$log = "C:\broker-crm\startup.log"
function Log($m){ "$(Get-Date -Format s)  [bridges] $m" | Out-File -Append -Encoding utf8 $log }

Log "=== start_bridges invoked ==="
# Four MT connections per platform, each on its own manager login so nothing blocks:
#   MT5: bridge.py = A/1025 (live sync) + mt5_deal_worker.py = B/1026 (deals)
#   MT4: mt4_loop.py = A/1025 (accounts) + mt4_journal_worker.py = B/1026 (journal)
# Stop ALL of them first (avoid duplicate connections on restart).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'bridge\.py|mt4_loop|fetch_mt4|mt5_deal_worker|mt4_journal_worker' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3

$py = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be = "C:\broker-crm\backend"
$logs = "C:\broker-crm\backend\logs"
# MT5: A live-sync bridge, then B deal worker
Start-Process -FilePath $py -ArgumentList "bridge.py" -WorkingDirectory $be -WindowStyle Minimized
Start-Sleep -Seconds 2
Start-Process -FilePath $py -ArgumentList "mt5_deal_worker.py" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$logs\mt5_deal_worker.log" -RedirectStandardError "$logs\mt5_deal_worker.err"
# MT4: A accounts loop, then B journal worker
Start-Process -FilePath $py -ArgumentList "mt4_loop.py" -WorkingDirectory $be -WindowStyle Minimized
Start-Sleep -Seconds 2
Start-Process -FilePath $py -ArgumentList "mt4_journal_worker.py" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$logs\mt4_journal_worker.log" -RedirectStandardError "$logs\mt4_journal_worker.err"
Log "started: bridge.py(MT5-A) mt5_deal_worker(MT5-B) mt4_loop(MT4-A) mt4_journal_worker(MT4-B)"
