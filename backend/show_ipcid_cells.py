p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()
# Find the IP cell - search backward from ip_count to the <td that opens it
i = s.find("l.ip_count")
# back up to find the <td that starts the IP cell
start = s.rfind("<td", 0, i)
# find end: after CID cell closes, before Score cell. Score cell has 'Priority score' or score circle
score_marker = s.find("Priority score", i)
if score_marker < 0:
    score_marker = s.find("{l.score||0}", i)
# the </td> just before the Score <td>
score_td = s.rfind("<td", 0, score_marker)
print("=== IP + CID cells (to be replaced) ===")
print(s[start:score_td])
print("=== END (next is Score cell) ===")
