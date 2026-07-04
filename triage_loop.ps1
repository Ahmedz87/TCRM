# BrokerCRM ticket triage — run every 5 min by Task Scheduler (BrokerCRM-TicketTriage).
# Safe & deterministic: acknowledges new tickets + flags urgent ones. No code changes, no restarts.
$ErrorActionPreference = 'SilentlyContinue'
$py     = 'C:\broker-crm\backend\venv\Scripts\python.exe'
$script = 'C:\broker-crm\backend\triage_tickets.py'
$log    = 'C:\broker-crm\backend\triage.log'
$env:PYTHONIOENCODING = 'utf-8'
# keep the log from growing unbounded (trim to last 500 lines occasionally)
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 200KB)) {
    Get-Content $log -Tail 500 | Set-Content "$log.tmp"; Move-Item "$log.tmp" $log -Force
}
& $py $script *>> $log
