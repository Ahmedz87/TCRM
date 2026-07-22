# TNFX Broker CRM — Project Context (Claude Code handoff)

Live forex-broker CRM on this Windows Server. Read before acting — the system is LIVE; be
careful with the DB and running processes.

> **This file is the always-loaded core. Deep/newer operational detail lives in the auto-memory
> (MEMORY.md + memory files). When CLAUDE.md and a memory disagree, the MEMORY is newer** (e.g.
> machine IPs, active router files, archive model have all been corrected there). Condensed
> 2026-07 to cut per-session tokens; full prior history is in git.

## What this is
CRM + risk/abuse-detection platform for forex broker TNFX. React frontend, FastAPI backend,
PostgreSQL DB, nginx serving the site over HTTPS. Pulls live data from MT4 + MT5 (London) and
Meta (Facebook) lead forms.

## Server / environment
- Windows Server 2025. Access via RDP as Administrator. (Machine map / current public IPs: see
  the `machine-map` memory — CLAUDE.md's old 199.247.5.96 is outdated.)
- Toolchain: Python 3.11.9 (MUST stay 3.11), Node v24.16.0, Git, PostgreSQL 16 client tools.
- PG bin not always on PATH: `$env:Path += ";C:\Program Files\PostgreSQL\16\bin"`
- Backend venv: `C:\broker-crm\backend\venv` (`.\venv\Scripts\Activate.ps1`).
- bcrypt MUST stay pinned at 4.0.1 (5.x breaks passlib).

## Project layout
- Backend: `C:\broker-crm\backend` (lowercase b). Frontend: `C:\Broker-crm\frontend` (Windows
  treats the path case-insensitively). API base in `src/api.ts` = `/api`. Build → `frontend\build`.
- Rebuild frontend: `cd C:\Broker-crm\frontend; $env:CI="false"; npm run build`. Bundle hash
  changes each build; if the UI looks stale tell the user to HARD-REFRESH (Ctrl+Shift+R).
- nginx: `C:\nginx` (v1.27.4). win-acme: `C:\wacs\wacs.exe`. Certs: `C:\certs`.
- **DUPLICATE ROUTERS**: some routers exist in BOTH `backend\` and `backend\routers\`. Always
  grep `main.py` to see which file it imports before editing. (Note: the `active-router-files`
  memory corrects CLAUDE's old claim — trading_accounts is mounted from the TOP-LEVEL file.)

## Database — broker_crm (remote, PostgreSQL 18)
- **Live DB is REMOTE: host=199.247.6.189 port=5432 dbname=broker_crm user=postgres** (password
  in gitignored `backend/.env` / `backend/db_config.py`). Dedicated Vultr Linux box, PG18, tuned.
  Firewalled to the CRM box only; SSH key-only. SSH: `ssh root@199.247.6.189`.
- **ALWAYS connect to 199.247.6.189, not localhost.** Old localhost PG16 is FROZEN (rollback
  fallback). All code repointed; `.env.bak-precutover` is the pre-cutover .env.
- **CLIENT-VERSION GOTCHA:** local `PostgreSQL\16\bin` tools CANNOT dump/restore the v18 server
  (client must be ≥ server). Use the new box's native PG18 tools via SSH. psql v16 can still run
  plain queries against v18 — only dump/restore breaks.
- **Backups:** daily 03:00 cron ON the new box → `/var/backups/broker_crm/*.dump` (PG18 -Fc, keep
  14) + Vultr VM snapshots. Old Windows backup task DISABLED (v16 can't dump v18). Restore drill
  verified — see `backup-restore-drill` memory.
- `database.py` Settings (pydantic) FORBIDS unknown .env keys → backend crashes on extras. Don't
  add META_* etc. to .env. SECRET_KEY is a strong random key; changing it logs everyone out.

### Tables (structural; counts drift, don't trust old numbers)
- leads (Meta: source=fb/ig channel, campaign_name=form name) + TradeSoft-imported leads.
- clients — raw accounts; the Clients LIST aggregates by **phone + platform** (MT4/MT5 stay
  separate). Depositor truth from deals, not the transactions table. See `client-totals-bug-guard`.
- deals — the biggest table (millions of rows; action: 0 buy 1 sell 2 balance 3 credit 6 bonus).
  MT4 trades from JOURNAL parsing; MT5 from the bridge.
- transactions — built from MT5 deals (build_transactions.py) + MT4 journal (fetch_mt4_balance.py,
  deal_id +4e9). tx_type deposit/withdrawal/internal_transfer/bonus_*; tx_date = real datetime.
- trading_accounts, account_identifiers (ip/cid/mqid — abuse data from the MT5 bridge), ibs
  (build_ibs.py from clients.agent), customers (CUS master — see customer-master memory).

## The site (LIVE) — HTTPS
- Domain: https://my1.tnfx.co. HTTPS via Let's Encrypt (win-acme, auto-renew). nginx redirects
  http→https and serves /.well-known/acme-challenge/ on :80 for renewals.
- Admin login admin@brokercrm.com (password in the manager; reset via reset_pw.py). Auth: POST
  /auth/login, OAuth2 form (username=email, password).
- SESSION INVALIDATION: JWTs carry `iat`; `users.tokens_valid_after` rejects older tokens. Changing
  a password sets it to NOW() → that user's old sessions log out. Manual force-logout:
  `UPDATE users SET tokens_valid_after=NOW() WHERE email=:e`.
- nginx: `C:\nginx\conf\nginx.conf` serves the build on 443 + proxies /api/ → backend :8000 (strips
  /api). Includes `security_headers.conf` (HSTS/X-Frame/nosniff/…; re-included inside
  `location = /index.html` because add_header doesn't merge) + a login-only rate limit (per-IP,
  429 on floods, only /*/auth/login keyed).
  - RELOAD GOTCHA 1: `nginx -s reload` FAILS unless run from `C:\nginx`:
    `cd C:\nginx; .\nginx.exe -t -p C:\nginx` then `.\nginx.exe -s reload -p C:\nginx`.
  - RELOAD GOTCHA 2: after a reboot nginx runs as SYSTEM, so an interactive `-s reload` gets
    `OpenEvent(...ngx_reload...) failed (5)`. Then either kill+restart from this session
    (`Get-Process nginx|Stop-Process -Force` then Start-Process the nginx.exe -p C:\nginx — ~1s
    :443 blip), reload from a SYSTEM shell, or wait for the next reboot. `nginx -t` works regardless.

