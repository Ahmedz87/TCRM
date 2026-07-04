p = r"C:\broker-crm\backend\loyalty_router.py"
s = open(p, encoding="utf-8").read()
c = []

# leaderboard query: add la.best_tier
if "la.last_trade_date, la.best_tier" not in s:
    s = s.replace(
        "la.lifetime_points, la.current_streak, la.best_streak, la.last_trade_date\n",
        "la.lifetime_points, la.current_streak, la.best_streak, la.last_trade_date, la.best_tier\n")
    c.append("lb-query")

# leaderboard response: add best_tier r[8]
if '"best_tier": r[8]' not in s:
    s = s.replace(
        '        "last_trade_date": str(r[7]) if r[7] else None,\n    } for r in rows]}',
        '        "last_trade_date": str(r[7]) if r[7] else None,\n        "best_tier": r[8] if len(r)>8 else r[2],\n    } for r in rows]}')
    c.append("lb-resp")

# member query: add la.best_tier
if "la.last_trade_date, la.referral_code, la.best_tier" not in s:
    s = s.replace(
        "la.current_streak, la.best_streak, la.last_trade_date, la.referral_code\n",
        "la.current_streak, la.best_streak, la.last_trade_date, la.referral_code, la.best_tier\n")
    c.append("mem-query")

# member response: add best_tier a[9]
if '"best_tier": a[9]' not in s:
    s = s.replace(
        '        "referral_code": a[8],',
        '        "referral_code": a[8], "best_tier": a[9] if len(a)>9 else tier,')
    c.append("mem-resp")

open(p,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(p, doraise=True)
print("router best_tier patches:", c)
print("compiles OK, best_tier refs:", s.count("best_tier"))
