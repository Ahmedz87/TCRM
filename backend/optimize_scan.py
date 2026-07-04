p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Make scan use DB credit data (fast) instead of live position checks per account.
# We add a 'credit' column read from DB, and defer the flat-check to cover time.
# Replace the live _eval_account loop with a fast DB-based version.

old = '''    mgr = _get_mt5() if platform == "MT5" else None
    out = []
    for r in rows:
        login, name, db_bal, no_cover = r[0], r[1], float(r[2] or 0), r[3]
        net_score, flagged = int(r[4] or 0), bool(r[5])
        item = {"login": login, "name": name or "", "balance": db_bal,
                "no_auto_cover": bool(no_cover), "status": "unknown",
                "credit": 0, "deficit": abs(db_bal), "cover_amount": 0, "flat": None,
                "network_score": net_score, "is_flagged": flagged,
                "in_abuse": login in abuse_logins}
        if mgr:
            ev = _eval_account(mgr, login)
            if ev:
                item.update(ev)
                item["no_auto_cover"] = bool(no_cover)
                item["network_score"] = net_score
                item["is_flagged"] = flagged
                item["in_abuse"] = login in abuse_logins
            else:
                item["status"] = "not_negative_now"
        out.append(item)
    if mgr: mgr.Disconnect()'''

new = '''    # Pull credit from DB (fast) - clients table has credit column
    out = []
    for r in rows:
        login, name, db_bal, no_cover = r[0], r[1], float(r[2] or 0), r[3]
        net_score, flagged = int(r[4] or 0), bool(r[5])
        credit = float(r[6] or 0) if len(r) > 6 else 0
        deficit = abs(db_bal)
        # Status from DB data only (no live position check here - too slow)
        if credit >= deficit:
            status = "eligible"   # provisional - verified flat at cover time
        else:
            status = "credit_low"
        item = {"login": login, "name": name or "", "balance": db_bal,
                "no_auto_cover": bool(no_cover), "status": status,
                "credit": credit, "deficit": deficit,
                "cover_amount": min(deficit, credit), "flat": None,
                "network_score": net_score, "is_flagged": flagged,
                "in_abuse": login in abuse_logins}
        out.append(item)'''

s = s.replace(old, new)

# Update the SELECT to also pull credit from DB
s = s.replace(
    """SELECT login, name, balance, no_auto_cover,
               COALESCE(network_score,0), COALESCE(is_flagged,FALSE)
        FROM clients""",
    """SELECT login, name, balance, no_auto_cover,
               COALESCE(network_score,0), COALESCE(is_flagged,FALSE),
               COALESCE(credit,0)
        FROM clients"""
)

open(p, "w", encoding="utf-8").write(s)
print("Scan optimized to use DB data (fast)")
print("Verify fast scan:", "verified flat at cover time" in s)
print("Credit in SELECT:", "COALESCE(credit,0)" in s)
