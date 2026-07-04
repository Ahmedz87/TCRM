p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Replace the simple abuse_logins set with a detailed lookup (type + evidence)
old_abuse = '''    # Build abuse lookup: which logins appear in abuse_cases
    abuse_logins = set()
    try:
        ar = db.execute(text("SELECT DISTINCT login_a FROM abuse_cases WHERE status != 'dismissed'")).fetchall()
        abuse_logins = {x[0] for x in ar if x[0]}
        ar2 = db.execute(text("SELECT DISTINCT login_b FROM abuse_cases WHERE status != 'dismissed'")).fetchall()
        abuse_logins |= {x[0] for x in ar2 if x[0]}
    except Exception:
        pass'''

new_abuse = '''    # Build abuse lookup with type + reason per login
    abuse_map = {}
    try:
        ar = db.execute(text("""
            SELECT login_a, login_b, abuse_type, severity, risk_score, evidence
            FROM abuse_cases WHERE status != 'dismissed'
        """)).fetchall()
        for row in ar:
            la, lb, atype, sev, risk, evid = row
            info = {"type": atype, "severity": sev, "risk": int(risk or 0), "reason": evid or ""}
            for lg in (la, lb):
                if lg and lg not in abuse_map:
                    abuse_map[lg] = info
    except Exception:
        pass
    abuse_logins = set(abuse_map.keys())'''

s = s.replace(old_abuse, new_abuse)

# Add abuse detail to each item
s = s.replace(
    '"in_abuse": login in abuse_logins}',
    '"in_abuse": login in abuse_logins,\n                "abuse_info": abuse_map.get(login)}'
)
# also the second occurrence in the mgr branch (now removed in fast scan, but safe)
s = s.replace(
    'item["in_abuse"] = login in abuse_logins',
    'item["in_abuse"] = login in abuse_logins\n                item["abuse_info"] = abuse_map.get(login)'
)

open(p, "w", encoding="utf-8").write(s)
print("Abuse detail added to scan")
print("Verify abuse_map:", "abuse_map" in s)
print("Verify abuse_info:", "abuse_info" in s)
