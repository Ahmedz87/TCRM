# Power Dialer — auto-flow (event-driven) activation guide

This is the "run it and it dials by itself" rebuild. What changed and how to turn it on.

## What it does now
- Click **Power Dial** → the backend auto-dials each contact with **agent-leg auto-answer**
  (no "accept the call" popup), places the call, and records it as the agent's active call.
- A background worker (`dialer_events.py`) listens to Yeastar's real call events and drives it:
  - **no answer / busy / declined / unreachable** → auto-writes the comment, reschedules per the
    retry ladder, drops the contact down the list, and the UI **advances to the next call by itself**.
  - **customer answers** → the UI rings + pops the customer card; the agent talks and clicks
    **Done** or **Schedule callback**.
- If the worker is down, the UI falls back to the old manual buttons — nothing breaks.

## The one thing Yeastar can't do
No answering-machine detection. A call that reaches voicemail or a carrier "switched-off"
recording counts as *answered*, so the agent will occasionally get popped for a machine. That's
the only gap vs. the ideal, and it would require Twilio/Telnyx/Asterisk to close.

## Activation steps (in order)
1. **Fix agent extensions** (still pending). Until an agent has a correct `users.extension`, the
   dialer refuses to dial for them (by design — it used to ring the owner's phone). See the
   extension-mapping proposal.
2. **Enable auto-answer for the agent extensions on the PBX** — Linkus admin → auto-answer for
   UC clients, OR ensure the desk phones honor the auto-answer header. Without this the agent
   still has to accept each call. (Yeastar setting, your side.)
3. **Restart the backend** so the new endpoints load (`/dialer/session/{id}/auto-next`,
   `/dialer/active-call`) and `dialer_active_calls` is created:
   `powershell -File C:\Broker-crm\restart_backend.ps1`
4. **Calibrate the event worker once** (Yeastar's exact event JSON varies by firmware):
   - Run: `cd C:\broker-crm\backend; .\venv\Scripts\python.exe dialer_events.py --debug`
   - Place ONE test call through the dialer.
   - Look at `backend\logs\dialer_events_raw.log` — confirm the events arrive and that the
     `SUBSCRIBE_MSG` shape + `_parse_members()` field names in `dialer_events.py` match the real
     JSON. Adjust if needed (the correlation/DB logic is firmware-agnostic; only the wire shape
     might differ).
5. **Run the worker for real** and keep it alive:
   `.\venv\Scripts\python.exe dialer_events.py`
   Then register a Task Scheduler entry like the MT bridges so it auto-starts (it needs to run
   continuously). It is intentionally NOT auto-started yet.

## One-time queue cleanup (optional, safe)
The queue had grown to ~876k orphaned 'pending' rows from old sessions (now purged on stop going
forward). To clear the existing backlog for already-stopped sessions:
```sql
DELETE FROM dialer_queue q USING dialer_sessions s
WHERE q.session_id = s.id AND s.status = 'stopped';
```
All outcomes are preserved in `dialer_call_logs` + the client/lead timeline, so this only drops
transient queue rows.

## Also recommended
- **Cap session size.** Sessions have been launched over the entire 164k-lead list. Add a cap
  (e.g. top 200 by priority) in `DialerLauncher.fetchAllLogins` so a run is workable.
