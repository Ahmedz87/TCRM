# Month-end performance snapshot + daily no-call nudge helper.
# Freezes LAST month's real performance score (so eligible commission never drifts) and refreshes
# the "deposit with no call" nudges. Schedule:
#   snapshot  -> monthly, day 1 ~00:30
#   no-call   -> daily (pass -NoCallOnly)
param([switch]$NoCallOnly)
$ErrorActionPreference = 'Continue'
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$be  = "C:\broker-crm\backend"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $be

# daily nudge
& $py notify_no_call.py --days 14

if (-not $NoCallOnly) {
  # freeze the PREVIOUS month (YYYY-MM)
  $lastMonth = (Get-Date).AddDays(-(Get-Date).Day).ToString('yyyy-MM')
  $code = @"
import sys; sys.path.insert(0, r'$be')
import sales_performance as SP
from database import SessionLocal
db = SessionLocal()
try:
    print(SP.freeze_month(db, '$lastMonth'))
finally:
    db.close()
"@
  $code | & $py -
}
