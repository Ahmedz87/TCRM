# Start the standalone TradeSoft CRM copy (read-only archive).
# Backend serves both the API and the built React SPA on http://127.0.0.1:8090
# Bound to localhost only — it holds real client data and has NO login, so it is
# NOT exposed publicly. Open it from a browser ON this server (via RDP), or put it
# behind nginx + auth if you need remote access.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$py = Join-Path $backend "venv\Scripts\python.exe"

# Free the port if something is already on it
Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "Starting TradeSoft CRM (copy) on http://127.0.0.1:8090 ..." -ForegroundColor Magenta
Set-Location $backend
& $py -m uvicorn main:app --host 127.0.0.1 --port 8090
