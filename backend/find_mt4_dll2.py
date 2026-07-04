import os, shutil

base = r'C:\Program Files (x86)\MetaTrader 4 Manager'
print(f"=== All files in {base} ===")
for f in os.listdir(base):
    full = os.path.join(base, f)
    size = os.path.getsize(full)
    print(f"  {f}  ({size:,} bytes)")

# Copy DLL to backend if found
print("\n=== Copying mtmanapi DLL to backend ===")
for f in os.listdir(base):
    if 'mtmanapi' in f.lower() or ('manager' in f.lower() and f.endswith('.dll')):
        src = os.path.join(base, f)
        dst = os.path.join(r'C:\broker-crm\backend', f)
        shutil.copy2(src, dst)
        print(f"  ✓ Copied: {f} → C:\\broker-crm\\backend\\")
