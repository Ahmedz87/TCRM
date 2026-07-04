p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

old_loop = '''            mgr = _get_mt5()
            if mgr:
                for (login,) in rows:
                    if not _auto_running["on"]: break
                    _do_cover(mgr, login, mode="auto")
                mgr.Disconnect()'''
new_loop = '''            for (login,) in rows:
                if not _auto_running["on"]: break
                _do_cover(None, login, mode="auto")  # uses bridge'''

if old_loop in s:
    s = s.replace(old_loop, new_loop)
    open(p, "w", encoding="utf-8").write(s)
    print("Auto loop fixed - uses bridge now")
else:
    print("Pattern not found, showing auto loop:")
    i = s.find("def _auto_loop")
    print(s[i:i+350])

import py_compile
try:
    py_compile.compile(p, doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
