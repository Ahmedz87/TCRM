@echo off
REM TradeSoft CRM copy launcher. Runs in the Administrator interactive session
REM (uvicorn hangs under SYSTEM/session-0 on this box — same quirk as the MT bridges).
REM Self-restart loop: if uvicorn ever exits, relaunch after 3s so it self-heals.
cd /d "C:\Broker-crm\tradesoft-crm\backend"
set PY=C:\Broker-crm\tradesoft-crm\backend\venv\Scripts\python.exe
set LOG=C:\Broker-crm\tradesoft-crm\backend\task.log
echo === LAUNCHER START %DATE% %TIME% (user: %USERNAME%) === > "%LOG%"

:loop
echo --- starting uvicorn %DATE% %TIME% --- >> "%LOG%"
"%PY%" -u -m uvicorn main:app --host 127.0.0.1 --port 8090 --no-access-log >> "%LOG%" 2>&1
echo --- uvicorn exited (code %ERRORLEVEL%) %DATE% %TIME%, restarting in 3s --- >> "%LOG%"
timeout /t 3 /nobreak > NUL
goto loop
