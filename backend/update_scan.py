p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Replace the scan function's DB query + enrichment to add network + abuse
old_scan = '''    rows = db.execute(text("""
        SELECT login, name, balance, no_auto_cover FROM clients
        WHERE balance < 0 AND platform = :p ORDER BY balance ASC
    """), {"p": platform}).fetchall()
    mgr = _get_mt5() if platform == "MT5" else None
    out = []
    for r in rows:
        login, name, db_bal, no_cover = r[0], r[1], float(r[2] or 0), r[3]
        item = {"login": login, "name": name or "", "balance": db_bal,
                "no_auto_cover": bool(no_cover), "status": "unknown",
                "credit": 0, "deficit": abs(db_bal), "cover_amount": 0, "flat": None}
        if mgr:
            ev = _eval_account(mgr, login)
            if ev:
                item.update(ev)
                item["no_auto_cover"] = bool(no_cover)
            else:
                item["status"] = "not_negative_now"
        out.append(item)
    if mgr: mgr.Disconnect()
    return {"platform": platform, "accounts": out,
            "eligible": sum(1 for a in out if a["status"]=="eligible" and not a["no_auto_cover"])}'''

new_scan = '''    rows = db.execute(text("""
        SELECT login, name, balance, no_auto_cover,
               COALESCE(network_score,0), COALESCE(is_flagged,FALSE)
        FROM clients
        WHERE balance < 0 AND platform = :p ORDER BY balance ASC
    """), {"p": platform}).fetchall()

    # Build abuse lookup: which logins appear in abuse_cases
    abuse_logins = set()
    try:
        ar = db.execute(text("SELECT DISTINCT login_a FROM abuse_cases WHERE status != 'dismissed'")).fetchall()
        abuse_logins = {x[0] for x in ar if x[0]}
        ar2 = db.execute(text("SELECT DISTINCT login_b FROM abuse_cases WHERE status != 'dismissed'")).fetchall()
        abuse_logins |= {x[0] for x in ar2 if x[0]}
    except Exception:
        pass

    mgr = _get_mt5() if platform == "MT5" else None
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
    if mgr: mgr.Disconnect()

    # Sort: eligible first (by deficit desc), then everything else (credit_low) at bottom by balance
    def sort_key(a):
        tier = 0 if a["status"] == "eligible" else 1
        return (tier, -abs(a["balance"]))
    out.sort(key=sort_key)

    return {"platform": platform, "accounts": out,
            "eligible": sum(1 for a in out if a["status"]=="eligible" and not a["no_auto_cover"])}'''

if old_scan in s:
    s = s.replace(old_scan, new_scan)
    print("Scan endpoint updated with network + abuse + sorting")
else:
    print("Old scan block not found exactly - check formatting")

open(p, "w", encoding="utf-8").write(s)
print("Verify:", "in_abuse" in s)
