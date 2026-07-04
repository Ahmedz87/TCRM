p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()
s = s.replace(
    'r = _j.loads(_u.urlopen(req, timeout=30).read())',
    'r = _j.loads(_u.urlopen(req, timeout=60).read())'
)
open(p, "w", encoding="utf-8").write(s)
print("Cover timeout increased to 60s. Verify:", "timeout=60" in s)
import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
