import urllib.request, json
d = json.loads(urllib.request.urlopen("http://localhost:5000/neg-cover/inspect/535979", timeout=20).read())
print(json.dumps(d, indent=2))
