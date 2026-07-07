"""
Power Dialer Router
Manages dialer sessions, call queue, call logs and smart rescheduling
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import models, auth
from database import get_db
from auth import get_current_user
import yeastar_service
import rbac

router = APIRouter(prefix="/dialer", tags=["dialer"])


# ── DYNAMIC PRIORITY SCORE ────────────────────────────────────────────────
# The queue is ranked top-first by a live priority score that:
#   • is ~0 right after a contact is called (last_call_at = now resets the time ramp), and
#   • ramps linearly back to 100 over 14 days  -> everyone re-surfaces to the top by day 14
#   • plus urgent "event" bonuses that push high-value cases straight to the top NOW.
# Sales just works the top of the list; acting on a contact zeroes it and it climbs back.
TIME_RAMP_DAYS = 14

# clients/IBs: 14-day ramp + financial-urgency bonuses
def CLIENT_PRIORITY(alias="c"):
    c = alias
    return f"""(
        LEAST(EXTRACT(EPOCH FROM (NOW() - COALESCE({c}.last_call_at::timestamptz, NOW() - INTERVAL '{TIME_RAMP_DAYS} days')))
              / ({TIME_RAMP_DAYS}*86400.0), 1.0) * 100
        + CASE WHEN EXISTS (SELECT 1 FROM transactions t WHERE t.login={c}.login
                 AND t.tx_type IN ('deposit','bonus_deposit') AND lower(COALESCE(t.status,''))='rejected'
                 AND t.created_at > COALESCE({c}.last_call_at::timestamptz,'epoch'::timestamptz)) THEN 60 ELSE 0 END
        + CASE WHEN EXISTS (SELECT 1 FROM transactions t WHERE t.login={c}.login
                 AND t.tx_type IN ('withdrawal','bonus_withdrawal') AND lower(COALESCE(t.status,''))='pending'
                 AND t.created_at > COALESCE({c}.last_call_at::timestamptz,'epoch'::timestamptz)) THEN 50 ELSE 0 END
        + CASE WHEN {c}.margin_level > 0 AND {c}.margin_level <= 100 THEN 70 ELSE 0 END
        + CASE WHEN COALESCE({c}.total_deposits,0) = 0 AND COALESCE({c}.last_login_at,'') <> '' THEN 40 ELSE 0 END
    )"""

# Lead priority lifecycle:
#   • NOT yet answered (brand-new OR called-but-not-connected) -> 100  (top of the dialer:
#       fresh leads get called first, and we keep trying until someone actually answers)
#   • once first ANSWERED (first_connected_at is set)          -> drop the 100, fall back to
#       "other parameters": 14-day re-call ramp + the lead's quality score.
def LEAD_PRIORITY(alias="l"):
    l = alias
    return f"""(CASE
        WHEN {l}.first_connected_at IS NOT NULL THEN
            LEAST(EXTRACT(EPOCH FROM (NOW() - COALESCE({l}.last_call_at::timestamptz, NOW() - INTERVAL '{TIME_RAMP_DAYS} days')))
                  / ({TIME_RAMP_DAYS}*86400.0), 1.0) * 100
            + COALESCE({l}.score,0)
        ELSE 100
    END)"""


def _ensure_dialer_cols():
    """Ensure the dialer columns exist WITHOUT ever blocking app startup.

    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` still grabs an ACCESS EXCLUSIVE lock even
    when the column already exists. Running it unconditionally at import meant that if any
    other session held `clients`/`leads` (e.g. the MT bridge mid-write), every uvicorn boot
    hung forever waiting for the lock -> total login outage. So we (a) only ALTER columns
    that are actually MISSING (steady state = zero ALTERs, zero locks), and (b) set a short
    lock_timeout so a contended ALTER fails fast instead of freezing the whole app.
    """
    from database import SessionLocal
    want = {
        "clients": [("last_call_at", "TIMESTAMP"), ("last_call_outcome", "VARCHAR(20)"), ("first_connected_at", "TIMESTAMP")],
        "leads":   [("last_call_at", "TIMESTAMP"), ("last_call_outcome", "VARCHAR(20)"), ("first_connected_at", "TIMESTAMP")],
    }
    db = SessionLocal()
    try:
        existing = {(r[0], r[1]) for r in db.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_name IN ('clients','leads')"
        )).fetchall()}
        missing = [(t, c, typ) for t, cols in want.items() for (c, typ) in cols if (t, c) not in existing]
        if not missing:
            return  # all present — take NO lock, never block boot
        db.execute(text("SET lock_timeout = '4s'"))
        for t, c, typ in missing:   # table/col/type are hardcoded literals above (no injection)
            db.execute(text(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {c} {typ}"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

_ensure_dialer_cols()


# ── YEASTAR CLICK-TO-CALL ─────────────────────────────────────────────────
@router.post("/call")
def place_call(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Place a click-to-call through the Yeastar cloud PBX. Rings the agent's
    extension first, then dials the client/lead number.
    Body: {"phone": "+9647...", "extension": "101"(optional)}
    """
    phone = (data.get("phone") or "").strip()
    if not phone:
        return {"ok": False, "error": "no phone number"}
    # The logged-in user's own extension is the source of truth (follows them across
    # browsers). Fall back to an explicit body value.
    ext = (getattr(current_user, "extension", None) or "").strip()
    if not ext:
        ext = (data.get("extension") or "").strip()
    if ext in ("", "100", "TOKEN", "YOUR_YEASTAR_IP"):
        ext = None
    # SAFETY: never silently fall back to DEFAULT_CALLER_EXT (101). That extension belongs to a
    # real person (the owner), so an unmapped agent dialing would ring the OWNER's phone, the
    # agent would never connect, and every such call ended up logged as "no answer" (this was the
    # single biggest cause of the dialer's ~99% no-answer rate). Refuse instead and tell the agent.
    if not ext:
        return {"ok": False, "error": "no_extension",
                "errmsg": "Set your PBX extension in Settings before dialing (your click-to-call has no extension mapped)."}
    res = yeastar_service.dial(phone, caller=ext)
    ok = isinstance(res, dict) and res.get("errcode") == 0
    return {
        "ok": ok,
        "caller": ext or yeastar_service.DEFAULT_CALLER_EXT,
        "errcode": (res or {}).get("errcode"),
        "errmsg": (res or {}).get("errmsg"),
    }


@router.get("/extensions")
def extensions(current_user: models.User = Depends(get_current_user)):
    """List PBX extensions (for the agent extension picker in Settings)."""
    return {"extensions": yeastar_service.list_extensions()}


@router.get("/my-extension")
def get_my_extension(current_user: models.User = Depends(get_current_user)):
    """The logged-in agent's mapped PBX extension (what their click-to-call rings)."""
    return {"extension": getattr(current_user, "extension", None) or ""}


@router.post("/my-extension")
def set_my_extension(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Map the logged-in agent to a PBX extension (e.g. '101')."""
    ext = "".join(ch for ch in str(data.get("extension") or "") if ch.isdigit())
    db.execute(text("UPDATE users SET extension=:e WHERE id=:id"),
               {"e": ext or None, "id": current_user.id})
    db.commit()
    return {"ok": True, "extension": ext}

# ── SMART RESCHEDULE LOGIC ────────────────────────────────────────────────
def next_retry_time(attempt: int, first_called_at: datetime, call_time_hour: int) -> datetime | None:
    """
    Reschedule ladder for unanswered / switched-off / rejected calls:
      attempt 1 → +30 min
      attempt 2 → +1 hour
      attempt 3 → +2 hours
      attempt 4 → +24 hours
      attempt 5 → +2 days
      attempt 6+ → weekly (every 7 days)
      attempt 12+ → None (stop)
    """
    now = datetime.utcnow()
    if attempt == 1: return now + timedelta(minutes=30)
    if attempt == 2: return now + timedelta(hours=1)
    if attempt == 3: return now + timedelta(hours=2)
    if attempt == 4: return now + timedelta(hours=24)
    if attempt == 5: return now + timedelta(days=2)
    if attempt <= 11: return now + timedelta(days=7)   # weekly thereafter
    return None  # give up after ~6 weekly attempts

# ── CREATE SESSION ────────────────────────────────────────────────────────
@router.post("/session/start")
def start_session(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Start a new dialer session with a list of logins to call."""
    logins   = data.get("logins", [])     # for clients
    lead_ids = data.get("lead_ids", [])   # for leads
    source   = data.get("source", "clients")  # 'clients' or 'leads'
    filters  = data.get("filters", {})
    items    = logins if source == "clients" else lead_ids
    if not items:
        return {"error": "No items provided"}

    # AI-owned (WhatsApp AI) contacts are worked by the assistant — never dial them.
    try:
        col = "login" if source == "clients" else "id"
        tbl = "clients" if source == "clients" else "leads"
        ai_rows = db.execute(text(
            f"SELECT {col} FROM {tbl} WHERE {col} = ANY(:ids) AND COALESCE(ai_managed,FALSE)=TRUE"
        ), {"ids": items}).fetchall()
        ai_owned = {r[0] for r in ai_rows}
        if ai_owned:
            items = [i for i in items if i not in ai_owned]
        if not items:
            return {"error": "All selected contacts are AI-managed (handled by the WhatsApp assistant)"}
    except Exception:
        db.rollback()

    # Role-based safety net: an agent can only dial their own (team's) contacts, even if
    # the client somehow sent more. Preserves the original order.
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        col = "login" if source == "clients" else "id"
        tbl = "clients" if source == "clients" else "leads"
        rows = db.execute(text(
            f"SELECT {col} FROM {tbl} WHERE {col} = ANY(:ids) AND assigned_agent_id = ANY(:sc)"
        ), {"ids": items, "sc": _scope or [-1]}).fetchall()
        allowed = {r[0] for r in rows}
        items = [i for i in items if i in allowed]
        if not items:
            return {"error": "No assigned contacts to dial"}

    result = db.execute(text("""
        INSERT INTO dialer_sessions (agent_id, status, filters, total, source, created_at)
        VALUES (:agent, 'active', :filters, :total, :source, NOW())
        RETURNING id
    """), {"agent": current_user.id, "filters": str(filters), "total": len(items), "source": source})
    session_id = result.fetchone()[0]

    for pos, item_id in enumerate(items):
        if source == "clients":
            db.execute(text("""
                INSERT INTO dialer_queue (session_id, login, position, status, attempt, created_at)
                VALUES (:sid, :login, :pos, 'pending', 0, NOW())
            """), {"sid": session_id, "login": item_id, "pos": pos})
        else:
            db.execute(text("""
                INSERT INTO dialer_queue (session_id, lead_id, position, status, attempt, created_at)
                VALUES (:sid, :lead_id, :pos, 'pending', 0, NOW())
            """), {"sid": session_id, "lead_id": item_id, "pos": pos})

    db.commit()
    return {"session_id": session_id, "total": len(items)}

# ── GET NEXT CLIENT TO CALL ───────────────────────────────────────────────
@router.get("/session/{session_id}/next")
def get_next(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get the next client to call in the queue."""
    # Check session source
    sess = db.execute(text("SELECT source FROM dialer_sessions WHERE id=:sid"), {"sid": session_id}).fetchone()
    source = sess[0] if sess else "clients"

    if source == "leads":
        row = db.execute(text("""
            SELECT q.id, q.lead_id, q.attempt, l.full_name, l.phone, l.country, l.city,
                   0, 0, 0, NULL, q.scheduled_at,
                   l.campaign_name, l.source,
                   COALESCE(NULLIF(l.meta_created::text,''), l.created_at::text),
                   l.notes
            FROM dialer_queue q
            JOIN leads l ON l.id = q.lead_id
            WHERE q.session_id = :sid
              AND q.status = 'pending'
              AND (q.scheduled_at IS NULL OR q.scheduled_at <= NOW())
            ORDER BY
                -- due callbacks first, then highest dynamic priority, then queue order
                CASE WHEN q.scheduled_at IS NOT NULL AND q.scheduled_at <= NOW() THEN 0 ELSE 1 END ASC,
                """ + LEAD_PRIORITY("l") + """ DESC,
                q.position ASC
            LIMIT 1
        """), {"sid": session_id}).fetchone()
    else:
        row = db.execute(text("""
            SELECT q.id, q.login, q.attempt, c.name, c.phone, c.country, c.city,
                   c.balance, c.equity, c.total_deposits, c.last_deposit_at,
                   q.scheduled_at,
                   (SELECT campaign_name FROM leads WHERE matched_login = c.login
                        AND campaign_name IS NOT NULL ORDER BY id LIMIT 1),
                   c.source,
                   COALESCE(NULLIF(c.reg_date::text,''), c.created_at::text),
                   (SELECT comment FROM dialer_call_logs WHERE login = c.login
                        AND COALESCE(comment,'') <> '' ORDER BY called_at DESC LIMIT 1)
            FROM dialer_queue q
            JOIN clients c ON c.login = q.login
            WHERE q.session_id = :sid
              AND q.status = 'pending'
              AND (q.scheduled_at IS NULL OR q.scheduled_at <= NOW())
            ORDER BY
                -- Rescheduled clients due now get top priority
                CASE WHEN q.scheduled_at IS NOT NULL AND q.scheduled_at <= NOW()
                     THEN 0 ELSE 1 END ASC,
                -- Then by dynamic priority (14-day ramp + financial-urgency bonuses)
                """ + CLIENT_PRIORITY("c") + """ DESC,
                -- Then original queue position
                q.position ASC
            LIMIT 1
        """), {"sid": session_id}).fetchone()

    if not row:
        # Check if there are scheduled ones coming up
        upcoming = db.execute(text("""
            SELECT MIN(scheduled_at) FROM dialer_queue
            WHERE session_id = :sid AND status = 'pending' AND scheduled_at > NOW()
        """), {"sid": session_id}).scalar()
        return {"done": True, "next_scheduled_at": str(upcoming) if upcoming else None}

    return {
        "queue_id":       row[0],
        "login":          row[1],
        "lead_id":        row[1] if source=="leads" else None,
        "source":         source,
        "attempt":        row[2],
        "name":           row[3],
        "phone":          row[4],
        "country":        row[5],
        "city":           row[6],
        "balance":        float(row[7] or 0),
        "equity":         float(row[8] or 0),
        "total_deposits": float(row[9] or 0),
        "last_deposit":   str(row[10] or ""),
        "scheduled_at":   str(row[11] or ""),
        "campaign":       row[12] or "",
        "channel":        row[13] or "",
        "reg_date":       str(row[14] or ""),
        "last_comment":   (row[15] or "").strip(),
    }

# ── LOG CALL RESULT ───────────────────────────────────────────────────────
@router.post("/call/result")
def log_call_result(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Log the result of a call attempt.
    outcome: 'answered' | 'no_answer' | 'rejected' | 'off' | 'call_later' | 'done'
    """
    queue_id   = data.get("queue_id")
    session_id = data.get("session_id")
    login      = data.get("login")
    outcome    = data.get("outcome")  # answered/no_answer/rejected/off/call_later/done
    comment    = data.get("comment", "")
    call_later_at = data.get("call_later_at")  # ISO string if call_later

    now = datetime.utcnow()

    # Get current attempt
    row = db.execute(text("""
        SELECT attempt, created_at FROM dialer_queue WHERE id = :qid
    """), {"qid": queue_id}).fetchone()
    attempt = (row[0] if row else 0) + 1
    first_call_hour = (row[1].hour if row and row[1] else now.hour)

    # Auto-comments for non-answered calls
    auto_comments = {
        "no_answer": f"[Power Dialer] No answer — attempt {attempt}. Auto-scheduled for retry.",
        "rejected":  f"[Power Dialer] Call rejected by client — attempt {attempt}. Auto-scheduled for retry.",
        "off":       f"[Power Dialer] Phone switched off — attempt {attempt}. Auto-scheduled for retry.",
        "answered":  f"[Power Dialer] Connected — {comment}" if comment else "[Power Dialer] Connected.",
        "done":      f"[Power Dialer] Connected & done — {comment}" if comment else "[Power Dialer] Connected & closed.",
        "call_later": f"[Power Dialer] Client requested callback. Scheduled for {call_later_at}. Note: {comment}",
    }
    final_comment = comment if outcome in ("answered", "done") and comment else auto_comments.get(outcome, comment)

    # Log call
    db.execute(text("""
        INSERT INTO dialer_call_logs (session_id, login, queue_id, agent_id, outcome, comment, called_at)
        VALUES (:sid, :login, :qid, :agent, :outcome, :comment, NOW())
    """), {
        "sid": session_id, "login": login, "qid": queue_id,
        "agent": current_user.id, "outcome": outcome, "comment": final_comment
    })

    # Reset the dynamic priority for this contact (whatever the outcome): being called
    # zeroes the 14-day ramp + clears event bonuses, so they drop off the top and climb back.
    # short outcome label for the "Last call" column (answered/done -> connected)
    short_outcome = {"answered": "connected", "done": "connected"}.get(outcome, outcome)
    connected = short_outcome == "connected"   # the first real ANSWER ends the 100-pt boost
    lead_id = data.get("lead_id")
    if lead_id:
        db.execute(text("""UPDATE leads SET last_call_at = NOW(), last_call_outcome = :oc,
                           first_connected_at = COALESCE(first_connected_at, CASE WHEN :conn THEN NOW() END)
                           WHERE id = :lid"""),
                   {"oc": short_outcome, "conn": connected, "lid": lead_id})
    elif login:
        db.execute(text("""UPDATE clients SET last_call_at = NOW(), last_call_outcome = :oc,
                           first_connected_at = COALESCE(first_connected_at, CASE WHEN :conn THEN NOW() END)
                           WHERE login = :l"""),
                   {"oc": short_outcome, "conn": connected, "l": login})

    # Save call action to timeline (client or lead)
    if lead_id:
        # Save to lead notes as a clean, dated line (was double-bracketed "[[Power Dialer]...]").
        db.execute(text("""
            UPDATE leads SET notes = CONCAT(COALESCE(notes,''), :nl, :note), updated_at=NOW()
            WHERE id = :lid
        """), {"nl": "\n", "note": f"{now:%Y-%m-%d %H:%M} · {final_comment}", "lid": lead_id})
    elif login:
        db.execute(text("""
            INSERT INTO call_actions (login, agent_id, action, note, created_at)
            VALUES (:login, :agent, :action, :note, NOW())
        """), {
            "login": login, "agent": current_user.id,
            "action": f"dialer_{outcome}", "note": final_comment
        })

    # Determine next queue status
    if outcome == "done":
        # Fully done — remove from queue
        db.execute(text("UPDATE dialer_queue SET status='done', attempt=:a WHERE id=:qid"),
                   {"a": attempt, "qid": queue_id})

    elif outcome == "call_later":
        # Agent chose specific time — reschedule to top
        scheduled = datetime.fromisoformat(call_later_at) if call_later_at else now + timedelta(hours=1)
        db.execute(text("""
            UPDATE dialer_queue SET status='pending', attempt=:a, scheduled_at=:s, position=-1
            WHERE id=:qid
        """), {"a": attempt, "s": scheduled, "qid": queue_id})

    elif outcome in ("no_answer", "rejected", "off"):
        # Smart reschedule
        next_time = next_retry_time(attempt, now, first_call_hour)
        if next_time:
            db.execute(text("""
                UPDATE dialer_queue SET status='pending', attempt=:a, scheduled_at=:s
                WHERE id=:qid
            """), {"a": attempt, "s": next_time, "qid": queue_id})
        else:
            # Max attempts reached — mark done
            db.execute(text("UPDATE dialer_queue SET status='max_attempts', attempt=:a WHERE id=:qid"),
                       {"a": attempt, "qid": queue_id})
            db.execute(text("""
                INSERT INTO call_actions (login, agent_id, action, note, created_at)
                VALUES (:login, :agent, 'dialer_max_attempts',
                'Power Dialer: max call attempts reached. Removed from queue.', NOW())
            """), {"login": login, "agent": current_user.id})

    elif outcome == "answered":
        # Just answered — wait for done
        db.execute(text("UPDATE dialer_queue SET attempt=:a WHERE id=:qid"),
                   {"a": attempt, "qid": queue_id})

    db.commit()
    return {"ok": True, "comment": final_comment, "attempt": attempt}


# ── GET QUEUE LIST ────────────────────────────────────────────────────────
@router.get("/session/{session_id}/queue")
def get_queue(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get full queue list for preview panel."""
    # Check session source
    sess = db.execute(text("SELECT source FROM dialer_sessions WHERE id=:sid"), {"sid": session_id}).fetchone()
    source = sess[0] if sess else "clients"

    if source == "leads":
        rows = db.execute(text("""
            SELECT q.id, q.lead_id, q.position, l.full_name, l.phone, l.country, 0, 0
            FROM dialer_queue q
            JOIN leads l ON l.id = q.lead_id
            WHERE q.session_id = :sid AND q.status = 'pending'
            ORDER BY q.position ASC
            LIMIT 99999
        """), {"sid": session_id}).fetchall()
    else:
        rows = db.execute(text("""
            SELECT q.id, q.login, q.position, c.name, c.phone, c.country, c.balance, c.total_deposits
            FROM dialer_queue q
            JOIN clients c ON c.login = q.login
            WHERE q.session_id = :sid AND q.status = 'pending'
            ORDER BY q.position ASC
            LIMIT 99999
        """), {"sid": session_id}).fetchall()

    return {"items": [
        {"queue_id": r[0], "login": r[1], "position": r[2],
         "name": r[3], "phone": r[4], "country": r[5],
         "balance": float(r[6] or 0), "total_deposits": float(r[7] or 0)}
        for r in rows
    ]}

# ── SESSION STATS ─────────────────────────────────────────────────────────
@router.get("/session/{session_id}/stats")
def session_stats(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status='pending') as pending,
            COUNT(*) FILTER (WHERE status='done') as done,
            COUNT(*) FILTER (WHERE status='max_attempts') as exhausted,
            COUNT(*) as total
        FROM dialer_queue WHERE session_id = :sid
    """), {"sid": session_id}).fetchone()
    return {
        "pending": row[0], "done": row[1],
        "exhausted": row[2], "total": row[3]
    }

# ── STOP SESSION ─────────────────────────────────────────────────────────
@router.post("/session/{session_id}/stop")
def stop_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db.execute(text("UPDATE dialer_sessions SET status='stopped' WHERE id=:sid"),
               {"sid": session_id})
    # Purge this session's queue rows. Without this, every stopped session left its whole
    # contact list behind as 'pending' forever — the queue had grown to ~876k orphan rows.
    # All outcomes are already persisted to dialer_call_logs + the client/lead timeline, so
    # nothing is lost by clearing the transient queue.
    db.execute(text("DELETE FROM dialer_queue WHERE session_id=:sid"), {"sid": session_id})
    db.commit()
    return {"ok": True}

# ── CALL HISTORY ─────────────────────────────────────────────────────────
@router.get("/history")
def call_history(
    page: int = Query(1), page_size: int = Query(20),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    offset = (page - 1) * page_size
    rows = db.execute(text("""
        SELECT l.id, l.login, c.name, l.outcome, l.comment, l.called_at, u.full_name as agent
        FROM dialer_call_logs l
        LEFT JOIN clients c ON c.login = l.login
        LEFT JOIN users u ON u.id = l.agent_id
        ORDER BY l.called_at DESC
        LIMIT :lim OFFSET :off
    """), {"lim": page_size, "off": offset}).fetchall()
    return {"logs": [{"id":r[0],"login":r[1],"name":r[2],"outcome":r[3],
                      "comment":r[4],"called_at":str(r[5]),"agent":r[6]} for r in rows]}
