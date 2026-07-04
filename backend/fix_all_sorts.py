p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix all sort_col definitions to use aggregate-safe expressions (query is GROUPED BY ck)
replacements = [
    ('sort_col = "city ASC"', 'sort_col = "MIN(c.city) ASC"'),
    ('sort_col = "COALESCE(call_score,0) DESC, balance DESC"', 'sort_col = "COALESCE(MAX(c.call_score),0) DESC, SUM(c.balance) DESC"'),
    ('sort_col = "balance DESC"', 'sort_col = "SUM(c.balance) DESC"'),
    ('sort_col = "name ASC"', 'sort_col = "MIN(c.name) ASC"'),
    ('sort_col = "login DESC"', 'sort_col = "MIN(c.login) DESC"'),
    ('sort_col = "first_deposit_at DESC NULLS LAST"', 'sort_col = "MAX(c.first_deposit_at) DESC NULLS LAST"'),
    ('sort_col = "total_deposit DESC"', 'sort_col = "SUM(COALESCE(c.total_deposits,0)) DESC"'),
    ('sort_col = "equity DESC"', 'sort_col = "SUM(c.equity) DESC"'),
    ('sort_col = "total_withdraw DESC"', 'sort_col = "SUM(COALESCE(c.total_withdrawals,0)) DESC"'),
    ('sort_col = "country ASC"', 'sort_col = "MIN(c.country) ASC"'),
]
for old, new in replacements:
    if old in s:
        s = s.replace(old, new)
        print(f"Fixed: {old[:45]}")

open(p, "w", encoding="utf-8").write(s)
print("\nSaved. Now showing all sort_col defs:")
import re
for m in re.finditer(r'sort_col = "[^"]+"', s):
    print("  ", m.group(0))
