p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()
i = s.find("def _do_cover")
j = s.find("\ndef ", i+10)
if j < 0: j = s.find("\n@router", i)
print(s[i:j])
