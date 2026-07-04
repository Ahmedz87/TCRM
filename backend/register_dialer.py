# Run this on your server to register the dialer router in main.py
with open(r'C:\broker-crm\backend\main.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'power_dialer' not in content:
    content = content.replace(
        "from abuse_router import router as abuse_router",
        "from abuse_router import router as abuse_router\nfrom power_dialer_router import router as dialer_router"
    )
    content = content.replace(
        "app.include_router(abuse_router)",
        "app.include_router(abuse_router)\napp.include_router(dialer_router)"
    )
    with open(r'C:\broker-crm\backend\main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Done! Dialer router registered.")
else:
    print("Already registered.")
