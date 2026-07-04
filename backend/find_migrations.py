import os
files = os.listdir(r"C:\broker-crm\backend")
# Scripts that add columns
add_scripts = [f for f in files if f.endswith(".py") and ("add_" in f or "alter" in f.lower() or "column" in f.lower() or "migrate" in f.lower())]
print("=== Column/migration scripts found ===")
for f in sorted(add_scripts):
    print("  " + f)
