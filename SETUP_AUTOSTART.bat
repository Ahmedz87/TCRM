@echo off
REM One-time setup: registers the two missing scheduled tasks.
REM Right-click -> "Run as administrator" (or just double-click in an admin session).

echo Creating BrokerCRM-Bridges (starts MT bridges at logon)...
schtasks /create /tn "BrokerCRM-Bridges" /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Broker-crm\start_bridges.ps1" /sc onlogon /ru Administrator /f

echo Creating BrokerCRM-DepositDocs (daily 03:45 deposit-docs refresh)...
schtasks /create /tn "BrokerCRM-DepositDocs" /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Broker-crm\nightly_deposit_docs.ps1" /sc daily /st 03:45 /ru SYSTEM /f

echo Creating BrokerCRM-Prewarm (keeps all 4 backend instances' caches warm, every 5 min)...
schtasks /create /tn "BrokerCRM-Prewarm" /tr "C:\broker-crm\backend\venv\Scripts\python.exe C:\broker-crm\backend\prewarm.py" /sc minute /mo 5 /ru SYSTEM /f

echo.
echo Done. Verifying:
schtasks /query /tn "BrokerCRM-Bridges" /fo list | findstr "TaskName Status"
schtasks /query /tn "BrokerCRM-DepositDocs" /fo list | findstr "TaskName Status"
pause
