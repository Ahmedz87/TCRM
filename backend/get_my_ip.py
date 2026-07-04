import urllib.request

# Check multiple IP services to confirm
for url in [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
]:
    try:
        ip = urllib.request.urlopen(url, timeout=5).read().decode().strip()
        print(f"  {url}: {ip}")
    except Exception as e:
        print(f"  {url}: {e}")
