# Hourly TradeSoft -> CRM sync (Task: BrokerCRM-TradeSoftSync). Mirror refresh + incremental reconcile.
$ErrorActionPreference = 'SilentlyContinue'
Set-Location 'C:\broker-crm\backend'
& 'C:\broker-crm\backend\venv\Scripts\python.exe' 'tradesoft_sync.py'
