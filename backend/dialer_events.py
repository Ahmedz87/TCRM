# -*- coding: utf-8 -*-
"""
dialer_events.py — Power Dialer call-status worker (Yeastar P-Series OpenAPI WebSocket).

WHAT IT DOES
  Holds a persistent WebSocket to the PBX and turns real call events into automatic dialer
  actions, so agents don't click "No answer / Answered" for every call:
    * customer ANSWERS   -> mark the agent's active call 'answered'  (frontend rings + pops card)
    * no answer / busy / declined / unreachable -> auto-log the outcome + comment + reschedule
      (via power_dialer_router.apply_outcome) and mark the call so the frontend AUTO-ADVANCES.

  Correlation: POST /dialer/session/{id}/auto-next writes a row in `dialer_active_calls` keyed
  by agent_id, holding the agent's extension (caller) + the customer number (callee). This worker
  matches incoming events to that row by the agent extension / callee number.

RUN
    python dialer_events.py            # normal
    python dialer_events.py --debug    # ALSO append every raw frame to logs/dialer_events_raw.log

CALIBRATION NOTE (READ ME)
  Yeastar's exact subscribe-message shape and event field names can vary slightly by firmware.
  This worker logs raw frames in --debug mode. Run it once with --debug, place one test call,
  look at logs/dialer_events_raw.log, and adjust SUBSCRIBE_MSG / _parse_members() below to match
  the real JSON if needed. Everything else (correlation, apply_outcome, DB) is firmware-agnostic.

  Not auto-started. Add a Task Scheduler entry (like the MT bridges) once calibrated.
"""
import sys, os, io, json, time, asyncio, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import websockets
from sqlalchemy import text
from database import SessionLocal
import yeastar_service
from power_dialer_router import apply_outcome

DEBUG = "--debug" in sys.argv
RAW_LOG = os.path.join(os.path.dirname(__file__), "logs", "dialer_events_raw.log")

# Event type numbers (Yeastar P-Series OpenAPI).
EV_CALL_STATUS  = 30011   # ringing / answered / bye per member
EV_CALL_END     = 30012   # new CDR at hangup: status ANSWERED/NO ANSWER/BUSY/VOICEMAIL
EV_CALL_FAILED  = 30015   # dial failure: reason busy/unreachable/declined/timeout

SUBSCRIBE_MSG = {"topic_list": [EV_CALL_STATUS, EV_CALL_END, EV_CALL_FAILED]}
HEARTBEAT_SECS = 30       # PBX drops idle sockets after 60s

# Map Yeastar failure reasons / CDR statuses -> our outcome enum.
def _reason_to_outcome(reason: str) -> str:
    r = (reason or "").lower()
    if any(k in r for k in ("unreachable", "480", "congestion", "circuit", "channel")):
        return "off"          # switched off / unreachable
    if any(k in r for k in ("busy", "486", "declined", "603", "dnd")):
        return "rejected"
    return "no_answer"        # 408 timeout / no answer / anything else

def _cdr_to_outcome(status: str) -> str:
    s = (status or "").upper()
    if "ANSWER" in s and "NO" not in s:  # ANSWERED
        return "answered"
    if "BUSY" in s:
        return "rejected"
    if "VOICEMAIL" in s or "NO ANSWER" in s:
        return "no_answer"
    return "no_answer"


def _log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)

