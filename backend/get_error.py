import urllib.request, json
token = open("_token.txt").read().strip()
url = "http://localhost:8000/clients?sort=score&page=1&page_size=5"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    print("OK")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}:")
    print(body[:1500])
