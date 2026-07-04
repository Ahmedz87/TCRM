# -*- coding: utf-8 -*-
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from database import SessionLocal
import whatsapp_ai
db=SessionLocal()
cfg=whatsapp_ai.save_config(db, {
    "api_endpoint": "https://live-mt-server.wati.io/322549",
    "api_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1bmlxdWVfbmFtZSI6InJlZW1qQHRuZnguY28iLCJuYW1laWQiOiJyZWVtakB0bmZ4LmNvIiwiZW1haWwiOiJyZWVtakB0bmZ4LmNvIiwiYXV0aF90aW1lIjoiMDUvMTkvMjAyNiAyMjoxMjozNSIsInRlbmFudF9pZCI6IjMyMjU0OSIsImRiX25hbWUiOiJtdC1wcm9kLVRlbmFudHMiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBRE1JTklTVFJBVE9SIiwiZXhwIjoyNTM0MDIzMDA4MDAsImlzcyI6IkNsYXJlX0FJIiwiYXVkIjoiQ2xhcmVfQUkifQ.2AL-fTkhyk7Iq24kfCfAtkDBvR2TJlnfi0giquJ0jYw",
    "enabled": False, "auto_reply": True, "ai_owns_leads": True,
})
print("saved:", {k:cfg[k] for k in ('enabled','auto_reply','ai_owns_leads','api_endpoint','api_token_set')})
db.close()
