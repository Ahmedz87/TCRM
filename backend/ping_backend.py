import urllib.request
try:
    urllib.request.urlopen("http://localhost:8000/docs", timeout=5)
    print("Backend is UP")
except Exception as e:
    print(f"Backend DOWN or hanging: {e}")
