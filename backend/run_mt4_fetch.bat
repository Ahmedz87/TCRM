@echo off
cd /d C:\broker-crm\backend
call venv\Scripts\activate.bat
python fetch_mt4_once.py >> C:\broker-crm\backend\logs_mt4.txt 2>&1
