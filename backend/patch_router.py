p = "portal_router.py"
s = open(p, encoding="utf-8").read()
old = "UPDATE clients SET kyc_status=\x27pending\x27 WHERE id=:id AND kyc_status IS DISTINCT FROM \x27verified\x27"
new = "UPDATE clients SET kyc_status=\x27pending_review\x27 WHERE id=:id AND kyc_status IS DISTINCT FROM \x27verified\x27"
if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("portal_router.py patched - submit sets pending_review")
else:
    print("PATTERN NOT FOUND")
import py_compile; py_compile.compile(p, doraise=True); print("compiles OK")
