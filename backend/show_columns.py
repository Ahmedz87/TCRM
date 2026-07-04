import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import inspect
insp = inspect(engine)
for tbl in ["leads", "clients", "deals", "transactions"]:
    cols = [c["name"] for c in insp.get_columns(tbl)]
    print(f"=== {tbl} ({len(cols)} cols) ===")
    print("  " + ", ".join(cols))
    print()
