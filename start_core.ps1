# Broker CRM core — nginx + backend + meta poller. These run fine under SYSTEM,
# so this runs at boot (Task: BrokerCRM-Startup) and the site is live before anyone logs in.
$ErrorActionPreference = 'SilentlyContinue'
$log = "C:\broker-crm\startup.log"
function Log($m){ "$(Get-Date -Format s)  [core] $m" | Out-File -Append -Encoding utf8 $log }

Log "=== start_core invoked ==="
for ($i = 0; $i -lt 30; $i++) {
    if ((Get-Service postgresql-x64-16 -ErrorAction SilentlyContinue).Status -eq 'Running') { break }
    Start-Sleep -Seconds 2
}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn|meta_poller|dialer_events' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$py = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be = "C:\broker-crm\backend"
Start-Process -FilePath "C:\nginx\nginx.exe" -ArgumentList "-p","C:\nginx" -WorkingDirectory "C:\nginx" -WindowStyle Hidden
# 4 uvicorn instances behind nginx LB (8000 primary runs the neg-cover loop; 8001-8003 web-only).
# See restart_backend.ps1 for the topology rationale.
$env:BROKER_POOL_SIZE = "8"; $env:BROKER_POOL_OVERFLOW = "6"
$env:RUN_INPROC_LOOPS = "1"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.8000.err" -RedirectStandardOutput "$be\logs\uvicorn.8000.out" -WindowStyle Hidden
$env:RUN_INPROC_LOOPS = "0"
foreach ($wp in 8001,8002,8003) {
  Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","$wp" -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.$wp.err" -RedirectStandardOutput "$be\logs\uvicorn.$wp.out" -WindowStyle Hidden
}
Remove-Item Env:RUN_INPROC_LOOPS, Env:BROKER_POOL_SIZE, Env:BROKER_POOL_OVERFLOW -ErrorAction SilentlyContinue
Start-Sleep -Seconds 8
Start-Process -FilePath $py -ArgumentList "meta_poller.py" -WorkingDirectory $be -WindowStyle Hidden
Start-Process -FilePath $py -ArgumentList "enrich_loop.py" -WorkingDirectory $be -WindowStyle Hidden
# Power Dialer call-status worker (Yeastar WebSocket -> auto-advance). Network + DB only,
# no interactive desktop needed, so it runs fine here under SYSTEM at boot.
Start-Process -FilePath $py -ArgumentList "dialer_events.py" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$be\logs\dialer_events.out" -RedirectStandardError "$be\logs\dialer_events.err"
Log "core started (nginx, backend, meta_poller, enrich_loop, dialer_events)"
