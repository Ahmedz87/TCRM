import os, glob
frontend = r"C:\broker-crm\frontend\src"
# Find the main layout/header/sidebar files
for f in glob.glob(os.path.join(frontend, "**", "*.tsx"), recursive=True):
    name = os.path.basename(f)
    if any(k in name.lower() for k in ["layout","header","sidebar","topbar","nav","app"]):
        size = os.path.getsize(f)
        print(f"  {name} ({size} bytes)")
print("---")
# Also check App.tsx content for header/topbar structure
for cand in ["App.tsx","Layout.tsx","Sidebar.tsx"]:
    p = os.path.join(frontend, cand)
    if os.path.exists(p):
        c = open(p, encoding="utf-8", errors="ignore").read()
        has_bell = "🔔" in c or "notification" in c.lower()
        print(f"{cand}: {len(c)} chars, mentions notifications: {has_bell}")
