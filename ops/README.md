# Ops remediation bundle (2026-07-06)

Scripts prepared from the operations review. **Nothing here has been run** — review, then run
each from an elevated PowerShell on the CRM box. None of them modify the running app; they
register scheduled tasks and set up backup trust.

## 1. Register the three missing scheduled tasks — `register_missing_tasks.ps1`
The ops review found these referenced by project scripts but never actually registered, so:
no bridge auto-start after reboot, **no self-healing at all**, and no off-box backup pull.

```
powershell -ExecutionPolicy Bypass -File C:\Broker-crm\ops\register_missing_tasks.ps1
Get-ScheduledTask -TaskName BrokerCRM-* | Format-Table TaskName,State   # verify
```
Registers:
- **BrokerCRM-Bridges** — runs `start_bridges.ps1` at Administrator logon (MT DLL needs an
  interactive session). This is why the MT4/MT5 bridges don't come back after a reboot today.
- **BrokerCRM-Watchdog** — runs `health_watchdog.ps1` every 5 min (restarts nginx/backend if
  down). Right now nothing restarts a dead process.
- **BrokerCRM-OffboxBackup** — runs `pull_offbox_backup.ps1` daily 04:00. Needs step 2 first.

## 2. Fix off-box backup SSH trust — `setup_offbox_backup_trust.ps1`
`pull_offbox_backup.ps1` currently fails with *Host key verification failed* (the DB box key
isn't in Administrator's known_hosts), so the "second physical machine = off-box copy" doesn't
exist yet. Run **once as Administrator**:
```
powershell -ExecutionPolicy Bypass -File C:\Broker-crm\ops\setup_offbox_backup_trust.ps1
```
It adds the host key, then verifies unattended SSH and that dumps actually exist on the DB box.
**Also verify the DB box's own 03:00 cron is producing dumps** (this is the primary backup):
```
ssh root@199.247.6.189 "ls -la /var/backups/broker_crm | tail -5"
```
If that list is empty or stale, the daily backup is broken and needs fixing on the DB box —
that's the single most important item in this whole review.

## 3. Bind internal services to localhost (manual edit, needs a restart)
Backend `:8000` and the MT5 bridge `:5000` currently bind `0.0.0.0` — only the Windows firewall
stands between them and the internet. nginx's upstream is already `127.0.0.1:8000` (verified),
so binding the backend to localhost is safe. Change the two launch scripts:

- `restart_backend.ps1` line 26 and `start_core.ps1` (the uvicorn Start-Process): change
  `--host 0.0.0.0` → `--host 127.0.0.1`.
- `bridge.py` (`app.run(...)`): set `host="127.0.0.1"` (all its consumers — mt4_loop, copy
  engine — are on this box). Takes effect on the next bridge restart.

Takes effect on the next backend/bridge restart. Do this together with the security restart.

## 4. Restore the MT4 manager DLL (blocking, needs the file)
`backend\mtmanapi64.dll` is gone. `mt4_loop.py` only works because it holds an open handle;
its next restart permanently kills MT4 sync (and `mt4_journal_worker` is already dead). Copy
`mtmanapi64.dll` back into `C:\Broker-crm\backend\` from wherever the original is (the laptop /
MT4 manager install), then restart the bridges. Cannot be scripted from here — the file isn't
on the box.

## 5. Rotate the Yeastar PBX credentials
The PBX client id/secret were committed to git history (now moved to the gitignored
`yeastar_config.py`). Rotate the OpenAPI app credentials in the Yeastar console and update
`yeastar_config.py`. Optionally scrub history later, but rotation is the real fix.

## Also pending (from the security review, code side)
The security branch `hardening-fixes-2026-07-06` (commit `b3f1534`) is committed but **not yet
active** — activate it with `restart_backend.ps1`. After restart, confirm staff login and the
client portal still work.
