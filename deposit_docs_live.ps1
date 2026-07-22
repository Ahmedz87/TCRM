# Near-real-time deposit-docs pull (every ~10 min). Pulls only the last 2 days of TradeSoft
# deposits into deposit_documents + pay_qi_card/pay_zaincash/pay_sham_cash (cheap, idempotent).
# The S3 box's ocr_watch.py then OCRs each new receipt within ~75s. The nightly full build
# (BrokerCRM-DepositDocs, 03:45) stays as the catch-all safety net.
$ErrorActionPreference = 'SilentlyContinue'
$log = "C:\Broker-crm\backend\logs\deposit_docs_live.log"
function Log($m){ "$(Get-Date -Format s)  $m" | Out-File -Append -Encoding utf8 $log }
Set-Location 'C:\broker-crm\backend'
$py = 'C:\broker-crm\backend\venv\Scripts\python.exe'
Log "live pull start"
& $py build_deposit_docs.py --recent 2 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
& $py create_pay_method_tables.py 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
Log "live pull done"
