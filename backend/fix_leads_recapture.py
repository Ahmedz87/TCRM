p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# Remove the word RECAPTURE, keep only the symbol
s = s.replace(">\u267B RECAPTURE", ">\u267B")

open(p, "w", encoding="utf-8").write(s)
print("RECAPTURE word removed:", "\u267B RECAPTURE" not in s)
print("Symbol still present:", "\u267B" in s)
