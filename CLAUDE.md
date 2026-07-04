# TNFX Broker CRM — Project Context (Claude Code handoff)

This file briefs you (Claude Code) on a live forex-broker CRM running on this
Windows Server. Read it fully before acting. The system is LIVE — be careful with
the database and the running processes.

## What this is
A CRM + risk/abuse-detection platform for forex broker TNFX. React frontend, FastAPI
backend, PostgreSQL DB, nginx serving the site on a real domain over HTTPS. Pulls live
data from MT4 + MT5 trading servers (London) and Meta (Facebook) lead forms.

## Server / environment
- Windows Server 2025, host TNFX-CRM, public IP 199.247.5.96, Frankfurt DE.
- Access via RDP as Administrator. Everything runs on THIS server.
- Toolchain: Python 3.11.9 (MUST stay 3.11), Node v24.16.0, Git, PostgreSQL 16.14.
- PostgreSQL bin not always on PATH. In a new shell: `$env:Path += ";C:\Program Files\PostgreSQL\16\bin"`
- Python venv: `C:\broker-crm\backend\venv` (activate: `.\venv\Scripts\Activate.ps1`)
- bcrypt MUST stay pinned at 4.0.1 (5.x breaks passlib).

## Project layout
- Backend: `C:\broker-crm\backend` (lowercase b)
- Frontend: `C:\Broker-crm\frontend` (capital B — Windows treats same path)
  - API base in `src/api.ts` = `/api` (relative). Build output: `frontend\build`.
  - Rebuild: `cd C:\Broker-crm\frontend; $env:CI="false"; npm run build`. The bundle hash
    changes each build (e.g. main.XXXX.js); index.html references it. After a rebuild the
    BROWSER often caches the old index.html → tell the user to HARD-REFRESH (Ctrl+Shift+R).
