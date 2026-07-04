import os, glob

# 1. Find ALL clients_router.py files on the system
print("=== All clients_router.py files ===")
for base in [r"C:\broker-crm", r"C:\broker-crm\backend"]:
    for f in glob.glob(os.path.join(base, "**", "clients_router*.py"), recursive=True):
        size = os.path.getsize(f)
        has_marker = "_patch_marker" in open(f, encoding="utf-8", errors="ignore").read()
        print(f"  {f}  ({size} bytes, marker={has_marker})")

# 2. What does main.py import for clients?
print("\n=== main.py clients import ===")
mp = open(r"C:\broker-crm\backend\main.py", encoding="utf-8").read()
for line in mp.split("\n"):
    if "client" in line.lower() and ("import" in line or "include_router" in line):
        print(f"  {line.strip()}")

# 3. Check the working directory the server runs from
print("\n=== Current working dir ===")
print(" ", os.getcwd())
