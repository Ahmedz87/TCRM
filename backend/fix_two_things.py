p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# 1. Remove the 🔗 symbol next to the network score
s = s.replace(">🔗 {score}/10</span>", ">{score}/10</span>")

# 2. Remove the "NO DEPOSIT" / 🔥 badge next to lead names
import re
# Remove the whole registered_no_deposit badge block
pattern = re.compile(
    r"\{l\.match_badge === 'registered_no_deposit' && \(.*?\)\}",
    re.DOTALL
)
new_s, n = pattern.subn("", s)
if n > 0:
    s = new_s
    print(f"Removed {n} NO DEPOSIT badge block(s)")
else:
    print("NO DEPOSIT badge block not found - showing context:")
    i = s.find("registered_no_deposit")
    if i>0: print(repr(s[i-60:i+200]))

open(p, "w", encoding="utf-8").write(s)
print("🔗 removed:", "🔗 {score}" not in s)
print("NO DEPOSIT badge gone:", "🔥" not in s or "registered_no_deposit" not in s)
