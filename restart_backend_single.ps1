# Reliable single-instance backend restart.
# The venv python.exe is a LAUNCHER that spawns the base interpreter as a CHILD, and
# that child is what holds :8000. A naive Stop-Process on the launcher can leave the
# child alive serving STALE code while a new instance bind-fails. This script kills the
# whole uvicorn tree until :8000 is free, starts ONE uvicorn, then waits for /health so
# you know fresh code is actually serving.
#
# Use this for every backend deploy:  powershell -ExecutionPolicy Bypass -File C:\broker-crm\restart_backend.ps1
$ErrorActionPreference = 'SilentlyContinue'
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be  = "C:\broker-crm\backend"
$log = "C:\broker-crm\restart.log"
function Log($m) { "$(Get-Date -Format s)  $m" | Out-File -Append -Encoding utf8 $log; Write-Host $m }

Log "[restart] stopping uvicorn tree..."
for ($i = 0; $i -lt 8; $i++) {
  $port  = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' }
  if (-not $port -and -not $procs) { break }
  foreach ($p in $procs) { taskkill /F /T /PID $p.ProcessId 2>$null | Out-Null }
  if ($port) { taskkill /F /T /PID $port.OwningProcess 2>$null | Out-Null }
  Start-Sleep -Seconds 2
}

Log "[restart] starting one uvicorn..."
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $be -RedirectStandardError "$be\uvicorn.err.log" -RedirectStandardOutput "$be\uvicorn.out.log" -WindowStyle Hidden

for ($i = 0; $i -lt 30; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing
    if ($r.StatusCode -eq 200) { Log "[restart] UP and healthy."; exit 0 }
  } catch {}
  Start-Sleep -Seconds 1
}
Log "[restart] FAILED to come up within 30s - check uvicorn.err.log"
exit 1
