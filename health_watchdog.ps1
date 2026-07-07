# Self-healing watchdog. Runs every few minutes (Task: BrokerCRM-Watchdog).
#  - If nginx is down -> start it.
#  - If the backend is unhealthy (port dead OR /health/full says db is down) -> restart it.
#  - Pause during a deploy by creating  C:\broker-crm\.maintenance  (delete to resume).
# Only ever runs ONE uvicorn (restart_backend.ps1 frees :8000 first), so no duplicates.
$ErrorActionPreference = 'SilentlyContinue'
$log = "C:\broker-crm\watchdog.log"
function Log($m) { "$(Get-Date -Format s)  $m" | Out-File -Append -Encoding utf8 $log }

if (Test-Path "C:\broker-crm\.maintenance") { Log "[watchdog] maintenance flag set - skipping."; exit 0 }

if (-not (Get-Process nginx -ErrorAction SilentlyContinue)) {
  Log "[watchdog] nginx down -> starting"
  Start-Process -FilePath "C:\nginx\nginx.exe" -ArgumentList "-p","C:\nginx" -WorkingDirectory "C:\nginx" -WindowStyle Hidden
}

# Power Dialer event worker (Yeastar WebSocket -> auto-advance) — restart if it died.
if (-not (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*dialer_events*' })) {
  Log "[watchdog] dialer_events down -> starting"
  $dpy = "C:\broker-crm\backend\venv\Scripts\python.exe"; $dbe = "C:\broker-crm\backend"
  Start-Process -FilePath $dpy -ArgumentList "dialer_events.py" -WorkingDirectory $dbe -WindowStyle Hidden -RedirectStandardOutput "$dbe\logs\dialer_events.out" -RedirectStandardError "$dbe\logs\dialer_events.err"
}

$healthy = $false
try {
  $r = Invoke-WebRequest -Uri "http://localhost:8000/health/full" -TimeoutSec 6 -UseBasicParsing
  if ($r.StatusCode -eq 200) { $j = $r.Content | ConvertFrom-Json; if ($j.db -eq $true) { $healthy = $true } }
} catch {}

if ($healthy) { exit 0 }

Log "[watchdog] backend unhealthy -> restarting"
& "C:\broker-crm\restart_backend.ps1"
