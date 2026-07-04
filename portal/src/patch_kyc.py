import re
p = "Kyc.tsx"
s = open(p, encoding="utf-8").read()
old = "  if (status === \x27verified\x27) return null;\n  const inReview = status === \x27pending\x27;"
new = "  if (status === \x27verified\x27) return null;\n  const inReview = status === \x27pending_review\x27 || status === \x27in_review\x27 || status === \x27submitted\x27;"
if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Kyc.tsx patched - Verify now button will show for pending clients")
else:
    print("PATTERN NOT FOUND - current line:")
    i = s.find("const inReview")
    print(repr(s[i:i+80]))
