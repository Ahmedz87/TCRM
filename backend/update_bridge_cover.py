p = r"C:\broker-crm\backend\bridge.py"
s = open(p, encoding="utf-8").read()

# Replace the cover logic to: balance always to 0, take all available credit (capped at deficit)
old = '''        if cred < deficit:
            return jsonify({"login": login, "status": "credit_low", "credit": cred, "deficit": deficit})
        # Two-step cover
        mgr.DealerBalance(login, deficit, 5, "Negative balance payoff")
        mgr.DealerBalance(login, -deficit, 3, "Credit Out")'''

new = '''        # Cover: balance always to 0; take whatever credit exists (capped at deficit)
        credit_to_take = min(cred, deficit) if cred > 0 else 0
        mgr.DealerBalance(login, deficit, 5, "Negative balance payoff")
        if credit_to_take > 0:
            mgr.DealerBalance(login, -credit_to_take, 3, "Credit Out")'''

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Bridge cover updated: balance->0, take available credit")
else:
    print("Cover block not matched - showing current:")
    i = s.find("def neg_cover")
    print(s[i:i+600])

import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
