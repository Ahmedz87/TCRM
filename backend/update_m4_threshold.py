p = r"C:\broker-crm\backend\bridge.py"
s = open(p, encoding="utf-8").read()

old = '''        if n_pos > 0:
            # Model 4: only cover if floating PnL is also negative (losing open trades)
            floating = sum(float(p.Profit) for p in pos)
            if floating >= 0:
                return jsonify({"login": login, "status": "has_positions_positive_pnl"})
            # else: negative balance + negative PnL -> proceed to cover (safe: balance added first)'''

new = '''        if n_pos > 0:
            # Model 4: cover if floating PnL < $10 (negative or small positive). Skip if PnL >= $10.
            floating = sum(float(p.Profit) for p in pos)
            if floating >= 10:
                return jsonify({"login": login, "status": "has_positions_positive_pnl", "floating_pnl": floating})
            # else: PnL < 10 -> proceed to cover (safe: balance added first)'''

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Bridge Model 4 threshold updated to $10")
else:
    print("Block not matched - showing current:")
    i = s.find("Model 4")
    print(s[i-60:i+300])

import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
