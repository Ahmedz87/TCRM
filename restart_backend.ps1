# Multi-instance backend restart — ROLLING (zero-downtime) by default.
#
# uvicorn --workers is broken on this Windows box (WinError 87 in multiprocessing spawn), so we
# run separate single-worker instances and let nginx load-balance them (upstream crm_backend,
# `hash $http_authorization consistent` — see nginx.conf):
#   8000      = PRIMARY: RUN_INPROC_LOOPS=1 -> negative-balance cover loop (MT5Manager) + web.
#               Binds 0.0.0.0. NOT in the nginx upstream, so restarting it never touches web traffic.
#   8001-8005 = WEB: RUN_INPROC_LOOPS=0, 127.0.0.1. These five ARE the nginx upstream.
#
# WHY ROLLING (Jul 16 2026): the old script killed EVERY instance at once, so for the ~20s cold
# start nginx had "no live upstreams" and returned 502 to real users (proven in nginx error.log —
# a live client eating 502s on /api/notifications mid-deploy). Now each web instance is taken out,
# restarted and health-checked ONE AT A TIME, so 4 of 5 are always serving; nginx's default
# proxy_next_upstream (error/timeout) re-routes anyone hashed to the instance that is momentarily
# down. Trade-off: for a few seconds old and new code serve side by side (fine for stateless HTTP;
# if a deploy needs a hard cutover — e.g. an incompatible schema change — use -BigBang).
#
# Deploy:   powershell -ExecutionPolicy Bypass -File C:\broker-crm\restart_backend.ps1
# Hard cut: ... restart_backend.ps1 -BigBang      (old behaviour: kill all, start all, ~20s of 502s)
# Rollback: restart_backend_single.ps1            (single instance on 8000)
param([switch]$BigBang)

$ErrorActionPreference = 'SilentlyContinue'
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be  = "C:\broker-crm\backend"
$log = "C:\broker-crm\restart.log"
$webPorts = @(8001,8002,8003,8004,8005)   # the nginx upstream
$allPorts = @(8000) + $webPorts
function Log($m) { "$(Get-Date -Format s)  $m" | Out-File -Append -Encoding utf8 $log; Write-Host $m }

# CUTOVER (Jul 17 2026): the WEB instances (8001-8005) connect through PgBouncer (S2:6432,
# transaction pooling) instead of direct :5432 — the fix for QueuePool-timeout 500s under a burst
# of distinct users. Derived from .env at RUNTIME so the DB password is never written in this file.
# 8000 (neg-cover loop) + all scripts/loops (job_worker, enrich_loop, meta_poller, ...) stay on
# .env's :5432 direct — they run long batch queries that pgbouncer's query_timeout would kill.
$dbUrl6432 = ((Get-Content "$be\.env" | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=','') -replace '199\.247\.6\.189:5432','199.247.6.189:6432'

# Kill exactly the instance on one port. The venv python.exe is a LAUNCHER that spawns the base
# interpreter as a CHILD, and the child is what holds the socket — so match BOTH by "--port <p>" on
# the command line (the child inherits the args) and by whoever is actually listening on the port.
function Stop-Instance($port) {
  $ids = @()
  $ids += (Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
           Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match "--port\s+$port(\s|`$)" }
          ).ProcessId
  $ids += (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess
  foreach ($id in ($ids | Where-Object { $_ } | Sort-Object -Unique)) { taskkill /F /T /PID $id 2>$null | Out-Null }
  for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Start-Instance($port) {
  # smaller pool per instance so 6 instances stay under DB max_connections=200 (6 x (6+4) = 60)
  $env:BROKER_POOL_SIZE = "15"; $env:BROKER_POOL_OVERFLOW = "10"
  if ($port -eq 8000) {
    $env:RUN_INPROC_LOOPS = "1"; $bind = "0.0.0.0"            # loops -> stay direct on .env :5432
  } else {
    $env:RUN_INPROC_LOOPS = "0"; $bind = "127.0.0.1"
    if ($dbUrl6432 -match ':6432/') { $env:DATABASE_URL = $dbUrl6432 }   # web -> PgBouncer
  }
  Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host",$bind,"--port","$port" `
    -WorkingDirectory $be -RedirectStandardError "$be\logs\uvicorn.$port.err" `
    -RedirectStandardOutput "$be\logs\uvicorn.$port.out" -WindowStyle Hidden
  Remove-Item Env:RUN_INPROC_LOOPS, Env:BROKER_POOL_SIZE, Env:BROKER_POOL_OVERFLOW, Env:DATABASE_URL -ErrorAction SilentlyContinue
}

function Wait-Healthy($port, $tries = 60) {
  for ($i = 0; $i -lt $tries; $i++) {
    try { if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) { return $true } } catch {}
    Start-Sleep -Seconds 1
  }
  return $false
}

$failed = @()

if ($BigBang) {
  Log "[restart] BIG BANG: stopping ALL uvicorn instances (expect ~20s of 502s)..."
  for ($i = 0; $i -lt 8; $i++) {
    $procs  = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' }
    $listen = Get-NetTCPConnection -LocalPort $allPorts -State Listen -ErrorAction SilentlyContinue
    if (-not $procs -and -not $listen) { break }
    foreach ($p in $procs)  { taskkill /F /T /PID $p.ProcessId 2>$null | Out-Null }
    foreach ($l in $listen) { taskkill /F /T /PID $l.OwningProcess 2>$null | Out-Null }
    Start-Sleep -Seconds 2
  }
  foreach ($p in $allPorts) { Start-Instance $p }
  foreach ($p in $allPorts) {
    if (Wait-Healthy $p) { Log "[restart] port $p UP" } else { Log "[restart] port $p FAILED"; $failed += $p }
  }
}
else {
  # ---- rolling: one web instance at a time; nginx always keeps the other 4 serving ----
  Log "[restart] ROLLING restart of web instances $($webPorts -join ',') (nginx keeps the rest serving)..."
  foreach ($p in $webPorts) {
    if (-not (Stop-Instance $p)) { Log "[restart] port $p did not free up; aborting the roll."; $failed += $p; break }
    Start-Instance $p
    if (Wait-Healthy $p) {
      Log "[restart] port $p UP (rolled)"
    } else {
      # Do NOT keep rolling — that is exactly how you end up with every instance down.
      Log "[restart] port $p FAILED to come up. STOPPING the roll so the remaining instances keep serving."
      Log "[restart] check $be\logs\uvicorn.$p.err"
      $failed += $p; break
    }
  }
  # 8000 is outside the nginx upstream (loops), so it rolls last with no web-traffic impact
  if ($failed.Count -eq 0) {
    Log "[restart] rolling primary 8000 (loops; not in the nginx upstream)..."
    if (Stop-Instance 8000) {
      Start-Instance 8000
      if (Wait-Healthy 8000) { Log "[restart] port 8000 UP (rolled)" } else { Log "[restart] port 8000 FAILED"; $failed += 8000 }
    } else { Log "[restart] port 8000 did not free up"; $failed += 8000 }
  }
}

if ($failed.Count -gt 0) {
  Log "[restart] FAILED instances: $($failed -join ','). The others are still serving. Check logs\uvicorn.PORT.err."
  exit 1
}

Log "[restart] all instances UP and healthy. Pre-warming caches (~90s)..."
Push-Location $be
$warm = & $py "$be\prewarm.py" 2>&1
Pop-Location
$warm | ForEach-Object { Log "  $_" }
Log "[restart] pre-warm done."
exit 0
