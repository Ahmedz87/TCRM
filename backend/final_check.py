import urllib.request, json
token = open("_token.txt").read().strip()
url = "http://localhost:8000/clients?sort=score&page=1&page_size=15"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
data = json.loads(urllib.request.urlopen(req, timeout=15).read())
clients = data.get("clients", data.get("data", []))
print(f"Top 12 clients (priority sort):\n")
for c in clients[:12]:
    badge = c.get("lead_badge") or "-"
    print(f"  #{c.get('login')} {(c.get('name') or '')[:20]:20} score={c.get('call_score')} badge={badge}")
recaps = [c for c in clients if c.get("lead_badge")=="recapture"]
print(f"\nRecapture clients in top 15: {len(recaps)}")
