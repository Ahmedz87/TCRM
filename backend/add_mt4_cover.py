p = r"C:\broker-crm\backend\bridge_mt4.py"
s = open(p, encoding="utf-8").read()

# Add V_ADM_BALANCE_FIX constant if not present
if "V_ADM_BALANCE_FIX" not in s:
    s = s.replace("V_ADM_TRADES_REQUEST = 80", "V_ADM_TRADES_REQUEST = 80\nV_ADM_BALANCE_FIX = 82")

# Add the cover endpoint (dry_run defaults TRUE - no money moves unless explicitly live)
if "/mt4/cover" not in s:
    cover_ep = '''
@app.route("/mt4/cover/<int:login>", methods=["POST"])
def mt4_cover(login):
    """Cover negative balance. DRY-RUN by default. Pass ?live=1 to execute.
    MT4 balance op: AdmBalanceFix(login, cmd, value, comment). cmd 6=BALANCE, 7=CREDIT."""
    from flask import request
    live = request.args.get("live") == "1"
    try:
        u = _get_user_record(login)
        if not u:
            return jsonify({"login": login, "error": "user not found"}), 404
        bal, cred = u["balance"], u["credit"]
        if bal >= 0:
            return jsonify({"login": login, "status": "not_negative", "balance": bal})
        # Flat / PnL check (Model 4)
        try:
            all_trades = get_open_trades()
        except Exception:
            all_trades = []
        positions = [t for t in all_trades if t.get("login")==login and t.get("cmd") in (0,1)]
        floating = sum(float(t.get("profit",0)) for t in positions)
        if len(positions) > 0 and floating >= 10:
            return jsonify({"login": login, "status": "has_positions_positive_pnl", "floating_pnl": round(floating,2)})
        deficit = abs(bal)
        credit_to_take = min(cred, deficit) if cred > 0 else 0
        plan = {"login": login, "balance_before": bal, "credit_before": cred,
                "deficit": deficit, "credit_to_take": credit_to_take,
                "balance_after_planned": 0.0, "credit_after_planned": round(cred - credit_to_take, 2)}
        if not live:
            plan["status"] = "dry_run"
            plan["note"] = "No money moved. Add ?live=1 to execute."
            return jsonify(plan)
        # LIVE: balance first (+deficit), then credit out (-credit_to_take)
        man = get_manager()
        rc1 = vcall(man, V_ADM_BALANCE_FIX, c_int,
                    [c_int, c_int, c_double, c_char_p],
                    login, 6, float(deficit), b"Negative balance payoff")
        rc2 = None
        if credit_to_take > 0:
            rc2 = vcall(man, V_ADM_BALANCE_FIX, c_int,
                        [c_int, c_int, c_double, c_char_p],
                        login, 7, float(-credit_to_take), b"Credit Out")
        # Re-read
        u2 = _get_user_record(login)
        plan["status"] = "covered"
        plan["rc_balance"] = rc1
        plan["rc_credit"] = rc2
        plan["balance_after"] = u2["balance"] if u2 else None
        plan["credit_after"] = u2["credit"] if u2 else None
        return jsonify(plan)
    except Exception as e:
        return jsonify({"login": login, "status": "error", "error": str(e)}), 500

'''
    s = s.replace('@app.route("/mt4/health"', cover_ep + '@app.route("/mt4/health"')
    print("Added /mt4/cover endpoint (dry-run default)")

open(p, "w", encoding="utf-8").write(s)
import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
