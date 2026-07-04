p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# 1. Header: remove IP and CID, add Network
s = s.replace("'KYC','IP','CID','Score','Actions'", "'KYC','Network','Score','Actions'")

# 2. Add networkHover state near the top of the component (after another useState)
if "const [networkHover" not in s:
    s = s.replace(
        "const [selected, setSelected]",
        "const [networkHover, setNetworkHover] = useState<number|null>(null);\n  const [selected, setSelected]",
        1
    )

print("Header + state done. Now need to replace IP/CID cells - showing them:")
# Find the IP cell start
i = s.find("l.ip_count")
print("IP/CID cell area found at:", i>0)
open(p, "w", encoding="utf-8").write(s)
