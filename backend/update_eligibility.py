p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Update the fast DB-based status logic to use the 3 eligibility rules
old = '''        deficit = abs(db_bal)
        # Status from DB data only (no live position check here - too slow)
        if credit >= deficit:
            status = "eligible"   # provisional - verified flat at cover time
        else:
            status = "credit_low"'''

new = '''        deficit = abs(db_bal)
        # 3 eligibility rules: balance >= -200, OR credit >= 50% deficit, OR credit >= full
        if db_bal >= -200 or credit >= deficit * 0.5 or credit >= deficit:
            status = "eligible"   # provisional - verified flat at cover time
        else:
            status = "credit_low"  # not auto-eligible, but manual Run still allowed'''

if old in s:
    s = s.replace(old, new)
    print("DB eligibility updated with 3 rules")
else:
    print("DB status block not matched")

# Also update the live flat-check section's re-evaluation to use same 3 rules
old2 = '''                elif chk.get("credit", 0) < a["deficit"]:
                    a["status"] = "credit_low"
                # else stays eligible'''
new2 = '''                else:
                    bal_live = chk.get("balance", 0)
                    cred_live = chk.get("credit", 0)
                    def_live = abs(bal_live)
                    if bal_live >= -200 or cred_live >= def_live * 0.5 or cred_live >= def_live:
                        a["status"] = "eligible"
                    else:
                        a["status"] = "credit_low"'''

if old2 in s:
    s = s.replace(old2, new2)
    print("Live flat-check eligibility updated with 3 rules")
else:
    print("Live check block not matched - showing:")
    i = s.find('not chk.get("flat"')
    print(s[i:i+300])

open(p, "w", encoding="utf-8").write(s)
import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
