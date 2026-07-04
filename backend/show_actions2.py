p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
# Find the end of CID cell -> start of Actions cell
i = s.find("'✅ New device'")
# search forward for the next </td> then the Actions <td>
j = s.find("</td>", i)
print("=== From CID close to next cell ===")
print(repr(s[j:j+400]))
