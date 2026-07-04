"""Run this once to create all missing tables"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import engine, Base
import models
Base.metadata.create_all(bind=engine)
print("All tables created OK")

# Check
from database import SessionLocal
db = SessionLocal()
print("Clients:", db.query(models.Client).count())
print("Network edges:", db.query(models.NetworkEdge).count())
print("Identifiers:", db.query(models.AccountIdentifier).count())
db.close()
