# activate_and_verify.ps1  --  restart the backend to activate the hardening-fixes branch,
# then probe the endpoints to confirm the security fixes are actually live.
#
# Run from an elevated PowerShell on the CRM box:
#   powershell -ExecutionPolicy Bypass -File C:\Broker-crm\ops\activate_and_verify.ps1
#
# It (1) sets the maintenance flag so the watchdog won't fight the restart, (2) runs the
# project's restart_backend.ps1, (3) clears the flag, (4) runs read-only/unauthenticated
# probes. The probes are safe: the /register + /client-dashboard probes are UNAUTHENTICATED
# and now return 401/403 BEFORE doing anything, so nothing is created or read.

$ErrorActionPreference = 'Continue'
$base = 'http://localhost:8000'
$flag = 'C:\broker-crm\.maintenance'
$pass = 0; $fail = 0

function Status([scriptblock]$req) {
    # Return the HTTP status code for a request, whether it succeeds or throws (PS 5.1 style).
    try {
        $r = & $req
        return [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return -1
    }
}
function Check($name, $got, $want) {
    if ($got -eq $want) { Write-Host ("  PASS  {0} -> {1}" -f $name, $got) -ForegroundColor Green; $script:pass++ }
    else { Write-Host ("  FAIL  {0} -> got {1}, expected {2}" -f $name, $got, $want) -ForegroundColor Red; $script:fail++ }
}

# ── 1. restart ─────────────────────────────────────────────────────────────
Write-Host "[activate] pausing watchdog + restarting backend ..."
New-Item -ItemType File -Force -Path $flag | Out-Null
try {
    & C:\Broker-crm\restart_backend.ps1
} finally {
    Remove-Item $flag -Force -ErrorAction SilentlyContinue
}

# ── 2. wait for health ─────────────────────────────────────────────────────
$up = $false
for ($i = 0; $i -lt 30; $i++) {
    if ((Status { Invoke-WebRequest "$base/health" -TimeoutSec 3 -UseBasicParsing }) -eq 200) { $up = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $up) { Write-Host "[activate] backend did NOT come up healthy -- check backend\uvicorn.err.log" -ForegroundColor Red; exit 1 }
Write-Host "[verify] backend healthy. Probing security fixes ..."

# ── 3. probes ──────────────────────────────────────────────────────────────
# /auth/register with no token must now be rejected (was 200 = public account creation).
$reg = Status { Invoke-WebRequest "$base/auth/register" -Method POST -TimeoutSec 5 -UseBasicParsing `
        -ContentType 'application/json' `
        -Body '{"full_name":"probe","email":"probe-donotcreate@example.invalid","password":"x","role":"super_admin"}' }
Check '/auth/register unauthenticated is blocked (401)' $reg 401

# /client-dashboard/kpis/{login} with no token must now be 401 (was public financial data).
$kpi = Status { Invoke-WebRequest "$base/client-dashboard/kpis/1829" -TimeoutSec 5 -UseBasicParsing }
Check '/client-dashboard/kpis unauthenticated is blocked (401)' $kpi 401

# CORS: a disallowed Origin must NOT be echoed back in Access-Control-Allow-Origin.
$acao = $null
try {
    $r = Invoke-WebRequest "$base/health" -Headers @{ Origin = 'https://evil.example' } -TimeoutSec 5 -UseBasicParsing
    $acao = $r.Headers['Access-Control-Allow-Origin']
} catch {}
if ($acao -eq 'https://evil.example' -or $acao -eq '*') {
    Write-Host ("  FAIL  CORS still reflects a foreign origin -> {0}" -f $acao) -ForegroundColor Red; $fail++
} else {
    Write-Host ("  PASS  CORS does not reflect foreign origin (ACAO='{0}')" -f $acao) -ForegroundColor Green; $pass++
}

# ── 4. summary ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host ("[verify] {0} passed, {1} failed." -f $pass, $fail)
if ($fail -gt 0) {
    Write-Host "One or more fixes are NOT live. The old code may still be serving -- confirm restart_backend.ps1 reported UP, then re-run." -ForegroundColor Yellow
    exit 1
}
Write-Host "All security probes passed. Now smoke-test a real staff login + the client portal in a browser." -ForegroundColor Green
