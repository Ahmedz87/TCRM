p = r"C:\broker-crm\backend\routers\clients_router.py"
s = open(p, encoding="utf-8").read()

# Fix ORDER BY: lead_badge -> MAX(c.lead_badge), call_score -> MAX(c.call_score), balance -> SUM(c.balance)
old = "CASE WHEN lead_badge='recapture' THEN 0 ELSE 1 END ASC, COALESCE(call_score,0) DESC, balance DESC"
new = "CASE WHEN MAX(c.lead_badge)='recapture' THEN 0 ELSE 1 END ASC, COALESCE(MAX(c.call_score),0) DESC, SUM(c.balance) DESC"
if old in s:
    s = s.replace(old, new)
    print("Fixed score-sort ORDER BY with aggregates")
else:
    print("Exact pattern not found, searching ORDER BY lines:")
    import re
    for m in re.finditer(r'ORDER BY[^\n]+', s):
        print("  ", m.group(0)[:120])

# Also the pin-recapture prefix may have been added to OTHER sorts too.
# Fix any bare 'lead_badge=' in ORDER BY context generally
s = s.replace("CASE WHEN lead_badge='recapture'", "CASE WHEN MAX(c.lead_badge)='recapture'")

open(p, "w", encoding="utf-8").write(s)
print("Saved.")

# Show all ORDER BY lines now
import re
print("\n=== ORDER BY lines now ===")
for m in re.finditer(r'ORDER BY[^\n]+', s):
    print("  ", m.group(0)[:130])
