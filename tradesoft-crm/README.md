# TradeSoft CRM — Standalone Copy (read-only archive)

A self-contained rebuild of the legacy **Workice / TradeSoft ("FXOD")** broker CRM,
served from a **decoupled copy** of its data. It has **no connection** to the live
`broker_crm` system, the MT bridges, or the production site — it only reads its own
private database.

It reproduces the core TradeSoft screens (Dashboard, Clients, Leads, Trading Accounts,
Transactions, Users & Staff) over the real archived records.

---

## What it is built from

The original TradeSoft is a Laravel application (its source is in `../Old CRM Code`).
We did **not** clone that PHP codebase — instead this is a faithful, modern rebuild in
the same stack as your main CRM (**FastAPI + React**), reading the data that was
mirrored out of TradeSoft's MySQL. The legacy export gave us 5 denormalized views,
which are copied here as real tables:

| Table (this DB) | Rows | Source |
|---|---|---|
| `fx_clients_view` | 64,453 | clients (people) |
| `fx_leads_view` | 202,061 | leads |
| `fx_accounts_view` | 264,385 | MT trading accounts |
| `fx_transactions_view` | 621,711 | deposits / withdrawals / transfers |
| `fx_users_view` | 190,160 | user / IB / staff records |

## Architecture

```
tradesoft-crm/
├── backend/            FastAPI (read-only API + serves the built SPA)
│   ├── main.py         entity list/detail/search + dashboard stats
│   ├── db.py           connection pool to the tradesoft_crm database
│   └── venv/           its own Python venv (FastAPI, uvicorn, psycopg2)
├── frontend/           React + Vite SPA (Workice-style purple theme)
│   ├── src/            Dashboard, ListPage, Detail, Layout, config
│   └── dist/           production build (served by the backend)
└── start.ps1           one-command launcher
```

- **Database:** a dedicated PostgreSQL DB **`tradesoft_crm`** on the local server
  (`postgresql://postgres:YOUR_PASSWORD@localhost:5432/tradesoft_crm`). It is a one-time copy of
  `broker_crm.tradesoft_old`, so nothing here touches the live broker database.

## Run it

It runs automatically via a Windows Scheduled Task **`TradeSoftCRM`** and is reachable at
**http://127.0.0.1:8090** in a browser **on the server** (RDP desktop).

- The task runs `run_server.cmd` as **`Administrator` (interactive session)**, triggered **at
  logon**. `run_server.cmd` launches uvicorn on :8090 in a **self-restart loop** (if uvicorn
  ever exits it relaunches after 3s).
- ⚠️ It is NOT run as SYSTEM **on purpose**: under session-0/SYSTEM the **uvicorn process hangs
  on startup and never binds** (verified — the DB connects fine, uvicorn just never starts; the
  same session-0 quirk this box has with the MT manager). So, like `BrokerCRM-Bridges`, it runs
  in the logged-on Administrator session.

  **Uptime behaviour:**
  - Survives RDP **disconnect** (a disconnected session keeps its processes running).
  - Survives uvicorn **crashes** (self-restart loop + task restart-on-failure).
  - A full **log off** stops it; it **auto-starts again on next logon** (and after a reboot,
    once an admin logs in via RDP — which is when you'd open the browser anyway).
- Bound to **localhost only** (real client data, no login). For remote access, front it with
  nginx + auth.

Manual control:
```powershell
Start-ScheduledTask -TaskName TradeSoftCRM     # start
Stop-ScheduledTask  -TaskName TradeSoftCRM     # stop
.\start.ps1                                    # or run in the foreground (logs to console)
```
Startup/run log: `backend\task.log`.

### Rebuild the frontend after UI changes

```powershell
cd C:\Broker-crm\tradesoft-crm\frontend
$env:CI="false"; npm run build
```

### Dev mode (hot reload)

```powershell
# terminal 1 — backend API
cd backend; .\venv\Scripts\python.exe -m uvicorn main:app --port 8090
# terminal 2 — Vite dev server (proxies /api to :8090)
cd frontend; npm run dev   # http://localhost:5190
```

## Refresh the data (auto, hourly)

The copy is kept current by **`backend/refresh.py`**, which pulls the latest data
**directly from the legacy TradeSoft MySQL views** into `tradesoft_crm` and re-derives
contact enrichment. Each table is loaded into a `<t>__new` staging table and **swapped in
atomically**, so the running CRM always serves a complete table — never an empty or
half-loaded one. A full refresh is ~1.35M rows in ~3–4 minutes.

- **Scheduled task `TradeSoftCRM-Refresh`** runs it **every 60 minutes** (as SYSTEM —
  refresh.py is pure DB/network work and does NOT hit the uvicorn session-0 issue), plus at
  startup. `IgnoreNew` prevents overlap if a run is slow; 30-min execution cap.
- Manual run: `python refresh.py`   ·   log: `backend\refresh.log` (appends each run).

Source = the same 5 contact-stripped views as before (so still no email/phone *values* from
the source — those are recovered from broker_crm by MT login in the enrichment step).

## Notes & data caveats

- **Read-only.** There is no create/update/delete — this is an archive viewer.
- **Email/phone recovered by login match.** The legacy export stripped contact *values*
  (only verified-flags survived). We recover them from the live `broker_crm` by joining on
  the MT trading-login number (`backend/enrich_contacts.py` → `contact_enrichment` table):
  **~60,700 people regain an email and ~59,700 a phone** (essentially all funded clients;
  leads with no MT account stay blank). Re-run `python enrich_contacts.py` to refresh.
  This is the only step that reads broker_crm — the running app never does.
- **Credentials hidden.** Password hashes, tokens and OTP secrets present in the raw
  user mirror are stripped by the API and never sent to the browser.
- **Money figures exclude system entries.** ~1,100 legacy `payment_method = 0`
  balance-fix rows carry a sentinel `99,999,999.99` amount; the dashboard excludes them
  so deposit/withdrawal totals are realistic (~$124.5M deposits / ~$61.8M withdrawals).
- **Soft-deletes hidden.** Lists show live records (`deleted_at IS NULL`) by default.
```
