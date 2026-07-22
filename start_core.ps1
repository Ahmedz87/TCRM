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
    Where-Object { $_.CommandLine -match 'uvicorn|meta_poller|dialer_events|job_worker' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$py = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be = "C:\broker-crm\backend"
# CUTOVER (Jul 17 2026): web instances 8001-8005 connect via PgBouncer (S2:6432); 8000 (loops) +
# all scripts/loops stay on .env :5432 direct. Derived from .env at runtime (password never in file).
$dbUrl6432 = ((Get-Content "$be\.env" | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=','') -replace '199\.247\.6\.189:5432','199.247.6.189:6432'
Start-Process -FilePath "C:\nginx\nginx.exe" -ArgumentList "-p","C:\nginx" -WorkingDirectory "C:\nginx" -WindowStyle Hidden
# 6 uvicorn instances behind nginx LB. MUST MATCH restart_backend.ps1 AND the nginx upstream
# (nginx hashes users across 8001-8005; 8000 runs the in-proc neg-cover loop and is kept off the
# hot path). Jul 16: this file still said 8001-8003 after the tier grew to 8001-8005, so a REBOOT
# left 8004/8005 dead and nginx retried into two missing upstreams. Keep these three in sync.
$env:BROKER_POOL_SIZE = "15"; $env:BROKER_POOL_OVERFLOW = "10"
$env:RUN_INPROC_LOOPS = "1"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.8000.err" -RedirectStandardOutput "$be\logs\uvicorn.8000.out" -WindowStyle Hidden
$env:RUN_INPROC_LOOPS = "0"
if ($dbUrl6432 -match ':6432/') { $env:DATABASE_URL = $dbUrl6432 }   # web tier -> PgBouncer
foreach ($wp in 8001,8002,8003,8004,8005) {
  Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","$wp" -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.$wp.err" -RedirectStandardOutput "$be\logs\uvicorn.$wp.out" -WindowStyle Hidden
}
Remove-Item Env:RUN_INPROC_LOOPS, Env:BROKER_POOL_SIZE, Env:BROKER_POOL_OVERFLOW, Env:DATABASE_URL -ErrorAction SilentlyContinue
Start-Sleep -Seconds 8
# Redirect stdout/stderr to files: without it these print to a hidden console whose handle can
# break, and a print(flush=True) then raises "I/O operation on closed file" and kills the loop —
# that crashed enrich_loop (=> the notification bell + fast lead-enrichment froze, ticket #274).
Start-Process -FilePath $py -ArgumentList "meta_poller.py" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$be\logs\meta_poller.out" -RedirectStandardError "$be\logs\meta_poller.err"
Start-Process -FilePath $py -ArgumentList "enrich_loop.py" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$be\logs\enrich_loop.out" -RedirectStandardError "$be\logs\enrich_loop.err"
# Power Dialer call-status worker (Yeastar WebSocket -> auto-advance). Network + DB only,
# no interactive desktop needed, so it runs fine here under SYSTEM at boot.
Start-Process -FilePath $py -ArgumentList "dialer_events.py" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$be\logs\dialer_events.out" -RedirectStandardError "$be\logs\dialer_events.err"
# Durable job worker (job_worker.py) — drains the `jobs` table (real MT bonus credits, etc.) with
# retry/backoff so money-affecting async work survives restarts and never silently vanishes. DB +
# localhost-HTTP only. If the bridge isn't up yet at boot, credit jobs just retry until it is.
Start-Process -FilePath $py -ArgumentList "job_worker.py","--loop" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$be\logs\job_worker.out" -RedirectStandardError "$be\logs\job_worker.err"
Log "core started (nginx, 6x backend, meta_poller, enrich_loop, dialer_events, job_worker)"
# Pre-warm every instance so the first person in after a reboot doesn't eat the cold-start
# (heavy list/KPI pages). Safe to fail — the 5-min BrokerCRM-Prewarm task also covers it.
Start-Sleep -Seconds 10
& $py "$be\prewarm.py" 2>&1 | Out-Null
Log "core pre-warmed"
