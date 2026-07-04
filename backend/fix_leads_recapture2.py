p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# The badge text is on its own line: "\n                        ♻ RECAPTURE\n"
old = "}}>\n                        \u267B RECAPTURE\n"
new = "}}>\u267B"
if old in s:
    s = s.replace(old, new)
    print("Removed (exact match)")
else:
    # fallback: just replace the text portion
    s = s.replace("\u267B RECAPTURE", "\u267B")
    print("Removed (fallback)")

open(p, "w", encoding="utf-8").write(s)
print("RECAPTURE gone:", "RECAPTURE" not in s)
