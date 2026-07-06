# setup_offbox_backup_trust.ps1  --  run ONCE as Administrator (the account whose SSH key
# reaches the DB box). Fixes the "Host key verification failed" error that currently makes
# pull_offbox_backup.ps1 (and any non-interactive ssh to the DB box) fail.
#
# It adds the DB box's host key to Administrator's known_hosts so BatchMode ssh/scp can run
# unattended, then does a dry connectivity check. It does NOT change any keys or credentials.

$ErrorActionPreference = 'Stop'
$DbHost = '199.247.6.189'
$sshDir = Join-Path $env:USERPROFILE '.ssh'
$known  = Join-Path $sshDir 'known_hosts'

New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

# Capture the DB box's current host key (ed25519 + rsa) and append any lines not already present.
Write-Host "Scanning host key for $DbHost ..."
$scanned = & ssh-keyscan -H $DbHost 2>$null
if (-not $scanned) { throw "ssh-keyscan returned nothing. Is $DbHost reachable on port 22?" }

$existing = if (Test-Path $known) { Get-Content $known } else { @() }
$added = 0
foreach ($line in $scanned) {
    if ($existing -notcontains $line) { Add-Content -Path $known -Value $line; $added++ }
}
Write-Host "known_hosts updated (+$added lines): $known"

# Connectivity check (BatchMode = no password prompt; relies on Administrator's private key).
Write-Host "Testing unattended SSH to the DB box ..."
$test = & ssh -o BatchMode=yes -o ConnectTimeout=20 "root@$DbHost" "ls -1t /var/backups/broker_crm/*.dump 2>/dev/null | head -1"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "SSH still failing (exit $LASTEXITCODE). Check that Administrator's id_ed25519 is authorized on the DB box (ssh root@$DbHost by hand once)."
} elseif (-not $test) {
    Write-Warning "SSH works but no dump files found in /var/backups/broker_crm. Verify the DB box's 03:00 pg_dump cron is actually producing dumps."
} else {
    Write-Host "OK. Newest dump on DB box: $test"
    Write-Host "You can now run: & C:\Broker-crm\pull_offbox_backup.ps1  (and register BrokerCRM-OffboxBackup)."
}
