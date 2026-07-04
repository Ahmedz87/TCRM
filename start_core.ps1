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
    Where-Object { $_.CommandLine -match 'uvicorn|meta_poller' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$py = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be = "C:\broker-crm\backend"
Start-Process -FilePath "C:\nginx\nginx.exe" -ArgumentList "-p","C:\nginx" -WorkingDirectory "C:\nginx" -WindowStyle Hidden
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $be -WindowStyle Hidden
Start-Sleep -Seconds 5
Start-Process -FilePath $py -ArgumentList "meta_poller.py" -WorkingDirectory $be -WindowStyle Hidden
Log "core started (nginx, backend, meta_poller)"
