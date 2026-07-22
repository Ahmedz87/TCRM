import sys, io, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import urllib.request
from auth import create_access_token
import db_config
conn = db_config.connect(); cur = conn.cursor()
cur.execute("SELECT email FROM users WHERE role IN ('super_admin','admin') ORDER BY id LIMIT 1")
email = cur.fetchone()[0]; conn.close()
tok = create_access_token({"sub": email, "user_type": "staff"})
H = {"Authorization": f"Bearer {tok}"}

def t(url, port):
    u = f"http://127.0.0.1:{port}{url}"
    st = time.time()
    try:
        req = urllib.request.Request(u, headers=H)
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read(); code = r.status
    except Exception as e:
        return f"ERR {e}"
    return f"{time.time()-st:6.2f}s  ({code}, {len(body)}b)"

ENDPOINTS = [
    "/transactions?page=1&page_size=20&tx_type=deposit",
    "/transactions?page=1&page_size=20&tx_type=withdrawal",
    "/dashboard/kpis?period=this_month",
    "/clients?page=1&page_size=25",
]
for ep in ENDPOINTS:
    print(f"\n{ep}")
    for port in (8000, 8001, 8002, 8003):
        print(f"  :{port}  {t(ep, port)}")
