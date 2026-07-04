p = r"C:\broker-crm\backend\bridge.py"
s = open(p, encoding="utf-8").read()

if "/neg-cover/inspect" not in s:
    endpoint = '''

@app.route("/neg-cover/inspect/<int:login>", methods=["GET"])
def neg_inspect(login):
    """Read-only: show balance, credit, equity, floating PnL for diagnosis."""
    try:
        mgr = get_manager()
        acc = mgr.UserAccountGet(login)
        if not acc:
            return jsonify({"login": login, "error": "no account"}), 404
        out = {"login": login}
        for attr in ["Balance","Credit","Equity","Profit","Margin","MarginFree"]:
            try:
                out[attr] = float(getattr(acc, attr))
            except Exception:
                out[attr] = None
        pos = mgr.PositionGet(login)
        out["positions"] = 0 if pos is None else len(pos)
        if pos:
            out["floating_pnl"] = sum(float(p.Profit) for p in pos)
        else:
            out["floating_pnl"] = 0.0
        return jsonify(out)
    except Exception as e:
        return jsonify({"login": login, "error": str(e)}), 500
'''
    idx = s.rfind('if __name__')
    s = s[:idx] + endpoint + "\n" + s[idx:]
    open(p, "w", encoding="utf-8").write(s)
    print("Added /neg-cover/inspect endpoint to bridge")
else:
    print("Already added")
