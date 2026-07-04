# Pull the newest broker_crm dump from the dedicated DB box (199.247.6.189) to the CRM box.
# A second physical machine = a genuine off-box backup copy. Runs daily ~04:00 (after the DB
# box's own 03:00 pg_dump cron). Keeps the newest 14 locally.
$ErrorActionPreference = "Stop"
$Dest = "C:\broker-crm\backups\offbox"
$DbBox = "root@199.247.6.189"
$Log = "$Dest\offbox_pull.log"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

try {
    # newest dump filename on the DB box
    $newest = (ssh -o BatchMode=yes -o ConnectTimeout=20 $DbBox "ls -1t /var/backups/broker_crm/*.dump 2>/dev/null | head -1").Trim()
    if (-not $newest) { throw "no dump found on DB box" }
    $fname = Split-Path $newest -Leaf
    $local = Join-Path $Dest $fname

    if (Test-Path $local) {
        "$(Get-Date -Format s)  already have $fname - skip" | Add-Content $Log
    } else {
        scp -o BatchMode=yes -o ConnectTimeout=20 "${DbBox}:$newest" $local
        $sz = "{0:N0} MB" -f ((Get-Item $local).Length / 1MB)
        "$(Get-Date -Format s)  pulled $fname ($sz)" | Add-Content $Log
    }

    # prune: keep newest 14
    Get-ChildItem $Dest -Filter "broker_crm-*.dump" | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 14 | Remove-Item -Force -ErrorAction SilentlyContinue
}
catch {
    "$(Get-Date -Format s)  ERROR: $($_.Exception.Message)" | Add-Content $Log
    throw
}
