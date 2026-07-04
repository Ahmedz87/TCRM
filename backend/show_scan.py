p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()
i = s.find('@router.get("/scan")')
j = s.find("@router", i+10)
print(s[i:j])
