@echo off
cd /d C:\broker-crm\backend
call venv\Scripts\activate.bat
python fetch_meta_leads.py >> C:\broker-crm\backend\logs_meta.txt 2>&1
