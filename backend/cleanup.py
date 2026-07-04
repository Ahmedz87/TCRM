import os, glob
backend = r"C:\broker-crm\backend"
frontend = r"C:\broker-crm\frontend\src"
removed = 0
for folder in [backend, frontend]:
    for f in glob.glob(os.path.join(folder, "*(1)*")) + glob.glob(os.path.join(folder, "*_current*")) + glob.glob(os.path.join(folder, "*_export*")):
        try:
            os.remove(f); print(f"Removed: {os.path.basename(f)}"); removed+=1
        except: pass
print(f"Cleaned {removed} duplicate/old files.")
