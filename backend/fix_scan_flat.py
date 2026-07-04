p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# After building 'out', add a live flat-check via bridge for credit-eligible accounts only
anchor = '''    # Sort: eligible first (by deficit desc), then everything else (credit_low) at bottom'''

flat_check = '''    # Live flat-check via bridge ONLY for credit-eligible accounts (keeps it fast)
    import urllib.request as _u, json as _j
    for a in out:
        if a["status"] == "eligible":
            try:
                chk = _j.loads(_u.urlopen(f"{BRIDGE_URL}/neg-cover/check/{a['login']}", timeout=8).read())
                a["credit"] = chk.get("credit", a["credit"])
                a["balance"] = chk.get("balance", a["balance"])
                a["deficit"] = abs(chk.get("balance", a["balance"])) if chk.get("balance",0) < 0 else 0
                if not chk.get("flat", False):
                    a["status"] = "has_positions"
                elif chk.get("balance", 0) >= 0:
                    a["status"] = "not_negative_now"
                elif chk.get("credit", 0) < a["deficit"]:
                    a["status"] = "credit_low"
                # else stays eligible
            except Exception:
                pass  # bridge unreachable - leave as credit-based eligible

'''

if anchor in s and "Live flat-check via bridge" not in s:
    s = s.replace(anchor, flat_check + anchor)
    open(p, "w", encoding="utf-8").write(s)
    print("Scan now does live flat-check for eligible accounts")
else:
    print("Already added or anchor not found")

import py_compile
try:
    py_compile.compile(p, doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
