p = r"C:\broker-crm\backend\loyalty_router.py"
s = open(p, encoding="utf-8").read()
c = []

# leaderboard query: drop c.country
if "SELECT la.client_id, c.name, c.country, la.tier, la.points_balance," in s:
    s = s.replace("SELECT la.client_id, c.name, c.country, la.tier, la.points_balance,",
                  "SELECT la.client_id, c.name, la.tier, la.points_balance,")
    c.append("lb-query")

# leaderboard response block: reindex
old_lb = """        "client_id": r[0], "name": r[1] or f"Client #{r[0]}", "country": r[2] or "",
        "tier": r[3], "points_balance": float(r[4] or 0), "lifetime_points": float(r[5] or 0),
        "current_streak": r[6], "best_streak": r[7],
        "last_trade_date": str(r[8]) if r[8] else None,"""
new_lb = """        "client_id": r[0], "name": r[1] or f"Client #{r[0]}", "country": "",
        "tier": r[2], "points_balance": float(r[3] or 0), "lifetime_points": float(r[4] or 0),
        "current_streak": r[5], "best_streak": r[6],
        "last_trade_date": str(r[7]) if r[7] else None,"""
if old_lb in s:
    s = s.replace(old_lb, new_lb); c.append("lb-resp")

# member query: drop c.country
if "SELECT la.client_id, c.name, c.country, la.tier, la.points_balance, la.lifetime_points," in s:
    s = s.replace("SELECT la.client_id, c.name, c.country, la.tier, la.points_balance, la.lifetime_points,",
                  "SELECT la.client_id, c.name, la.tier, la.points_balance, la.lifetime_points,")
    c.append("mem-query")

# member reindex
if "    tier = a[3]\n    streak = a[6]" in s:
    s = s.replace("    tier = a[3]\n    streak = a[6]", "    tier = a[2]\n    streak = a[5]"); c.append("mem-idx1")
if "    if a[8]:\n        days_inactive = (datetime.date.today() - a[8]).days" in s:
    s = s.replace("    if a[8]:\n        days_inactive = (datetime.date.today() - a[8]).days",
                  "    if a[7]:\n        days_inactive = (datetime.date.today() - a[7]).days"); c.append("mem-idx2")

old_mr = """        "client_id": a[0], "name": a[1] or f"Client #{a[0]}", "country": a[2] or "",
        "tier": tier, "tier_rate": TIER_RATE.get(tier, 4),
        "points_balance": float(a[4] or 0), "lifetime_points": float(a[5] or 0),
        "current_streak": streak, "best_streak": a[7],"""
new_mr = """        "client_id": a[0], "name": a[1] or f"Client #{a[0]}", "country": "",
        "tier": tier, "tier_rate": TIER_RATE.get(tier, 4),
        "points_balance": float(a[3] or 0), "lifetime_points": float(a[4] or 0),
        "current_streak": streak, "best_streak": a[6],"""
if old_mr in s:
    s = s.replace(old_mr, new_mr); c.append("mem-resp1")

old_mr2 = """        "last_trade_date": str(a[8]) if a[8] else None,
        "days_inactive": days_inactive, "demote_in_days": demote_in,
        "referral_code": a[9],"""
new_mr2 = """        "last_trade_date": str(a[7]) if a[7] else None,
        "days_inactive": days_inactive, "demote_in_days": demote_in,
        "referral_code": a[8],"""
if old_mr2 in s:
    s = s.replace(old_mr2, new_mr2); c.append("mem-resp2")

open(p,"w",encoding="utf-8").write(s)
import py_compile
py_compile.compile(p, doraise=True)
print("ROUTER patched:", c)
print("remaining c.country refs:", s.count("c.country"))
