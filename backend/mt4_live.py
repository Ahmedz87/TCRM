import urllib.request, json
print("LIVE cover on #408104 (this WILL move money)...")
r = json.loads(urllib.request.urlopen(urllib.request.Request("http://localhost:5001/mt4/cover/408104?live=1", method="POST"), timeout=30).read())
print(json.dumps(r, indent=2))
