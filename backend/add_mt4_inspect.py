p = r"C:\broker-crm\backend\bridge_mt4.py"
s = open(p, encoding="utf-8").read()

if "from flask import" not in s:
    # Add Flask import after the ctypes imports (after the first import block)
    s = s.replace(
        "import ctypes\nimport ctypes.wintypes as wt",
        "import ctypes\nimport ctypes.wintypes as wt\nimport threading\nfrom flask import Flask, jsonify\n\napp = Flask(__name__)",
        1
    )

# Add inspect endpoint + new __main__ before the existing __main__
if "/mt4/inspect" not in s:
    endpoints = '''

# ─────────── HTTP ENDPOINTS (read-only for now) ───────────
def _get_user_record(login):
    """Read one user's balance/credit via AdmUsersRequest, filtered to login."""
    for u in get_all_users():
        if u["login"] == login:
            return u
    return None

@app.route("/mt4/inspect/<int:login>", methods=["GET"])
def mt4_inspect(login):
    """Read-only: balance, credit, open positions, floating PnL for a login."""
    try:
        u = _get_user_record(login)
        if not u:
            return jsonify({"login": login, "error": "user not found"}), 404
        bal = u["balance"]
        cred = u["credit"]
        # Open trades for this login + floating PnL
        try:
            all_trades = get_open_trades()
        except Exception:
            all_trades = []
        mine = [t for t in all_trades if t.get("login") == login]
        # Only count market trades (cmd 0=buy,1=sell) as positions, not balance ops
        positions = [t for t in mine if t.get("cmd") in (0, 1)]
        floating = sum(float(t.get("profit", 0)) for t in positions)
        return jsonify({
            "login": login, "balance": bal, "credit": cred,
            "positions": len(positions), "floating_pnl": round(floating, 2)
        })
    except Exception as e:
        return jsonify({"login": login, "error": str(e)}), 500

@app.route("/mt4/health", methods=["GET"])
def mt4_health():
    return jsonify({"status": "ok", "service": "mt4_bridge"})

'''
    # Insert endpoints + replace the __main__ to start Flask + background sync
    old_main = '''if __name__ == "__main__":
    sync_loop()'''
    new_main = endpoints + '''
if __name__ == "__main__":
    # Start sync in background so the web server is available immediately
    threading.Thread(target=sync_loop, daemon=True).start()
    log.info("MT4 bridge web server starting on http://0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)'''
    s = s.replace(old_main, new_main)
    print("Added Flask + inspect endpoint + web server (port 5001)")

open(p, "w", encoding="utf-8").write(s)
import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
