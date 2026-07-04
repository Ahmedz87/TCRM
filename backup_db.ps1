# Broker CRM — daily PostgreSQL backup (custom-format dump, restorable via pg_restore).
# Keeps the most recent 14 backups.
$ErrorActionPreference = 'Stop'
$bdir = "C:\broker-crm\backups"
New-Item -ItemType Directory -Force -Path $bdir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out   = "$bdir\broker_crm-$stamp.dump"
$log   = "$bdir\backup.log"

# DB password read from the environment (set BROKER_DB_PASSWORD on the box); not hardcoded
$env:PGPASSWORD = $env:BROKER_DB_PASSWORD
try {
    & "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -h 199.247.6.189 -p 5432 -U postgres -d broker_crm -Fc -f $out
    if ($LASTEXITCODE -ne 0) { throw "pg_dump exit code $LASTEXITCODE" }
    $size = (Get-Item $out).Length
    # prune: keep the 14 newest
    Get-ChildItem $bdir -Filter "broker_crm-*.dump" |
        Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 |
        Remove-Item -Force -ErrorAction SilentlyContinue
    "$(Get-Date -Format s)  OK  $out  ($([math]::Round($size/1MB,1)) MB)" | Out-File -Append -Encoding utf8 $log
} catch {
    "$(Get-Date -Format s)  FAIL  $($_.Exception.Message)" | Out-File -Append -Encoding utf8 $log
    throw
} finally {
    $env:PGPASSWORD = $null
}
