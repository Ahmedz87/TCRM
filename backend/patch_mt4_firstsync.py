p = "bridge_mt4.py"
s = open(p, encoding="utf-8").read()
old = "            if cycle % 10 == 0:"
new = "            if cycle == 1 or cycle % 10 == 0:"
if old in s and "cycle == 1 or" not in s:
    s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s)
    print("PATCHED: full sync now runs on cycle 1 (immediately) AND every 10 cycles")
elif "cycle == 1 or" in s:
    print("Already patched")
else:
    print("PATTERN NOT FOUND - the trigger line differs; will check")
import py_compile; py_compile.compile(p, doraise=True); print("compiles OK")
