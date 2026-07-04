import urllib.request, json
try:
    r = json.loads(urllib.request.urlopen(urllib.request.Request("http://localhost:5001/mt4/cover/408104", method="POST"), timeout=20).read())
    print("DRY RUN:", json.dumps(r, indent=2))
except urllib.error.HTTPError as e:
    if e.code == 404:
        print("404 - cover endpoint NOT loaded. MT4 bridge needs restart.")
    else:
        print(f"HTTP {e.code}")
