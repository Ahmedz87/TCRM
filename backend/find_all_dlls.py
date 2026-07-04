import os

base = r'C:\Program Files (x86)\MetaTrader 4 Manager'
print(f"All files including hidden in {base}:")
for root, dirs, files in os.walk(base):
    # Include hidden files
    dirs[:] = [d for d in dirs]
    for f in files:
        full = os.path.join(root, f)
        try:
            size = os.path.getsize(full)
            print(f"  {full}  ({size:,} bytes)")
        except:
            print(f"  {full}  (no access)")
