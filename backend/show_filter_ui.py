p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# 1. Show where filters are sent to backend (the URLSearchParams area)
i = s.find("if (filterVerified)")
print("=== Filter send area ===")
print(s[i-60:i+120])

# 2. Show a sample filter dropdown JSX to match the style
j = s.find("filterStatus")
# find a <select that uses a filter
k = s.find("setFilterSource", j)
sel_start = s.rfind("<select", 0, k)
sel_end = s.find("</select>", k) + 9
print("\n=== Sample filter dropdown (source) ===")
print(s[sel_start:sel_end] if sel_start>0 else "not found")
