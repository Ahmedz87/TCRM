import os

base = r'C:\Users\Ahmad\AppData\Roaming\MetaQuotes\MetaTrader 4 Manager'
print(f"=== Scanning {base} ===")

for root, dirs, files in os.walk(base):
    for f in files:
        full = os.path.join(root, f)
        size = os.path.getsize(full)
        print(f"  {full}  ({size:,} bytes)")