def _raw(frame):
    if not DEBUG:
        return
    try:
        os.makedirs(os.path.dirname(RAW_LOG), exist_ok=True)
        with open(RAW_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')}  {frame}\n")
    except Exception:
        pass


def _legs(payload):
    """Flatten members[] into leg dicts, tagging each with its kind (extension/outbound/...).
    Calibrated to the live firmware: members = [{"extension":{number,member_status}}] and
    [{"outbound":{from,to,member_status}}]."""
    legs = []
    members = payload.get("members") or payload.get("member") or []
    if isinstance(members, dict):
        members = [members]
    for m in members:
        if not isinstance(m, dict):
            continue
        for k in ("extension", "outbound", "inbound", "trunk"):
            d = m.get(k)
            if isinstance(d, dict):
                leg = dict(d); leg["_kind"] = k; legs.append(leg)
    return legs


def _corr(payload):
    """Extract (agent_ext, callee, cust_answered) from any 30011/30012/30015 payload.
    Real fields: CDR uses top-level call_from/call_to; failure/status use members[].outbound.to
    for the customer and members[].extension.number for the agent leg."""
    agent_ext = ""; callee = ""; cust_answered = False
    cf = str(payload.get("call_from") or "")
    ct = str(payload.get("call_to") or "")
    if cf and cf.isdigit() and len(cf) <= 6:
        agent_ext = cf
    if ct:
        callee = ct
    for leg in _legs(payload):
        num = str(leg.get("number") or "")
        to  = str(leg.get("to") or "")
        st  = str(leg.get("member_status") or leg.get("status") or "").upper()
        if leg["_kind"] == "extension" and num and len(num) <= 6:
            agent_ext = agent_ext or num
        if to and len(to) > 6:
            callee = callee or to
        if st in ("ANSWERED", "ANSWER") and ((to and len(to) > 6) or (num and len(num) > 6)):
            cust_answered = True
    return agent_ext, callee, cust_answered


def _find_active_call(db, agent_ext=None, callee=None):
    """Match an event to a live (non-terminal) dialer_active_calls row."""
    q = """SELECT agent_id, session_id, queue_id, login, lead_id, callee, agent_ext, status
           FROM dialer_active_calls
           WHERE COALESCE(outcome_applied,FALSE)=FALSE AND status IN ('ringing','answered')"""
    rows = db.execute(text(q)).fetchall()
    for r in rows:
        r_ext, r_callee = (r[6] or ""), (r[5] or "")
        if agent_ext and r_ext and str(agent_ext) == str(r_ext):
            return r
        if callee and r_callee and (str(callee).endswith(r_callee[-9:]) or r_callee.endswith(str(callee)[-9:])):
            return r
    return None


def _set_status(db, agent_id, status):
    db.execute(text("UPDATE dialer_active_calls SET status=:s, updated_at=NOW() WHERE agent_id=:a"),
               {"s": status, "a": agent_id})

def _apply_terminal(db, row, outcome):
    """Auto-apply a non-answer outcome (log + comment + reschedule) exactly once."""
    agent_id, sid, qid, login, lead_id = row[0], row[1], row[2], row[3], row[4]
    apply_outcome(db, session_id=sid, queue_id=qid, login=login, lead_id=lead_id,
                  outcome=outcome, comment="", agent_id=agent_id)
    db.execute(text("""UPDATE dialer_active_calls SET status=:s, outcome_applied=TRUE, updated_at=NOW()
                       WHERE agent_id=:a"""), {"s": outcome, "a": agent_id})
    db.commit()
    _log(f"auto-outcome '{outcome}' applied for agent {agent_id} (queue {qid})")


def handle_event(etype, payload):
    """Correlate one event to an active call and drive its status.

    CRITICAL: a customer outcome (no_answer/rejected/off) is applied ONLY when the event
    actually involves the CUSTOMER leg (callee present). A failure that is purely the AGENT's
    own extension (e.g. '486 Busy Here' on ext 390 because the agent's phone didn't auto-answer
    and the customer was never dialed) must NOT be logged against the customer — otherwise the
    dialer burns the queue with false 'rejected' outcomes on people who were never called."""
    db = SessionLocal()
    try:
        agent_ext, callee, cust_answered = _corr(payload)

        if etype == EV_CALL_STATUS:
            if cust_answered and callee:
                row = _find_active_call(db, callee=callee)
                if row:
                    _set_status(db, row[0], "answered"); db.commit()
                    _log(f"customer answered -> agent {row[0]} card pops")
            return

        if etype == EV_CALL_FAILED:
            if not callee:
                # Agent-leg-only failure: the agent's phone was busy/declined and the customer
                # was NOT dialed. Flag the agent's slot so the UI can say "your phone didn't
                # pick up" — but do NOT log a customer outcome.
                if agent_ext:
                    row = _find_active_call(db, agent_ext=agent_ext)
                    if row:
                        _set_status(db, row[0], "agent_no_answer"); db.commit()
                        _log(f"agent leg failed (ext {agent_ext}) — NOT logged against customer")
                return
            row = _find_active_call(db, callee=callee)
            if row:
                _apply_terminal(db, row, _reason_to_outcome(str(payload.get("reason") or "")))
            return

        if etype == EV_CALL_END:  # CDR = authoritative final outcome; always carries call_to
            if not callee:
                return
            row = _find_active_call(db, callee=callee)
            if not row:
                return
            outcome = _cdr_to_outcome(str(payload.get("status") or ""))
            talk = int(payload.get("talk_duration") or 0)
            if outcome == "answered" and talk > 0:
                _set_status(db, row[0], "answered"); db.commit()   # agent closes via Done/callback
            else:
                _apply_terminal(db, row, outcome if outcome != "answered" else "no_answer")
            return
    except Exception:
        db.rollback()
        _log("handle_event error:\n" + traceback.format_exc())
    finally:
        db.close()


def _extract(frame):
    """Return (etype:int|None, payload:dict) from a raw WS frame."""
    try:
        obj = json.loads(frame)
    except Exception:
        return None, {}
    # event type may be under 'type'/'sn'/'topic'; payload under 'msg'/'data'/itself
    etype = obj.get("type") or obj.get("topic") or obj.get("event")
    try:
        etype = int(etype)
    except Exception:
        etype = None
    payload = obj.get("msg") or obj.get("data") or obj
    if isinstance(payload, str):
        try: payload = json.loads(payload)
        except Exception: payload = {}
    return etype, (payload if isinstance(payload, dict) else {})


async def _heartbeat(ws):
    # Keepalive. IMPORTANT: re-send the FULL topic list, never an empty one — sending
    # {"topic_list": []} re-subscribes to NOTHING and silently kills the event stream after
    # the first heartbeat (observed on this firmware: events stopped 30s after connect).
    while True:
        await asyncio.sleep(HEARTBEAT_SECS)
        try:
            await ws.send(json.dumps(SUBSCRIBE_MSG))
        except Exception:
            return


CONNECTION_LIFETIME = 1200   # reconnect every 20 min with a FRESH token (PBX tokens expire ~30 min)


async def run_once(force_token=False):
    # Always start a connection on a fresh/valid token. If we're reconnecting because the PBX
    # said TOKEN EXPIRED, force a full re-login (the time-based cache can still look valid).
    token, host = yeastar_service.get_token_and_host(force=force_token)
    if not token:
        _log("no PBX token; retrying"); return False
    url = f"wss://{host}/openapi/v1.0/subscribe?access_token={token}"
    _log(f"connecting {host} ...")
    start = time.monotonic()
    async with websockets.connect(url, ssl=yeastar_service._CTX, ping_interval=None) as ws:
        await ws.send(json.dumps(SUBSCRIBE_MSG))
        _log("subscribed to 30011/30012/30015")
        hb = asyncio.create_task(_heartbeat(ws))
        try:
            async for frame in ws:
                _raw(frame)
                # PBX rejects the token on the open socket -> reconnect with a fresh one.
                if '"errcode":10004' in frame or "TOKEN EXPIRED" in frame:
                    _log("PBX token expired -> reconnecting with a fresh token")
                    return True
                # Proactively refresh before the ~30-min expiry so we never go deaf.
                if time.monotonic() - start > CONNECTION_LIFETIME:
                    _log("proactive token refresh (20 min) -> reconnecting")
                    return True
                etype, payload = _extract(frame)
                if etype in (EV_CALL_STATUS, EV_CALL_END, EV_CALL_FAILED):
                    handle_event(etype, payload)
        finally:
            hb.cancel()
    return False


async def main():
    _log(f"dialer_events worker starting (debug={DEBUG})")
    force = False
    while True:
        try:
            force = bool(await run_once(force_token=force))
        except Exception:
            _log("connection error:\n" + traceback.format_exc())
            force = True   # a dropped connection is often auth-related; re-login on reconnect
        await asyncio.sleep(3)   # reconnect backoff


if __name__ == "__main__":
    asyncio.run(main())
