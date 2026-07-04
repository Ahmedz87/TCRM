@echo off
REM One TradeSoft data refresh (MySQL -> tradesoft_crm). Driven hourly by the
REM TradeSoftCRM-Refresh scheduled task. Appends output to refresh.log.
cd /d "C:\Broker-crm\tradesoft-crm\backend"
"C:\Broker-crm\tradesoft-crm\backend\venv\Scripts\python.exe" refresh.py >> "C:\Broker-crm\tradesoft-crm\backend\refresh.log" 2>&1
