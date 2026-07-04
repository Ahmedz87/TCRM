import urllib.request, json
token = open("_token.txt").read().strip()

# Search the full response for ANY client with lead_badge populated
url = "http://localhost:8000/clients?sort=score&page=1&page_size=100"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
data = json.loads(urllib.request.urlopen(req, timeout=15).read())
clients = data.get("clients", data.get("data", []))
print(f"Checking {len(clients)} clients...")
print("Keys in first client:", list(clients[0].keys())[:40] if clients else "none")

# Is lead_badge anywhere?
has_key = any("lead_badge" in c for c in clients)
print(f"\nAny client has lead_badge key: {has_key}")

# Check the recapture login #564875 directly (we know it's recapture in DB)
found = [c for c in clients if str(c.get("login")) == "564875"]
print(f"Client #564875 in this page: {len(found)>0}")
