# Rebuild ib_trades (the IB Admin/Portal 'Trades' + per-IB commission source) from deals.
# One-shot rebuild (ib_trades.main = staging build + atomic swap, ~1-2 min). DB-only, no MT
# bridge / interactive session, so it runs fine under SYSTEM. Scheduled every 30 min + at boot.
# Root cause it fixes: ib_refresh_loop.py was a manual process with no persistence and died
# (froze ib_trades at Jun 29); this task keeps it live across reboots.
$ErrorActionPreference = "Continue"
$py  = "C:\broker-crm\backend\venv\Scripts\python.exe"
$log = "C:\broker-crm\backend\ib_refresh.log"
$env:PYTHONIOENCODING = "utf-8"
Set-Location C:\broker-crm\backend
"$(Get-Date -Format s)  === ib_trades rebuild start ===" | Add-Content $log
& $py -c "import ib_trades; ib_trades.main()" *>> $log
"$(Get-Date -Format s)  === ib_trades rebuild exit=$LASTEXITCODE ===" | Add-Content $log
