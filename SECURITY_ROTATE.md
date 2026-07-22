# SECURITY — Rotate MT manager credentials (P0-7)

**Status:** OPEN — needs someone with **MT server admin** access + a short maintenance window.
**Why:** the MT4/MT5 manager passwords were hardcoded in tracked source and are therefore in the
**git history**. Moving them into the gitignored `backend/mt_secrets.py` (done) stops *future* leaks
but does NOT remove them from history — the only fix is to **change them on the MT servers** so the
leaked values stop working. All 8 accounts must be rotated, whether or not each is actively
connecting right now, because all 8 are in history.

> The 8 freshly-generated replacement passwords are in **`backend/mt_secrets.NEW.txt`** on the CRM
> box (S1). That file is **gitignored** (never committed) and should be **deleted after** rotation.
> This runbook is intentionally secret-free.

---

## The 8 manager accounts

Only **3 distinct passwords** are in use today — the six B/C/D accounts (both servers) **share one
password**, including the provisioning + execution accounts. Give each account its **own unique**
password (the generated set already does).

### MT5 server — `192.109.15.62:443`
| Login | Role | Purpose | Password today |
|-------|------|---------|----------------|
| 1025 | A — live sync    | sessions/equity/account list (bridge.py) | unique |
| 1026 | B — deals/journal| history pull (mt5_deal_worker)           | **shared** |
| 3027 | C — provisioning | UserAdd / credit / real deposits         | **shared** |
| 3028 | D — execution    | copy-trade order send/close              | **shared** |

### MT4 server — `192.109.17.53:443`
| Login | Role | Purpose | Password today |
|-------|------|---------|----------------|
| 1025 | A — live sync    | mt4_loop live sync             | unique |
| 1026 | B — journal      | journal pull (mt4_journal_worker) | **shared** |
| 3027 | C — provisioning | provisioning                   | **shared** |
| 3028 | D — execution    | execution                      | **shared** |

---

## Rotation procedure (maintenance window, ~15 min)

Do it in one window so the running processes aren't using a stale password for long.

1. **Open** `backend/mt_secrets.NEW.txt` (on S1) — it lists the new password for each of the 8
   accounts and has a paste-ready `mt_secrets.py` block at the bottom.

2. **On the MT5 server admin** (MT5 Administrator / server manager) set the new password for
   manager logins **1025, 1026, 3027, 3028** — each to its new value from the file.

3. **On the MT4 server admin** do the same for **1025, 1026, 3027, 3028**.

4. **On S1**, replace the contents of `backend/mt_secrets.py` with the paste-ready block at the
   bottom of `mt_secrets.NEW.txt` (this is the ONLY file that stores them; `mt_managers.py` imports
   from it). Save.

5. **Restart everything that holds an MT connection** so it reconnects with the new password:
   - **Bridges / workers:** stop `bridge.py`, `mt4_loop.py`, `mt5_deal_worker.py`,
     `mt4_journal_worker.py` (and `step_b_trades.py` / copy execution if running), then relaunch via
     `C:\Broker-crm\start_bridges.ps1` (they need the interactive session). Brief MT-sync gap (~a few min).
   - **Web tier** (reads `mt_secrets.py` for neg-cover): rolling restart, zero downtime —
     `powershell C:\Broker-crm\restart_backend.ps1`.

6. **Verify** the new passwords work:
   - Bridge health: `curl http://127.0.0.1:5000/health` (or check it reports connected + trader count).
   - Watch `backend\logs\*.err` for any `connect failed` / auth errors from the workers.
   - Confirm live data still flows (a fresh account/equity update after a cycle).

7. **Delete** `backend/mt_secrets.NEW.txt` once everything reconnects cleanly. The live secret then
   exists only in `backend/mt_secrets.py` (gitignored).

---

## Also part of this task

- **Confirm the GitHub repo is PRIVATE** with **secret-scanning / push-protection ON.** The old
  secrets are in its history, so a public repo = immediate exposure. If it was ever public, treat
  rotation as urgent and assume the old values are compromised.
- **Rotate the database password.** ✅ DONE Jul 17 2026 — `2722` rotated to a strong 24-char via
  `backend/rotate_db_pw.py` (auto-generates the password, parameterized ALTER USER, backs up +
  verifies before writing configs). Updated `backend/db_config.py` + `backend/.env`, regenerated
  the PgBouncer userlist (new SCRAM verifier), and restarted the whole stack (web/loops/bridge/
  workers) — all verified. New value is in the gitignored `backend/db_password.NEW.txt` — **store it
  in a password manager, then delete that file.** Rollback: `backend/*.bak-prerotate-*` hold the old
  configs; the old password is in them.
- **(Optional, thorough) Purge history.** Even after rotation the old strings remain readable in
  `git log`. If you want them gone, rewrite history (`git filter-repo`) and force-push — coordinate
  with anyone else who has clones. Rotation is the security fix; purging is cleanup.

---

## Quick reference — what changed in the code (already done)
- All MT passwords now live ONLY in `backend/mt_secrets.py` (gitignored). `mt_managers.py` is a thin
  shim re-exporting `MT5_SERVER / MT4_SERVER / MT5 / MT4`, so every `import mt_managers as M` caller
  is unchanged.
- ~16 files were de-secreted (bridge.py, bridge_mt4.py, mt5_deal_worker.py, mt4_journal_worker.py,
  routers/neg_cover_router.py, neg_balance.py, make_neg_router.py, fetch_mt5_emails.py, and the
  probe/diagnostic scripts). Verified: 0 tracked files contain any MT password.
