# Daily deposit-docs refresh (Task: BrokerCRM-DepositDocs, 03:45).
# Pulls NEW TradeSoft deposits into deposit_documents + pay_qi_card/pay_zaincash/pay_sham_cash
# (idempotent, additive). The S3 box (192.248.181.91) then fetches the receipt files at 04:30
# and runs the Haiku sender/receiver OCR + transaction_wallet rebuild (cron: /root/nightly_docs.sh).
$ErrorActionPreference = 'SilentlyContinue'
$log = "C:\Broker-crm\backend\logs\deposit_docs_task.log"
function Log($m){ "$(Get-Date -Format s)  $m" | Out-File -Append -Encoding utf8 $log }
Set-Location 'C:\broker-crm\backend'
$py = 'C:\broker-crm\backend\venv\Scripts\python.exe'
Log "=== deposit docs refresh start ==="
& $py build_deposit_docs.py 2>&1 | Select-Object -Last 2 | ForEach-Object { Log $_ }
& $py create_pay_method_tables.py 2>&1 | ForEach-Object { Log $_ }
Log "=== done ==="
