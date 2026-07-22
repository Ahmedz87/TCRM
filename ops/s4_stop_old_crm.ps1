# s4_stop_old_crm.ps1 — run ON S4 (199.247.5.96) as Administrator.
#
# Stops the OLD CRM stack that is still double-writing to the live DB (old MT5 bridge updating
# trading_accounts with stale values, old meta poller inserting leads, etc. — it was the "ghost
# writer" that kept zeroing client deposit totals; see S1 memory client-totals-bug-guard).
#
# SCOPE (deliberately narrow — touches NOTHING else, especially not Ovadot):
#   • kills python.exe processes whose command line references the old CRM folder (broker-crm)
#     or its scripts (bridge.py / mt4_loop / meta_poller / uvicorn main:app / mt5_deal_worker /
#     mt4_journal_worker / enrich_loop / tradesoft)
#   • disables Task-Scheduler tasks named BrokerCRM-*
#   • does NOT stop nginx, does NOT touch any non-broker-crm process, folder, or task.
#
# It PRINTS what it will kill first, then acts, then shows what's left running.

Write-Host "=== S4 old-CRM cleanup ===" -ForegroundColor Cyan

# 1) find old CRM python processes
$targets = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -match 'broker-crm|bridge\.py|mt4_loop|mt4_journal_worker|mt5_deal_worker|meta_poller|uvicorn|enrich_loop|tradesoft|fetch_meta|fetch_mt4|ib_refresh|copy_loop|run_abuse'
}
if ($targets) {
    Write-Host "`nWill stop these OLD CRM processes:" -ForegroundColor Yellow
    $targets | ForEach-Object { "{0,7}  {1}" -f $_.ProcessId, $_.CommandLine.Substring(0,[Math]::Min(110,$_.CommandLine.Length)) }
    # include their child interpreters (venv launcher -> real python)
    $tp = @($targets.ProcessId)
    $kids = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $tp -contains $_.ParentProcessId }
    @($targets) + @($kids) | Sort-Object ProcessId -Unique | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host ("stopped {0}" -f $_.ProcessId)
    }
} else {
    Write-Host "no old CRM python processes found" -ForegroundColor Green
}

# 2) disable the old auto-start tasks so they never come back on reboot/logon
Get-ScheduledTask | Where-Object { $_.TaskName -like 'BrokerCRM*' } | ForEach-Object {
    Disable-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue | Out-Null
    Write-Host ("disabled task: {0}" -f $_.TaskName)
}

# 3) show everything still running (so you can confirm Ovadot etc. is untouched)
Write-Host "`n=== python processes STILL running (should be only Ovadot / non-CRM) ===" -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
    $cl = $_.CommandLine; if (-not $cl) { $cl = "(no cmdline)" }
    "{0,7}  {1}" -f $_.ProcessId, $cl.Substring(0, [Math]::Min(110, $cl.Length))
}

Write-Host "`nDone. The live DB should stop receiving writes from this box within a minute." -ForegroundColor Green
