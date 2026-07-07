# Multi-instance backend restart (4 uvicorn instances behind nginx load-balancing).
# uvicorn --workers is broken on this Windows box (WinError 87 in multiprocessing spawn), so we
# run separate single-worker instances on ports 8000-8003 and let nginx round-robin them.
#   8000 = PRIMARY: RUN_INPROC_LOOPS=1 -> runs the negative-balance cover loop (MT5Manager,
#          one connection per login) + serves web. Binds 0.0.0.0 (unchanged from before).
#   8001-8003 = WEB-ONLY: RUN_INPROC_LOOPS=0 -> no in-app loops, just serve requests. 127.0.0.1.
# Shrunk DB pool per instance (8+6=14) so 4 instances = ~56 connections, under max_connections=200.
# Rollback to single worker: run restart_backend_single.ps1
#
# Deploy:  powershell -ExecutionPolicy Bypass -File C:\broker-crm\restart_backend.ps1
$ErrorActionPreference = 'SilentlyContinue'
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be  = "C:\broker-crm\backend"
$log = "C:\broker-crm\restart.log"
$ports = @(8000,8001,8002,8003)
function Log($m) { "$(Get-Date -Format s)  $m" | Out-File -Append -Encoding utf8 $log; Write-Host $m }

Log "[restart] stopping uvicorn tree..."
for ($i = 0; $i -lt 8; $i++) {
  $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' }
  $listen = Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue
  if (-not $procs -and -not $listen) { break }
  foreach ($p in $procs)  { taskkill /F /T /PID $p.ProcessId 2>$null | Out-Null }
  foreach ($l in $listen) { taskkill /F /T /PID $l.OwningProcess 2>$null | Out-Null }
  Start-Sleep -Seconds 2
}

Log "[restart] starting 4 instances..."
$env:BROKER_POOL_SIZE = "8"; $env:BROKER_POOL_OVERFLOW = "6"
$env:RUN_INPROC_LOOPS = "1"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.8000.err" -RedirectStandardOutput "$be\logs\uvicorn.8000.out" -WindowStyle Hidden
$env:RUN_INPROC_LOOPS = "0"
foreach ($p in 8001,8002,8003) {
  Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","$p" -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.$p.err" -RedirectStandardOutput "$be\logs\uvicorn.$p.out" -WindowStyle Hidden
}
Remove-Item Env:RUN_INPROC_LOOPS, Env:BROKER_POOL_SIZE, Env:BROKER_POOL_OVERFLOW -ErrorAction SilentlyContinue

$allUp = $true
foreach ($p in $ports) {
  $ok = $false
  for ($i = 0; $i -lt 40; $i++) {
    try { if ((Invoke-WebRequest "http://127.0.0.1:$p/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) { $ok = $true; break } } catch {}
    Start-Sleep -Seconds 1
  }
  if ($ok) { Log "[restart] port $p UP" } else { Log "[restart] port $p FAILED"; $allUp = $false }
}
if ($allUp) { Log "[restart] all 4 instances UP and healthy." ; exit 0 }
Log "[restart] one or more instances did NOT come up. Check logs uvicorn.PORT.err. Rollback: restart_backend_single.ps1"
exit 1
