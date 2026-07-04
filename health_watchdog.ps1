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

$healthy = $false
try {
  $r = Invoke-WebRequest -Uri "http://localhost:8000/health/full" -TimeoutSec 6 -UseBasicParsing
  if ($r.StatusCode -eq 200) { $j = $r.Content | ConvertFrom-Json; if ($j.db -eq $true) { $healthy = $true } }
} catch {}

if ($healthy) { exit 0 }

Log "[watchdog] backend unhealthy -> restarting"
& "C:\broker-crm\restart_backend.ps1"
