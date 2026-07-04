import urllib.request, json, time

print("=== 1. Is bridge alive? ===")
try:
    d = json.loads(urllib.request.urlopen("http://localhost:5000/neg-cover/check/535979", timeout=15).read())
    print("Bridge OK:", json.dumps(d))
except Exception as e:
    print(f"BRIDGE DOWN/HANGING: {e}")
    print(">> The bridge needs restarting. Stop it (Ctrl+C) and run: python bridge.py")
    raise SystemExit

print("\n=== 2. Cover directly via bridge ===")
try:
    t0=time.time()
    r = json.loads(urllib.request.urlopen(urllib.request.Request("http://localhost:5000/neg-cover/cover/535979", method="POST"), timeout=60).read())
    print(f"Took {time.time()-t0:.1f}s: {json.dumps(r)}")
except Exception as e:
    print(f"Bridge cover FAILED: {e}")
