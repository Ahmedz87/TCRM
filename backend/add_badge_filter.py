p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# 1. Add filterBadge state
if "filterBadge" not in s:
    s = s.replace(
        "const [filterVerified, setFilterVerified] = useState('');",
        "const [filterVerified, setFilterVerified] = useState('');\n  const [filterBadge,    setFilterBadge]    = useState('');"
    )
    print("1. State added")

# 2. Add to hasFilters check
s = s.replace(
    "!![filterStatus,filterSource,filterCountry,filterCity,filterAgent,filterPlatform,filterVerified].filter(Boolean).length",
    "!![filterStatus,filterSource,filterCountry,filterCity,filterAgent,filterPlatform,filterVerified,filterBadge].filter(Boolean).length"
)

# 3. Add Badge dropdown to the filter array (after Platform)
s = s.replace(
    "['Platform', filterPlatform, setFilterPlatform, ['','meta','google','manual'], ['All','Meta','Google','Manual']],",
    "['Platform', filterPlatform, setFilterPlatform, ['','meta','google','manual'], ['All','Meta','Google','Manual']],\n            ['Badge', filterBadge, setFilterBadge, ['','recapture','registered_no_deposit'], ['All','\u267B Recapture','\U0001F525 No Deposit']],"
)

# 4. Send filterBadge to backend
s = s.replace(
    "if (filterVerified) p.set('verified', filterVerified);",
    "if (filterVerified) p.set('verified', filterVerified);\n      if (filterBadge)    p.set('badge',    filterBadge);"
)

# 5. Add filterBadge to useEffect deps
s = s.replace(
    "filterPlatform, filterVerified]",
    "filterPlatform, filterVerified, filterBadge]"
)

open(p, "w", encoding="utf-8").write(s)
print("Badge filter added:")
print("  State:", "filterBadge" in s)
print("  Dropdown:", "🔥 No Deposit" in s or "No Deposit'" in s)
print("  Sent to backend:", "p.set('badge'" in s)
