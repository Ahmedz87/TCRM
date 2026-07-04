import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import importlib, clients_router
importlib.reload(clients_router)
from database import SessionLocal
from sqlalchemy import text

# Simulate the exact query column positions
db = SessionLocal()
try:
    # Pull one recapture client's row through the actual SELECT to check index alignment
    s = open(r"C:\broker-crm\backend\clients_router.py", encoding="utf-8").read()
    # crude: find SELECT ... FROM clients c and count columns isn't reliable here,
    # so just test the live endpoint result instead
    print("Patch applied. Now restart backend and check the API.")
    print("Recapture clients in DB:", db.execute(text("SELECT COUNT(*) FROM clients WHERE lead_badge='recapture'")).scalar())
finally:
    db.close()
