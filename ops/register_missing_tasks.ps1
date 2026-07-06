# register_missing_tasks.ps1  —  REVIEW, then run from an elevated (admin) PowerShell.
#
# The ops review found three Task Scheduler entries referenced by the project scripts but
# NOT actually registered, so there is no bridge auto-start, no self-healing, and no off-box
# backup pull. All three target scripts already exist and are correct; this only registers
# the tasks that run them. Mirrors the existing BrokerCRM-Startup task's pattern.
#
# Run:  powershell -ExecutionPolicy Bypass -File C:\Broker-crm\ops\register_missing_tasks.ps1
# Undo: Unregister-ScheduledTask -TaskName BrokerCRM-Bridges,BrokerCRM-Watchdog,BrokerCRM-OffboxBackup -Confirm:$false
#
# NOTE on principals:
#  - Bridges MUST run in an interactive desktop session (the native MT manager DLL hangs under
#    SYSTEM/session-0), so it runs as Administrator at logon (LogonType Interactive).
#  - OffboxBackup uses Administrator's SSH key, so it also runs as Administrator. With
#    LogonType Interactive it only fires while Administrator is logged in (consistent with the
#    bridges). To run it even when logged out, re-register with a stored-password principal.
#  - Watchdog runs as SYSTEM (same as BrokerCRM-Startup); it only touches nginx + the backend.

$ErrorActionPreference = 'Stop'
$ps = 'powershell.exe'

function Register-One($name, $args, $principal, $trigger) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Write-Host "[$name] exists -> unregistering to re-create"
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
    $action = New-ScheduledTaskAction -Execute $ps -Argument $args
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[$name] registered."
}

# ── BrokerCRM-Bridges: MT4/MT5 bridges at admin logon (interactive session required) ──
$bridgesPrincipal = New-ScheduledTaskPrincipal -UserId 'Administrator' -LogonType Interactive -RunLevel Highest
$bridgesTrigger   = New-ScheduledTaskTrigger -AtLogOn -User 'Administrator'
Register-One 'BrokerCRM-Bridges' `
    '-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File C:\Broker-crm\start_bridges.ps1' `
    $bridgesPrincipal $bridgesTrigger

# ── BrokerCRM-Watchdog: self-heal nginx + backend every 5 minutes ──
$wdPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$wdTrigger   = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) `
                 -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-One 'BrokerCRM-Watchdog' `
    '-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File C:\Broker-crm\health_watchdog.ps1' `
    $wdPrincipal $wdTrigger

# ── BrokerCRM-OffboxBackup: pull newest DB dump to the CRM box daily 04:00 ──
# Requires the DB box host key to be trusted first — run setup_offbox_backup_trust.ps1 once.
$obPrincipal = New-ScheduledTaskPrincipal -UserId 'Administrator' -LogonType Interactive -RunLevel Highest
$obTrigger   = New-ScheduledTaskTrigger -Daily -At 4:00am
Register-One 'BrokerCRM-OffboxBackup' `
    '-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File C:\Broker-crm\pull_offbox_backup.ps1' `
    $obPrincipal $obTrigger

Write-Host ""
Write-Host "Done. Verify with:  Get-ScheduledTask -TaskName BrokerCRM-* | Format-Table TaskName,State"
Write-Host "Smoke-test the watchdog now:  & C:\Broker-crm\health_watchdog.ps1 ; Get-Content C:\broker-crm\watchdog.log -Tail 5"