- nginx: `C:\nginx` (v1.27.4). win-acme (HTTPS): `C:\wacs\wacs.exe`. Certs: `C:\certs`.
- IMPORTANT — DUPLICATE ROUTERS: some routers exist in BOTH `backend\` and `backend\routers\`.
  `main.py` mounts the ones under `backend\routers\` for: auth, clients, neg_cover,
  notifications, settings, trading_accounts, ib. So the ACTIVE clients router is
  `backend\routers\clients_router.py` (NOT `backend\clients_router.py`). Other routers
  (leads_router, transactions_router, ib_router, network_router, meta_capi_router, etc.)
  live at `backend\` top level and are mounted from there. When editing, confirm which file
  main.py imports.

## Database — broker_crm (MIGRATED Jun 27 2026 to a dedicated box — PostgreSQL 18)
- **THE LIVE DB IS NOW REMOTE: host=199.247.6.189 port=5432 dbname=broker_crm user=postgres password=<in backend/.env / backend/db_config.py — NOT committed>**
  (dedicated Vultr Linux box, Frankfurt, 12 vCPU / 22GB / NVMe, PostgreSQL 18, tuned: shared_buffers 6GB,
  effective_cache_size 16GB). Firewalled so ONLY the CRM box 199.247.5.96 can reach 5432; SSH key-only
  (Administrator's id_ed25519); fail2ban on. SSH in from the CRM box: `ssh root@199.247.6.189`.
- **ALWAYS connect to 199.247.6.189, NOT localhost.** The old localhost PostgreSQL 16 is FROZEN (kept as a
  rollback fallback until the new box proves stable, then decommission). All app/bridge/script code was
  repointed (host="localhost"/DSN/getenv→199.247.6.189; .env too). `.env.bak-precutover` is the pre-cutover
  .env. ROLLBACK = revert the host edits + restart, old DB is intact & current as of the cutover.
- **CLIENT-VERSION GOTCHA:** the CRM box's `C:\Program Files\PostgreSQL\16\bin` tools (pg_dump/pg_restore/psql)
  are v16 and CANNOT dump/restore the v18 server (client must be ≥ server). Use the NEW box's native PG18
  tools (`ssh root@199.247.6.189 "sudo -u postgres pg_dump ..."`). psql v16 can still run plain queries
  against v18 fine — only dump/restore breaks.
- **Backups:** daily 03:00 cron ON the new box → `/var/backups/broker_crm/*.dump` (PG18 pg_dump -Fc, keep 14)
  + Vultr automatic VM snapshots. The old Windows `backup_db.ps1` + `BrokerCRM-DailyBackup` task are DISABLED
  (v16 can't dump v18).
- backend/.env DATABASE_URL=postgresql://postgres:<PASSWORD>@199.247.6.189:5432/broker_crm  (real value only in the gitignored .env / db_config.py)
- database.py Settings (pydantic BaseSettings) FORBIDS extra .env keys. Do NOT put META_*
  or other unknown keys in .env or the backend crashes ("Extra inputs are not permitted").
  Meta token is baked into the fetch scripts instead.
- SECRET_KEY in .env is now a strong 86-char random key (was the placeholder — hardened
  this session). Changing it logs everyone out (JWTs invalidate); they just re-login.

### Row counts (approx, live — Jun 2026)
- leads ~20,318 (Meta, 11 forms; source = per-lead channel facebook/instagram; campaign_name
  = form name). match badges: recapture 82, registered_no_deposit 492.
- clients 19,195 raw accounts → the Clients LIST aggregates by **phone + platform** = ~15,201
  unique rows (a person's multiple same-platform accounts merge; MT4 and MT5 stay separate).
  clients.platform: MT4 5,288, rest blank = MT5.
- deals ~4,019,241 (action: 0 buy, 1 sell, 2 balance/deposit-withdraw, 3 credit, 6 bonus).
  MT4 trades came from JOURNAL parsing (see MT4 notes), MT5 from the bridge.
- transactions 92,214 — built from MT5 deals (action 2/3/6) via build_transactions.py, PLUS
  MT4 deposits/withdrawals parsed from the MT4 journal via fetch_mt4_balance.py (MT4 rows use
  deal_id offset +4e9 to avoid collision). tx_type: deposit/withdrawal/internal_transfer/
  bonus_deposit/bonus_withdrawal. tx_date holds the REAL datetime.
- trading_accounts 19,175 (MT5 + MT4). account_identifiers 27,142 (ip/cid/mqid — live
  abuse-detection data from the MT5 bridge).
- ibs 1,027 — populated by build_ibs.py from clients.agent (the MT agent/IB login).

## The site (LIVE) — now HTTPS
- Domain: https://my1.tnfx.co  (DNS A record my1 -> 199.247.5.96)
- HTTPS via Let's Encrypt (win-acme). Cert: C:\certs\my1.tnfx.co-chain.pem + -key.pem.
  Auto-renews via a win-acme Task Scheduler entry. nginx redirects http->https and keeps
  /.well-known/acme-challenge/ served on :80 for renewals.
- Admin login: admin@brokercrm.com / <password redacted — see password manager; reset via reset_pw.py>. Other: admin@tnfx.co
  (different password). Auth: POST /auth/login, OAuth2 form (username=email,password).
- SESSION INVALIDATION (Jun 2026): JWTs carry `iat`; users.tokens_valid_after rejects any token
  issued before it (auth.get_current_user). Changing a password sets tokens_valid_after=NOW(), so
  ALL of that user's old sessions are logged out (per-user, not everyone — unlike SECRET_KEY rotation).
  Wired into: /auth/change-password (also returns a fresh token so the changer stays in), users_router
  password edit, and reset_pw.py. To force-logout a user manually:
  UPDATE users SET tokens_valid_after=NOW() WHERE email=:e.
- nginx config: C:\nginx\conf\nginx.conf (backups: nginx.conf.bak-*). Serves frontend build
  on 443 + proxies /api/ to backend :8000 (strips /api). 80 = redirect + ACME.
  GOTCHA: nginx -s reload FAILS unless run from C:\nginx:
    cd C:\nginx; .\nginx.exe -t -p C:\nginx   (test first)
    cd C:\nginx; .\nginx.exe -s reload -p C:\nginx

## The processes & AUTO-START (survive reboot)
Five processes run (each its own python/exe). They are now auto-started via Task Scheduler
(NOT NSSM). KEY FINDING: the native MT manager DLL only works in an INTERACTIVE desktop
session — it silently hangs under SYSTEM/session-0. So a hybrid is used:
- **BrokerCRM-Startup** (SYSTEM, at boot) -> `C:\broker-crm\start_core.ps1` -> nginx +
  backend (uvicorn :8000) + meta_poller.py. The SITE comes up on reboot with no login.
- **BrokerCRM-Bridges** (Administrator, at logon) -> `C:\broker-crm\start_bridges.ps1` ->
  bridge.py (MT5) + mt4_loop.py (MT4). These need the interactive session, so they start
  when the admin RDPs in.
- **BrokerCRM-DailyBackup** (SYSTEM, daily 03:00) -> `C:\broker-crm\backup_db.ps1`.
For FULLY hands-off reboot (bridges too, no login) you'd need Windows auto-logon (stores the
Administrator password) — NOT set up; would need the Windows password.

The 5 processes:
1. Backend:  cd C:\broker-crm\backend; .\venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 8000
2. nginx:    cd C:\nginx; .\nginx.exe -p C:\nginx
3. MT5 bridge: python bridge.py  (Flask :5000; polls online sessions every 30s for IP/CID;
   writes trading_accounts + account_identifiers; connects MT5 192.109.15.62:443)
4. MT4 loop:  python mt4_loop.py  (every 60s -> fetch_mt4_recent.py + syncs MT4 clients into
   trading_accounts; every ~10 cycles -> fetch_mt4_balance.py 2 to pull new MT4 deposits)
5. Meta loop: python meta_poller.py  (every 5 min -> fetch_meta_leads.py)   <-- NOT meta_loop.py
- Only ONE bridge per MT login. MT4 manager login=1025 (192.109.17.53:443), one connection
  at a time. mt4_loop's fetchers connect/pull/disconnect cleanly. Don't run a second MT4
  connection while mt4_loop runs (e.g. when running a diagnostic, STOP mt4_loop first).
- Manual restart of everything (interactive): the same Start-Process commands the start_*.ps1
  scripts use. Kill all: Get-Process python | Stop-Process -Force; Get-Process nginx | Stop-Process -Force

## Backups
- backup_db.ps1 runs pg_dump -Fc (custom format) to C:\broker-crm\backups\broker_crm-*.dump,
  keeps the newest 14. Restore: pg_restore. Verified working under SYSTEM. Log: backups\backup.log.

## Data fetchers / key scripts (backend\)
- fetch_meta_leads.py — pulls ALL Meta lead forms (derives a PAGE token from the system-user
  token via /{PAGE_ID}?fields=access_token — page-level /leadgen_forms NEEDS a page token).
  Captures per-lead `platform` (fb/ig) -> source = facebook/instagram; campaign_name = form
  name; meta_created = real form-submit time. De-duped on meta_lead_id. --dry-run / --form ID.
- meta_poller.py — runs fetch_meta_leads.py every 5 min (token from meta_sync.py).
  GOTCHA (fixed Jun 17 2026): fetch_meta_leads.py printed sample lead names; Arabic names under the
  headless cp1252 console raised UnicodeEncodeError and KILLED the whole fetch before inserting ANY
  lead -> leads silently stopped (token was fine, never expires). Fix: the script now forces
  sys.stdout/stderr to UTF-8 (errors='replace') at the top. If leads stop again, FIRST run
  `python fetch_meta_leads.py --dry-run` to see the real error; it's almost never the token.
  NOTE: this box has a respawner that keeps SYSTEM-python copies of meta_poller/bridge/mt4_loop/uvicorn
  alive alongside the venv ones (duplicate processes). Harmless for leads (fetch de-dups on
  meta_lead_id) but messy; only ONE MT4 connection should really run (see MT4 notes).
- fill_lead_country.py — leads.country from phone calling code.
- auto_match.py — matches leads<->clients (email or last-9 phone). Deposit truth = deals
  (action=2, profit>0), NOT the empty transactions/first_deposit_at. Sets match_badge
  (recapture / registered_no_deposit / converted), fills network (ip/cid from
  account_identifiers), computes a blended lead SCORE (0-100; +50 for matched). Run / --loop.
- build_transactions.py — MT5 deals (action 2/3/6) -> transactions. Idempotent (deal_id uq).
- fetch_mt4_balance.py — MT4 deposits/withdrawals/credits from the MT4 JOURNAL -> transactions
  (deal_id +4e9). Run only when mt4_loop is stopped. wired into mt4_loop every ~10 min (2d window).
- build_ibs.py — populates `ibs` from clients.agent: name/contact from the IB's own client
  account, ib_level parsed from group_name (IB-5..IB-10 = Bronze..Master), volume + commission
  (FX + XAU* lots × level + others × 1 point; lots = deals.volume/10000). Idempotent.
- fetch_mt4_once.py / fetch_mt4_recent.py — MT4 user + trade fetch (DAYS=3650 / DAYS=2).
- bridge.py (MT5), bridge_mt4.py (MT4 manager API) — see code.

## MT4 specifics (important — learned this session)
- Manager login 1025 has the data on the laptop but on THIS server the Admin* APIs are limited:
  AdmUsersRequest('*') returns exactly **5,288 users** (all already in clients) across 36 groups;
  **AdmTradesRequest returns 0** for every group/mode. So pumping mode is NOT the trade source.
- The WORKING source for MT4 trades AND balance ops is the SERVER JOURNAL (vtable 96,
  LOG_TYPE_TRADES). sync_trade_journal() in bridge_mt4.py parses "close order" -> trades;
  fetch_mt4_balance.py parses "changed balance/credit #order - amount for 'login' - 'comment'"
  -> deposits/withdrawals. The journal has a LIMITED retention window (not full history).

## Abuse detection engine (backend/abuse_engine.py — v3) — Jun 2026
- THE engine is `abuse_engine.py` v3 (NOT abuse_detectors_v2.py, unused). abuse_router's
  run_all_detectors() -> `run_engine(db)`. Frontend: Dashboard 'abuse' tab -> AbuseDetection.tsx,
  now an INVESTIGATION view (left ranked case list ↔ right visual "case file"): signals that fired,
  the opposing trade legs side-by-side, money flow, device/IP/phone links, one-click Freeze/Hold/
  Clear. Run from CLI: `python run_abuse.py [--keep]` (clears open cases first by default; ~3 min).
- v3 design = FEWER + DEEPER + PROVABLE (desk said v2 was too noisy/shallow/unconvincing):
  - Multi-signal: each detector builds a weighted `signals[]`; score=sum of fired weights; flag only
    if score>=50 AND >=2 signals fire. severity >=75 crit / >=60 high / >=50 med.
  - Structured evidence: abuse_cases.evidence_json (added col) holds {headline, signals, proof_pairs,
    proof_trades, money_flow, links, accounts}. get_case_detail returns it as `evidence_obj`; the UI
    renders it. /abuse/type-counts feeds the filter chips.
  - build_clusters(): connected components of accounts sharing device(cid/mqid)/ip/phone — the basis
    for ring & chip-dump. cluster_tradeable() caps per-member trade pulls (a mega-scalper in a cluster
    caused an OOM — fixed) and improves precision (rings are small bonus accts, not 50k-trade scalpers).
- UI = KPI CARDS (not a table): each case is a card with its headline numbers as KPI tiles. The
  per-case `kpis` (label/value list) is stored in abuse_cases.kpis and returned by /abuse/cases so
  the card renders without fetching detail. evidence_obj["kpis"] is the source.
- 7 detectors (clear names):
  margin_partner 🔥HOT: a credit/bonus acct blows up (margin-out, loss<=-300 in a 5-min window, went
                 negative) and another acct wins within the 80% band (0.8-1.25x) of that loss on the
                 SAME symbol, OPPOSITE side, within ±2min, volume-matched (mirror) OR the pair repeats.
                 Aggregated per (loser,winner) pair. broker_loss = bonus/credit that funded the loss.
                 Big market-driven blow-ups (no opposite client) correctly DON'T match.
  hedge_ratio    any account where >=25% of opening trades are hedged (opposite same-symbol open within
                 5min, matched vol; efficient time-windowed sweep over ALL accounts). KPI shows the %
                 and the fraction e.g. "86% (136/158)". score=50+(ratio-0.25)*120. ~868 accts flagged.
  bonus_ring     device/phone-linked accounts hedging EACH OTHER on bonus (opp opens <=15s, matched vol)
  bonus_cashout  took bonus + withdrew >=1.2x deposit; CRITICAL only if also barely-traded (grab&go)
  chip_dump      linked pair transferring money via paired opposite CLOSES (one wins, one loses, repeat)
  swap_carry     swap-free(-IS) acct, >=8 overnight holds across >=4 nights, gated on positive PnL
  toxic_arb      >=90% win-rate, >=50 closes, avg hold <15min via FIFO pairing, +PnL (feed-lag arb)
- abuse_cases has `hot` BOOLEAN (margin_partner sets it) + `evidence_json`. /abuse/type-counts returns
  per-type total/critical/hot. /abuse/cases supports hot=1 filter and returns `hot`. dedup unique index
  is (abuse_type,login_a,COALESCE(login_b,0),COALESCE(symbol,'')) so pair cases with a shared winner
  don't collapse. UI = ONE unified KPI table (default all types as rows: serial#, catching time, type
  +HOT, accounts(n), symbol, severity, possible broker loss, risk); row click -> slide-in case-file
  drawer; tabs filter All/Hot/per-type. ~3-5 min run.
- DAY-TO-DAY INTEGRATION: run_engine() builds `abuse_account_flags` (login -> worst open case:
  abuse_type/severity/hot/case_id/n_cases; covers EVERY login in a case via all_logins, not just
  login_a). Rebuild standalone: `from abuse_engine import build_account_flags`. Endpoints: POST
  /abuse/flags {logins:[...]} -> per-login flag (used as a frontend overlay); GET /abuse/cases?login=N
  -> all cases involving N. Surfaced in: Transactions withdrawals (⛔ HOLD badge, sev-coloured, click
  -> case modal; transactions_router reads abuse_account_flags), Clients list (abuse chip via /abuse/
  flags overlay on each row+related accts), IB profile client table (ib_router get_ib fills abuse_flag/
  severity/hot from abuse_account_flags). Network graph is now LAZY: GET /abuse/cases/{id}/network
  (separate from the detail call) so the case file opens immediately.
- Case file (drawer) is built for BACK-OFFICE: a plain-language "What happened / Why it costs us / What
  to do" block (EXPLAIN map in AbuseDetection.tsx) + the signals + dated proof legs (each chip_dump leg
  shows open→close time + hold, via FIFO open lookup) + money flow + a NETWORK GRAPH. The graph comes
  from abuse_router.case_network(db,logins,abuse_type) returned as detail.network {nodes,edges}: 1-hop
  relationships among the case accounts via shared device(cid/mqid)/ip (account_identifiers), shared
  phone (clients), family/IB (network_edges), plus the abuse link itself. Frontend NetworkGraph renders
  an SVG (case accounts = red nodes, edges colour-coded by reason w/ legend). Solo types (bonus_cashout,
  swap_carry) correctly return 1 node / 0 edges. A case-detail open is ~2s (several link queries).
- SAFETY: run-detection does NOT auto-freeze (apply_auto_actions not called). Desk freezes manually
  via POST /abuse/cases/{id}/action (freeze sets clients.is_flagged + trading_accounts.is_active=FALSE
  for that case's logins only).
- DATA GOTCHAs (all handled): deals has NO open_price (single-execution rows at `price`); clients has
  NO is_islamic (only trading_accounts — backfilled from group_name -IS token); deals.swap ~empty
  (1.3k/4M) so overnight is derived via FIFO open->close pairing, not the swap field; 01:00-05:00 UTC
  is the BUSIEST window (Asian gold) so 'night' alone is not a signal; all_logins stored COMMA-sep
  (use parse_logins(), not json.loads).

## Meta CAPI (lead quality -> Meta)
- meta_capi_router.py sends CRM lead-stage events to Meta dataset **1611045120042482**
  (Conversions API). WORKING (events_received:1). Endpoint POST /meta/lead/{id}/stage maps
  qualified/converted/not_qualified/lost. It is WRITE-ONLY — you cannot read quality back via
  the API; only visible in Meta Events Manager (production events, not the Test Events tab
  unless you pass a test_event_code).

## Sales Agents page + IB list filters (Jun 2026)
- agents_router.py (prefix /agents, mounted in main.py). GET /agents includes sales agents +
  sales managers + Team Leaders (role IN sales_agent/sales_manager OR title ILIKE '%team leader%'),
  EXCLUDES Narmeen (sales director). 55 people. Per-agent: clients/leads/verified_leads/ibs (lifetime),
  new_clients/new_ibs (registered in the PERIOD via clients.reg_date — NOT created_at, which is only the
  import date Jun 15-16), deposits/withdrawals (transactions in period via tx_date), commission, net.
  Params: period (today…last_year, reuses ib_router.period_dates), group (''/sales/manager/team_leader),
  search, sort (every column). Lead metrics via matched client (leads have no agent yet, all 'new').
  COMMISSION: the sales_commissions/commission_plans/sales_targets tables are EMPTY, so commission =
  markup revenue the agent's clients generated = SUM(deals.markup_profit)/10000 (markup_profit is in the
  /10000 scale like volume; ~$7/lot; total ~$1.4M). Swap to a real formula once one is defined. The big-
  period query scans deals so it takes ~6-8s. Frontend: SalesAgents.tsx (period bar + group dropdown +
  sortable columns), nav key 'sales_agents' under IB System in Dashboard.tsx.
- IB Admin list (IBAdmin.tsx) columns Sales agent / Country / City / Level are CLICK-TO-FILTER
  (get_ibs now accepts country/city/ib_level/sales_agent_id; returns sales_agent + sales_agent_id =
  the agent on the IB's OWN account clients.login=ib.agent_id). Active filters show as removable chips.
  Clicking a sales agent AGAIN (already filtered by it) fires navigate->sales_agents (agentId focus).

## Unified login — staff CRM vs Client Portal (Jun 2026)
- SAME login URL/page routes by account type. /auth/login: tries `users` (staff) FIRST; if the email
  isn't a staff user, falls back to `clients` (LOWER(email) match + verify clients.password_hash).
  Token carries user_type ('staff'|'client') + (clients) login. /auth/me decodes the token and returns
  staff (from users, with tokens_valid_after check) or client (from clients) accordingly. Staff path
  unchanged — do NOT break it.
- clients.password_hash (added) = the client's portal password (bcrypt via auth.get_password_hash).
  Existing 15k clients have none until set (registration flow should set it; or admin sets it). DEMO
  client: samir.al-rashid@email.com / <password redacted> (login 10119).
- Frontend App.tsx: if user.user_type==='client' -> renders ClientDashboard (wrapped in a Client Portal
  header w/ logout), else the staff Dashboard. ClientDashboard hits /client-dashboard/kpis/{login}
  (defined in leads_router.py as client_router, prefix /client-dashboard).
- SECURITY TODO: /client-dashboard/* endpoints take a login param and DON'T verify the caller's token
  owns that login (any login is queryable). Harden with a get_current_client dependency before real
  client rollout (SAFETY RULES: real client auth is a gate before real money).

## Power Dialer (Yeastar click-to-call)
- power_dialer_router.py (prefix /dialer, mounted in main.py) + frontend/src/PowerDialer.tsx
  (DialerLauncher button on Clients/Leads). Needs tables dialer_sessions / dialer_queue /
  dialer_call_logs — created by `python create_dialer_tables.py` (they were MISSING, which broke
  the whole feature; fixed Jun 2026). get_next prioritises by clients.call_score (NOT c.score,
  which doesn't exist). /dialer/call rings via yeastar_service (PBX reachable, ext 101 = SUCCESS).
  Flow: session/start -> session/{id}/queue -> /next -> /call/result (smart reschedule by attempt:
  5/15/30min,1h, then next-day±2h...) -> /stats -> /stop. Outcomes log to dialer_call_logs AND the
  client timeline (call_actions) / lead notes.

## Client Portal (separate CRA app — LIVE at /portal/)
- SECOND React app in `C:\Broker-crm\portal` (CRA, react-scripts 5.0.1, React 19, MUI 9, react-router-dom
  7 state-based — no BrowserRouter). package.json has `"homepage":"/portal"`; src/api.ts BASE=`/api`
  (nginx proxy). Build: `cd C:\Broker-crm\portal; $env:CI="false"; npm run build` (use
  `npm install --legacy-peer-deps` — React 19 peer conflicts; a plain `npm install` reports exit 0 but
  leaves node_modules empty). Served by nginx `location /portal/ { alias C:/Broker-crm/portal/build/; }`.
- Backend: `backend/portal_router.py` (prefix /portal, mounted in main.py). Own JWT scope="portal" via
  `_make_portal_token` / `get_current_client` (separate from admin tokens). AUTH (hardened Jun 2026 — the
  portal is on the PUBLIC domain my1.tnfx.co): REAL login is POST /portal/auth/login {identifier, password}
  — identifier = email OR trading login OR client id (NOT name); verifies clients.password_hash (bcrypt);
  a client with NO password set CANNOT log in. The old passwordless POST /portal/auth/dev-login is DISABLED
  (returns 403) behind `ALLOW_DEV_LOGIN=False` in portal_router.py — keep it False on the public site;
  flip to True only in a private/dev box for impersonation. To give a client portal access: set
  clients.password_hash via auth.get_password_hash (admin/registration). Demo client WITH a password:
  login 577667 / client_id 23352 (Ahmed Wissam Ibrahim, lxutee2@gmail.com). Frontend portal/src/Login.tsx
  now has email/login + password fields → portalLogin() in api.ts.
- LOGIN-OWNERSHIP HARDENING (Jun 2026): every data endpoint already derives client_id from the JWT, but the
  money endpoints accepted a `login` from the body. `_assert_owns_login(db, client_id, login)` now gates
  /portal/deposit, /portal/withdraw, /portal/deposit/initiate (403 "That account is not yours" if the login
  isn't in _client_logins). /transfer + /positions/{id}/close + copy endpoints were already ownership-checked.
- PASSWORD ONBOARDING (complete): registration sets clients.password_hash (registration_router /submit);
  OTP forgot-password resets it (password_reset_router /auth/pwreset/send|verify|reset, scope='client', also
  clears the lockout); NEW logged-in change-password POST /portal/auth/change-password (verifies current,
  min 8, returns a fresh token so the user stays in, clears lockout) wired into portal Profile page
  (ChangePassword form in portal/src/pages/Profile.tsx).
- BRUTE-FORCE LOCKOUT (Jun 2026): DB-backed table `portal_login_attempts` (shared across the 2 uvicorn
  workers + survives restarts, auto-created at portal_router import). portal_login checks BEFORE verifying
  the password: LOCK (429) if >=5 failed attempts for the identifier OR >=20 for the IP within the last
  15 min (MAX_FAILS_IDENT/MAX_FAILS_IP/WINDOW_MIN consts). Real client IP via X-Forwarded-For/X-Real-IP
  (nginx). A successful login wipes that identifier's failed rows; rows >1 day old are GC'd on each attempt.
  To unlock a user manually: DELETE FROM portal_login_attempts WHERE ident=:e (lowercase email/login).
  STILL TODO before real money: token doesn't verify it owns the login (defense-in-depth).
  Endpoints: /me /dashboard /accounts /trades /ib-trades /deposit /withdraw /money-requests /loyalty/*
  /transfer /accounts/* /kyc/*. Deposit/withdraw are SIMULATION (write portal_money_requests, no gateway).
- KEY DATA-LINKAGE GOTCHA (fixed Jun 2026): `trading_accounts.client_id` and `deals.client_id` are NULL
  everywhere — the portal client→accounts/deals link is BY LOGIN, not client_id. `_client_logins(db,
  client_id)` resolves the client's own login + every phone+platform sibling (same aggregation as the
  Clients list); /accounts /trades /dashboard all query `WHERE login = ANY(:logins)`. Before this, every
  portal user saw 0 trades / fallback-only accounts.
- TWO 500s fixed: (1) /portal/accounts fallback selected clients.account_type which doesn't exist (only
  group_name/platform/login/name) → NULLed it. (2) /portal/dashboard 500: the deposits query hit the
  then-missing portal_money_requests table; its try/except had NO db.rollback(), so the aborted txn
  poisoned the next query ("current transaction is aborted") → 500. Fixed by creating the table AND adding
  db.rollback() in the except. LESSON: any try/except around a query that may fail MUST db.rollback() or
  it poisons the SQLAlchemy session for the rest of the request.
- First request after a uvicorn restart is slow (~18s cold-start: imports/plan warmup); warm calls ~0.1s.

## Copy Trading (signal providers + followers) — Jun 2026
- Both portal (client-facing) + admin (staff). Data model in `backend/seed_copy_trading.py` (creates the
  tables AND seeds 50 demo providers). Tables: `copy_providers` (profile + denormalized stats:
  return_pct/return_30d/win_rate/max_drawdown/profit_factor/total_trades/avg_hold_min/followers/aum/
  risk_level/strategy/markets/status/featured; nullable client_id+login for the apply flow / future MT
  link), `copy_provider_history` (daily equity curve, start $10k), `copy_provider_trades` (sample trades),
  `copy_followers` (subscriptions: provider_id, client_id NULLABLE for synthetic, allocation, multiplier,
  copy_mode proportional/fixed/mirror, status active/stopped, pnl).
- SEED: `python seed_copy_trading.py` — idempotent (TRUNCATEs the copy_* tables then reseeds). 50 diverse
  providers: scalping/intraday/swing/news/grid/conservative, gold-only/EURUSD-only/FX-majors/indices/multi,
  returns -35%..+143%, 1..150 days history, ~5k trades, ~1.6k followers (≈130 are REAL portal clients so
  'My Copies' is populated). 9 are net losers for realism. random.seed(42) → reproducible.
- API `backend/copy_router.py` — TWO routers mounted in main.py: `portal_copy` (prefix /portal/copy, auth
  get_current_client) and `admin_copy` (prefix /copy, auth get_current_user/staff). Portal: GET /providers
  (leaderboard; sort=return/winrate/followers/drawdown/risk/new, filters strategy/market/risk_max/search/
  featured; returns `following` per card), GET /providers/{id} (detail + equity_curve + recent_trades +
  recent_followers + i_follow), POST /follow {provider_id,allocation,multiplier,copy_mode} (min-investment
  guard, 1 active sub per client+provider), POST /unfollow, GET /my-following (+ totals), GET /my-provider,
  POST /apply (become a provider → status 'pending'). Admin: GET /admin/providers?status=, GET /admin/stats,
  POST /admin/providers/{id}/approve|reject|feature.
- FRONTEND: portal `portal/src/pages/CopyTrading.tsx` (wired into Portal.tsx nav key 'copytrading' — was a
  ToolPage placeholder) — Discover leaderboard cards w/ inline SVG equity curves, detail modal (curve +
  stats + trades + copiers + follow form), My Copies tab, Become-a-Provider tab. Staff
  `frontend/src/CopyTradingAdmin.tsx` (Dashboard.tsx nav key 'copy_admin', 🪞 in Main) — KPI cards +
  sortable provider table + approve/reject/feature actions.
- REPLICATION ENGINE `backend/copy_engine.py` (Jun 2026) — DRY-RUN, gated. `COPY_LIVE_ENABLED`
  (env COPY_LIVE_ENABLED=1, default FALSE) is the hard gate; while False the engine only WRITES intended
  orders to `copy_mirror_orders` (status='simulated', dry_run=TRUE) and NEVER calls MT.
  `compute_follower_lots(master_lots, copy_mode, multiplier, allocation, master_capital=10000)` sizes each
  follower: proportional = master_lots*(allocation/master_capital)*mult; mirror = master_lots*mult; fixed =
  mult (acts as the lot size); clamped MIN_LOT 0.01 / MAX_LOT 50. `replicate_trade(db,provider_id,
  master_trade,dry_run)` fans one master trade to all active followers; `run_dry_run_cycle(db,pid,n)` previews
  the last N seeded trades (idempotent — clears prior dry-run rows). `place_order_via_bridge()` is a guarded
  STUB (raises unless COPY_LIVE_ENABLED) — wire it to the MT5 bridge :5000 OrderSend route only after a
  one-account live test. Admin API: POST /copy/admin/replicate/dry-run {provider_id,n_trades}, GET
  /copy/admin/mirror-orders. Admin UI: "Preview copy ⚙" button per approved provider → modal showing the
  computed mirror orders. Test harness: `python copy_engine_test.py` (sizing unit checks + one-account
  scenario + live-gate assertion; cleans up its rows).
- CONTINUOUS DAEMON `backend/copy_loop.py` (Jun 2026, DRY-RUN) — tails each approved provider's master
  trades and fans them to followers via replicate_trade(source='loop'); computes each follower's copied P/L
  (pnl_per_master_lot × follower_lots) and writes copy_followers.pnl so 'My Copies' shows REAL results.
  Incremental & idempotent via `copy_provider_cursor` (last_source_id/processed per provider). Master source:
  real providers (login set) → live `deals` rows; synthetic seeded providers (login NULL) → replay
  copy_provider_trades as the feed (demo CAP=40 trades/provider so the table stays bounded ~47k loop orders).
  `copy_mirror_orders.source` separates 'loop' (daemon) from 'preview' (admin one-off) so the admin Preview
  button never clobbers daemon rows. CLI: `python copy_loop.py --once|--loop [--interval N]|--status|--reset`.
  NOT auto-started (avoids continuous writes on the prod box) — run --loop manually, or add a Task Scheduler
  entry like the other loops if you want it always-on. Still DRY-RUN: COPY_LIVE_ENABLED stays False.
- REAL PROVIDERS `backend/promote_real_providers.py` (Jun 2026) — read-only on deals; ranks real accounts by
  genuine performance (return%, win rate, max DD, profit factor, volume) and creates copy_providers rows
  LINKED to the real MT login (login set, is_real=TRUE, verified, status='approved') with equity curve
  (copy_provider_history) + recent trades (copy_provider_trades) from ACTUAL deal history. 30 created
  alongside the 50 demo (is_real=FALSE). Return base = deposits (deals action=2 profit>0), floored so the
  equity curve can't go negative (DD capped 95%, realistic). Idempotent (clears prior is_real rows, rebuilds).
  Re-run: `python promote_real_providers.py [--target N] [--dry-run]`. API: copy_providers.is_real exposed in
  _prov_card + GET /portal/copy/providers?real_only=1; portal CopyTrading shows a green "REAL" badge + a
  "✓ Real traders" filter. NOTE: real providers tail the live `deals` table in copy_loop.py (the daemon's
  real-master path), so their stats update from real trades; the seeded ones stay synthetic.
- PRODUCTION LAYER `backend/copy_enrich.py` (Jun 2026) — adds + computes:
  • ACTIVITY: copy_providers.last_trade_at + active (traded within 14d; real=from deals, demo=from
    copy_provider_trades). Leaderboard floats active above inactive (ORDER BY active DESC) and supports
    ?active_only=1; portal defaults to active-only with a "Show inactive" toggle + greyed INACTIVE badge.
  • FOLLOWER RISK SETTINGS: copy_followers.copy_existing (new/all/skip_losing — the ZuluTrade "copy their
    open positions?" choice), max_lot, stop_equity_pct. follow endpoint accepts them; portal copy dialog has
    the radio + max-lot + stop-loss inputs and relabels allocation = "your copy capital (not a fee)".
  • PROVIDER EARNINGS (the incentive): perf_fee_earned = fee_pct% × Σ follower peak_pnl (HIGH-WATER MARK
    per follower) + commission_earned = copier volume lots × $3/lot (IB-style rebate, PROVIDER_COMMISSION_PER_LOT).
    Surfaced in portal Become-a-Provider (earnings tiles) + admin (Earnings column + KPI). Re-run copy_enrich.py
    to refresh (idempotent, read-only on deals/abuse).
  • INTEGRITY: copy_providers.abuse_flag overlaid from abuse_account_flags (worst open case for the login);
    admin shows a ⚠ next to flagged providers.
  • COPIED-POSITION LIFECYCLE (Jun 2026): on follow with copy_existing != 'new', `_snapshot_positions()`
    snapshots the provider's open positions into `copy_positions` for the follower (sized via
    compute_follower_lots, skip_losing drops negative ones). copy dialog defaults to 'all' (copy losing too,
    first option). My Copies has TWO sub-tabs: Providers (table: Copied-from, return, allocation, my P/L,
    open count, Disconnect) + Open trades (GET /portal/copy/my-open-trades — table with provider/symbol
    filters, sort by provider/symbol/pnl, per-row manual Close via POST /portal/copy/positions/{id}/close).
    Disconnect = POST /portal/copy/unfollow {provider_id, close_positions} with a keep-or-close confirm modal
    (ZuluTrade-style). ALL still SIMULATION — copy_positions.dry_run=TRUE, no MT orders placed.
  • OPEN POSITIONS: GET /portal/copy/providers/{id}/open-positions → bridge read-only /positions/{login}
    (added to bridge.py, activates on next natural bridge restart); falls back to recent trades (source='recent')
    until then. Portal detail has an "Open positions" tab alongside Recent trades / Copiers.
- PRODUCTION FEATURES `backend/copy_features.py` (Jun 2026, all DB-only/simulation):
  • RISK ENFORCEMENT: `enforce_risk(db)` auto-closes a follower's open copy_positions + sets the follower
    status='stopped' (stopped_reason='stop_loss') + notifies when open loss% ≤ -stop_equity_pct. Per-follower
    max_lot capped via `cap_to_max_lot()` at snapshot/replicate. Wired into copy_loop each cycle.
  • VETTING: `vet_applicant()` requires ≥30 closed trades + ≥7 days on the applicant's own login before
    POST /portal/copy/apply succeeds (GET /portal/copy/eligibility surfaces it to the UI). `auto_suspend_flagged()`
    sets copy_providers.suspended=TRUE + active=FALSE for any provider carrying an abuse_flag and notifies its
    copiers. list_providers ALWAYS excludes suspended (COALESCE(suspended,FALSE)=FALSE).
  • NOTIFICATIONS: `copy_notifications` table + `notify()`. Types: copy_started / stop_loss / provider_flagged /
    provider_inactive. GET /portal/copy/notifications (+unread), POST /notifications/read. Portal bell in the
    Copy Trading header (NotifBell in CopyTrading.tsx).
  • FEES: follower's owed performance fee = fee_pct% × follower peak_pnl (high-water mark); shown per-row in
    My Copies ("Fee owed") + provider's own earnings. PAYOUTS: `settle_payouts()` snapshots each provider's
    unsettled fee+commission into `copy_payouts` (pending); admin GET /copy/admin/payouts, POST
    /payouts/settle, POST /payouts/{id}/pay (→ IB later). Admin "⚙ Run safety sweep" button calls
    POST /copy/admin/maintenance (enforce_risk + auto_suspend + inactive notices + settle).
  • DISCLAIMER: one-time risk acknowledgment (`copy_acks`) required before a real (non-demo) copy — follow
    returns 412 "disclaimer_required" until accepted; portal shows a risk-disclosure checkbox in the copy
    dialog. GET /portal/copy/disclaimer, POST /disclaimer/accept.
  • DEMO COPY: copy_followers.is_demo — "Copy on demo (paper)" toggle skips the disclaimer + flags the sub as
    paper. Low-allocation guardrail warns when allocation < 2× min_investment (lot-rounding over-leverage).
  • PROVIDER DASHBOARD: GET /portal/copy/provider-dashboard → copiers list + payouts, rendered in the portal
    Become-a-Provider approved view.
- LIVE EXECUTION MACHINERY — BUILT & GATED (Jun 2026, NOT yet activated):
  • bridge.py routes `/trade/open` + `/trade/close` (via MT5Manager MTRequest + mgr.DealerSend). TRIPLE-gated:
    env COPY_BRIDGE_TRADING (default off → dry echo), per-request dry default True, hard lots cap
    COPY_TRADE_MAX_LOTS (default 1.0). `_dealer_trade()` builds the dealer request defensively (the exact
    MTRequest fields get validated in the one-account test). ⚠ The LIVE bridge has NOT been restarted, so
    these routes are present in the file but NOT active on :5000 yet (avoids interrupting MT sync).
  • copy_engine.place_order_via_bridge / close_order_via_bridge POST to the bridge (gated by COPY_LIVE_ENABLED).
  • copy_positions table (per-follower open position, closed when the master closes) for the live lifecycle.
  • ONE-ACCOUNT TEST HARNESS `copy_live_test.py` — DRY by default; real only with --live AND COPY_LIVE_ENABLED=1
    AND bridge COPY_BRIDGE_TRADING=1 AND bridge restarted. Validates sizing + bridge round-trip on a single
    follower before any broad copying.
- TO ACTUALLY GO LIVE (supervised, real money — do WITH the user, on ONE account first):
  (1) restart the bridge so /trade/* load (~4min, brief MT-sync gap; see bridge process notes);
  (2) on the bridge set env COPY_BRIDGE_TRADING=1 + COPY_TRADE_MAX_LOTS small;
  (3) `set COPY_LIVE_ENABLED=1`; (4) `python copy_live_test.py --follower-login <funded test acct> --lots 0.01
  --live` and verify the open/close on the MT terminal (adjust _dealer_trade MTRequest fields if the SDK differs);
  (5) link copy_providers.login to a real MT master; (6) only then run copy_loop.py --loop with the gates on.
  Follower pnl/provider stats stay seeded/simulated until live fills feed them.

## PowerShell / shell gotchas
- Inline `python -c "..."` mangles quotes. Use a here-string to a file, or write a script.
- Don't paste raw SQL into PowerShell. Use psql -c or a psycopg2 python script (creds via backend/db_config.py).
- The Bash tool is Git Bash (POSIX). For long-running stuff use run_in_background.

## What was done THIS session (Jun 2026)
- Meta: multi-form fetch (all 11 forms, ~20k leads), per-lead fb/ig channel, country from phone.
- Leads: auto_match scoring/badges/network; recapture & no-deposit tags with Meta-form-date
  hover popups; registration-date column; +50 priority score for matched (sorts to top).
- Transactions page: built from MT5 deals + MT4 journal; internal transfers split out; real
  datetimes; abuse flag decoupled from network (now reads abuse_cases, empty until detectors run).
- IB system: populated 1,027 IBs; IB Admin list (KPIs, status tiers active/low/inactive/
  super-inactive by trading-clients-in-period, configurable via "Status rules"); IB profile
  (8 period KPIs, clients table with network/volume/deposit-method/abuse/start-trade, two tabs);
  Action menu (call outcomes + promote/demote/pay/set-target); IB name clickable to filter,
  click-again -> IB page. ib_router /ibs/{id} fixed (was 500 on missing referral_links).
- Clients: real deposits/withdrawals/dep#/first-deposit/last-activity from transactions
  (aggregated across ALL of a person's logins); list now groups by phone+platform = ~15.2k
  (was merging MT4+MT5 into one row = 12.3k); removed the recapture sort-pin (now pure score).
- Trading account profile: open positions + trade history fixed (frontend read wrong fields
  open_trades/history vs backend open_positions/trade_history, and never fetched the detail).
- MT4 deposits: fetch_mt4_balance.py loaded ~12.4k deposits ($353K) etc. from the journal.
- Ops/security: HTTPS (Let's Encrypt + auto-renew), SECRET_KEY hardened, auto-start on reboot
  (Task Scheduler hybrid), daily pg_dump backup.

## PENDING / NEXT WORK
1. **Abuse-detection section** — ✅ DONE (Jun 2026). Rebuilt as `backend/abuse_engine.py`
   (6 data-grounded scored detectors) and wired into abuse_router via run_all_detectors.
   See "Abuse detection engine" section below. abuse_cases table now exists & populated
   (~2,431 cases). Remaining optional polish: tune thresholds; wire abuse_cases into the
   Transactions withdrawal-flag / IB / clients abuse columns if not already reading it.
2. **MT4 full history / fully hands-off reboot** — MT4 journal retention is limited (got what's
   there). Fully-hands-off reboot for the bridges needs Windows auto-logon (the Administrator
   password) — currently bridges start at admin login.
3. **Lead-quality score weights** — tune if desired (currently match +50 / verified +15+15 /
   both-contacts +10 / recency +10/+5).
4. **transactions.client_id** mostly null; leads country/score/network are populated; campaign
   filled. Most original "empty columns" work is DONE.
5. **Auto-logon (fully hands-off reboot for the bridges)** — DEFERRED by user. Enabling Windows
   auto-logon (registry AutoAdminLogon=1, DefaultUserName=Administrator, DefaultPassword=<pw>,
   DefaultDomainName) makes the server log Administrator in at boot, which creates the interactive
   desktop session the native MT manager DLL needs, so the at-logon `BrokerCRM-Bridges` task fires
   and the MT4/MT5 bridges (live data sync) come back automatically after a reboot with no manual
   RDP login. Currently the site/backend survive reboot (SYSTEM boot task) but the bridges wait
   until an admin logs in. Tradeoff: the Windows Administrator password is stored in the registry
   in recoverable form. Needs no code change — only enabling it, and the user must supply the
   Windows password. User chose NOT to do this for now (keep the password off the box).

## SAFETY RULES (carry these forward)
- The portal's account-creation + deposits are SIMULATED (fake creds, no real MT provisioning).
  Do NOT wire real money / real account provisioning until: data stable, REAL client auth
  replaces dev-login, bridge UserAdd tested on ONE account first, payment APIs wired one at a
  time with webhook verification. Previous sessions correctly refused to shortcut this.
- This is a production DB with real client data. Prefer additive changes (ADD COLUMN IF NOT
  EXISTS, INSERT ... ON CONFLICT). Back up before destructive operations (daily backup exists).
  Don't TRUNCATE without explicit confirmation.
- clients.cid has FAKE sequential placeholders (C100000...) from old seed — harmless; real
  CID/IP detection reads account_identifiers, NOT clients.cid.
- When stopping mt4_loop for a diagnostic, RESTART it after (it won't come back until next
  admin logon otherwise).

## Test client logins (Ahmed Zaman): 1829, 2353, 4106, 4745, 5094