## Processes & AUTO-START (survive reboot)
Auto-started via Task Scheduler (NOT NSSM). **KEY FINDING: the native MT manager DLL only works in
an INTERACTIVE desktop session — it silently hangs under SYSTEM/session-0.** Hence the hybrid:
- **BrokerCRM-Startup** (SYSTEM, at boot) → `start_core.ps1` → nginx + backend (uvicorn :8000) +
  meta_poller.py. Site comes up on reboot with no login.
- **BrokerCRM-Bridges** (Administrator, at logon) → `start_bridges.ps1` → bridge.py (MT5) +
  mt4_loop.py (MT4). Need the interactive session → start when the admin RDPs in.
- **BrokerCRM-DailyBackup** — superseded by the remote-box cron (see Backups).

The processes:
1. Backend: `cd C:\broker-crm\backend; .\venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 8000`
2. nginx: `cd C:\nginx; .\nginx.exe -p C:\nginx`
3. MT5 bridge: `python bridge.py` (Flask :5000; polls online sessions every 30s for IP/CID; writes
   trading_accounts + account_identifiers; connects MT5).
4. MT4 loop: `python mt4_loop.py` (every 60s → fetch_mt4_recent.py + sync MT4 clients; every ~10
   cycles → fetch_mt4_balance.py for new MT4 deposits).
