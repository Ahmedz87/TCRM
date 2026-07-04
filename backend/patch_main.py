p = r"C:\broker-crm\backend\main.py"
s = open(p, encoding="utf-8").read()
if "hedge_router" not in s:
    s = s.replace("from abuse_router import router as abuse_router",
                  "from abuse_router import router as abuse_router\nfrom hedge_router import router as hedge_router")
    s = s.replace("app.include_router(abuse_router)",
                  "app.include_router(abuse_router)\napp.include_router(hedge_router)")
    open(p, "w", encoding="utf-8").write(s)
    print("hedge_router registered")
else:
    print("already registered")
