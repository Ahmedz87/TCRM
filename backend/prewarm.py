"""Pre-warm freshly restarted uvicorn instances so users never hit the ~20s cold start
(imports + DB pool + KPI caches). Called by restart_backend.ps1 after health checks.
Hits each instance DIRECTLY by port (nginx round-robin would warm one instance 3x)."""
import time, sys
import requests
from auth import create_access_token
from database import SessionLocal
from sqlalchemy import text

PORTS = [8000, 8001, 8002, 8003, 8004, 8005]
# Warm the DEFAULT variant each page actually opens with — not just the bare path. The
# Dashboard defaults to period=this_month, so warming only the all_time KPI left the most-
# opened page cold for every user (Jul 15). Keep this list == the on-load fetch of each page.
PATHS = [
    "/dashboard/kpis",
    "/dashboard/kpis?period=this_month",           # dashboard on-load default
    "/dashboard/kpis?period=today",
    # the Dashboard fires 5 calls on mount — warm ALL of them, not just kpis, or the page
    # "loads" until the slowest cold one returns (Jul 15)
    "/dashboard/trends?period=this_month",
    "/dashboard/leaderboard?period=this_month",
    "/dashboard/funnel?period=this_month",
    "/dashboard/compare?granularity=month",
    "/transactions?page=1&page_size=20&tx_type=deposit",
    "/transactions?page=1&page_size=20&tx_type=withdrawal",
    # match the EXACT query the Clients page sends on load (archived+period+sort), or the
    # cache key never matches and every open recomputes the all_time aggregation (Jul 15)
    "/clients?page=1&page_size=50&archived=active&period=all_time&sort=score",
    "/clients?page=1&page_size=50",
    "/leads?page=1&page_size=50",
    # Same exact-match rule as /clients above: get_ibs' cache key includes EVERY param
    # (period/sort/direction/search/page/page_size), so "/ibs?page=1&page_size=25" warmed a key the
    # UI never asks for and the IB Admin list ate a ~25s cold build on every first open (Jul 16).
    # This is the exact query IBAdmin.tsx issues on load — keep in sync with its defaults.
    "/ibs?page=1&page_size=20&sort=volume&direction=desc&search=&period=all_time",
    "/agents",              # Sales Agents default view
    "/agents?period=this_month",   # the on-load default — keep instant
    "/agents?period=today",
    "/agents?period=this_week",
    "/agents?period=last_month",
    "/markups/others",             # Markup page (now reads the rollup — cheap, keep warm)
    "/markups/crosscheck",
]

def main():
    # An admin token resolves to the 'all' data scope — and the heavy list caches are now keyed
    # by SCOPE, not user id (clients_router), so warming as admin warms the SAME entry every
    # all-access user (admin/backoffice/customer_care/director/...) reads. Warm every instance
    # directly by port so all are hot regardless of which one a user sticks to.
    db = SessionLocal()
    email = db.execute(text(
        "SELECT email FROM users WHERE role IN ('admin','super_admin') ORDER BY id LIMIT 1"
    )).scalar()
    db.close()
    H = {"Authorization": "Bearer " + create_access_token(data={"sub": email})}

    def warm(port, path, label=None):
        t0 = time.time()
        try:
            r = requests.get(f"http://127.0.0.1:{port}{path}", headers=H, timeout=120)
            print(f"warm :{port} {(label or path)[:40]:42} {r.status_code} {time.time()-t0:5.1f}s", flush=True)
            return r
        except Exception as e:
            print(f"warm :{port} {(label or path)[:40]:42} ERR {str(e)[:40]}", flush=True)
            return None

    # The IB Admin list lazily fetches /ibs/status-breakdown right after /ibs, and that cache key
    # includes the `agents` CSV of whichever IBs landed on the page — so it can't be a static PATH
    # (a fixed URL would warm a key the UI never asks for AND still pay the heavy deals scan).
    # Derive the real CSV from the list response, then warm the exact key the page will request.
    IB_LIST = "/ibs?page=1&page_size=20&sort=volume&direction=desc&search=&period=all_time"

    for port in PORTS:
        for path in PATHS:
            warm(port, path)
        try:
            r = requests.get(f"http://127.0.0.1:{port}{IB_LIST}", headers=H, timeout=120)
            agents = [str(x.get("agent_id")) for x in (r.json().get("ibs") or []) if x.get("agent_id")]
            if agents:
                warm(port, f"/ibs/status-breakdown?period=all_time&agents={','.join(agents)}",
                     label="/ibs/status-breakdown (page agents)")
        except Exception as e:
            print(f"warm :{port} /ibs/status-breakdown                   SKIP {str(e)[:40]}", flush=True)


if __name__ == "__main__":
    main()