5. Meta loop: `python meta_poller.py` (every 5 min → fetch_meta_leads.py).
- Only ONE MT4 connection at a time (manager login 1025). Stop mt4_loop before any MT4 diagnostic,
  and RESTART it after (won't come back until next admin logon). Kill-all:
  `Get-Process python | Stop-Process -Force; Get-Process nginx | Stop-Process -Force`.
- Note the venv "duplicate python processes" are launcher+child PAIRS (normal), not a respawner —
  see `venv-launcher-pairs` memory.
- Fully hands-off reboot for the bridges needs Windows auto-logon (stores the Administrator
  password) — DEFERRED by user; kept off the box.

## Data fetchers / key scripts (backend\)
- `fetch_meta_leads.py` — pulls all Meta lead forms (derives a PAGE token from the system-user
  token). Captures fb/ig channel, campaign_name, meta_created. De-duped on meta_lead_id.
  `--dry-run` / `--form ID`. GOTCHA: it forces stdout/stderr to UTF-8 — Arabic names under the
  cp1252 headless console once raised UnicodeEncodeError and silently killed the whole fetch. If
  leads stop, FIRST run `--dry-run`; it's almost never the token.
- `auto_match.py` — matches leads↔clients (email / last-9 phone); deposit truth = deals (action 2,
  profit>0); sets match_badge + blended lead SCORE. `--loop`.
- `build_transactions.py` (MT5 deals→transactions, idempotent), `fetch_mt4_balance.py` (MT4 journal
  deposits/withdrawals; run only when mt4_loop stopped), `build_ibs.py` (ibs from clients.agent).
- `bridge.py` (MT5), `bridge_mt4.py` (MT4 manager API).

## MT4 specifics
- On THIS server the Admin* APIs are limited: `AdmUsersRequest('*')` = 5,288 users (all already in
  clients); `AdmTradesRequest` returns 0. Pumping mode is NOT the trade source.
- The WORKING source for MT4 trades AND balance ops is the SERVER JOURNAL (vtable 96,
  LOG_TYPE_TRADES). `sync_trade_journal()` parses "close order"→trades; fetch_mt4_balance.py parses
  balance/credit lines→deposits/withdrawals. Journal has LIMITED retention (not full history).
- `mtmanapi64.dll` history: it went missing once (MT4 sync ran on a deleted-but-open handle);
  restored from the old box — see `mt4-dll-missing` memory. Spare at S3.

## Abuse detection engine (backend/abuse_engine.py — v3)
- THE engine is `abuse_engine.py` v3 (NOT abuse_detectors_v2.py). abuse_router.run_all_detectors()
  → `run_engine(db)`. CLI: `python run_abuse.py [--keep]` (~3-5 min). Frontend: Dashboard 'abuse'
  tab → AbuseDetection.tsx (ranked case list ↔ visual case-file drawer w/ signals, proof legs,
  money flow, network graph, one-click Freeze/Hold/Clear).
- Design: multi-signal, weighted; flag only if score≥50 AND ≥2 signals fire (sev ≥75 crit/≥60
  high/≥50 med). Structured evidence in `abuse_cases.evidence_json` + `kpis`; UI renders KPI cards.
- 7 detectors: **margin_partner** (🔥HOT — credit/bonus acct blows up while a linked acct wins the
  mirror within ±2min; broker_loss = the bonus/credit that funded it), **hedge_ratio**,
  **bonus_ring**, **bonus_cashout**, **chip_dump**, **swap_carry**, **toxic_arb**.
- Integration: `run_engine()` builds `abuse_account_flags` (login→worst open case). Surfaced in
  Transactions withdrawals (HOLD badge), Clients list, IB profile. POST /abuse/flags {logins}.
- SAFETY: detection does NOT auto-freeze. Desk freezes manually via POST /abuse/cases/{id}/action
  (sets clients.is_flagged + trading_accounts.is_active=FALSE for that case's logins only).
- DATA GOTCHAs: deals has no open_price (single-execution rows at `price`); is_islamic only on
  trading_accounts; deals.swap ~empty so overnight derived via FIFO pairing; 01:00-05:00 UTC is the
  BUSIEST window (Asian gold); all_logins is COMMA-sep (use parse_logins()).

## Other feature areas (concise — code is source of truth)
- **Meta CAPI** (`meta_capi_router.py`): sends lead-stage events to Meta dataset 1611045120042482.
  WRITE-ONLY (can't read quality back except in Meta Events Manager). POST /meta/lead/{id}/stage.
- **Sales Agents** (`agents_router.py`, prefix /agents): per-agent KPIs by period; new_clients via
  clients.reg_date. Real earning model now in `sales_commission.py` — see `sales-retention-commission`
  memory. IB Admin list columns are click-to-filter.
- **Unified login**: /auth/login tries `users` (staff) first, else falls back to `clients`
  (password_hash). Token carries user_type. Don't break the staff path.
- **Power Dialer** (`power_dialer_router.py`, prefix /dialer) + Yeastar PBX click-to-call. Needs
  dialer_sessions/queue/call_logs. Prioritises by clients.call_score. Dialer sessions must stay
  scope-gated (see `rbac-scoping-model`).
- **Client Portal** (separate CRA app `C:\Broker-crm\portal`, LIVE at /portal/; build with
  `npm install --legacy-peer-deps` then `$env:CI="false"; npm run build`). Backend
  `portal_router.py` (prefix /portal, own JWT scope="portal"). REAL login POST /portal/auth/login
  {identifier,password} (email/login/id, verifies clients.password_hash); dev-login DISABLED
  (ALLOW_DEV_LOGIN=False, keep it False on public). Brute-force lockout via `portal_login_attempts`.
  Money endpoints gated by `_assert_owns_login`. Client→accounts link is BY LOGIN (client_id is
  NULL everywhere) — `_client_logins()` resolves phone+platform siblings. Deposits/withdraws are
  SIMULATION. LESSON: any try/except around a query MUST db.rollback() or it poisons the session.
- **Copy Trading** (portal + admin): tables/seed in `seed_copy_trading.py`; real MT-linked providers
  in `promote_real_providers.py`; `copy_router.py` (portal_copy /portal/copy + admin_copy /copy);
  engine `copy_engine.py` + daemon `copy_loop.py` + `copy_features.py` (risk/vetting/fees/payouts).
  ALL DRY-RUN/SIMULATION behind `COPY_LIVE_ENABLED` (default FALSE) + bridge `COPY_BRIDGE_TRADING`
  + per-request dry + `COPY_TRADE_MAX_LOTS` cap. Live `/trade/open|close` routes are built in
  bridge.py but the live bridge hasn't been restarted to load them. Going live = supervised, one
  funded account first (steps in git history / copy_live_test.py).
- **Standalone TradeSoft CRM copy** (`C:\Broker-crm\tradesoft-crm`): read-only replica of the legacy
  Workice CRM — see `tradesoft-crm-standalone` memory.

## PowerShell / shell gotchas
- Inline `python -c "..."` mangles quotes → write a script file or use a here-string.
- Don't paste raw SQL into PowerShell; use psql -c or a psycopg2 script (creds via db_config.py).
- Bash tool = Git Bash (POSIX). Long-running stuff → run_in_background.

## SAFETY RULES (carry forward)
- Portal account-creation + deposits are SIMULATED. Do NOT wire real money / real MT provisioning
  until: data stable, real client auth, bridge UserAdd tested on ONE account first, payment APIs
  wired one at a time with webhook verification. Previous sessions correctly refused to shortcut this.
- Production DB with real client data. Prefer additive changes (ADD COLUMN IF NOT EXISTS, INSERT …
  ON CONFLICT). Back up before destructive ops. Don't TRUNCATE without explicit confirmation.
- clients.cid has FAKE sequential placeholders (C100000…) — real CID/IP detection reads
  account_identifiers, NOT clients.cid.
- When stopping mt4_loop for a diagnostic, RESTART it after (won't return until next admin logon).

## Test client logins (Ahmed Zaman): 1829, 2353, 4106, 4745, 5094
