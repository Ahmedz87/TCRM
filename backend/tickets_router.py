"""
Internal ticketing / feedback system.
- Staff (CRM) create tickets via a pinned red button on every page: which section,
  a screenshot (pasted/uploaded, downscaled client-side), a note, and a critical level.
- Portal clients (currently all test users) create tickets the same way.
- The live chat lets a tester leave an "operator note" telling the AI bot how to answer;
  those (for_ai=TRUE, not done) are fed into the bot's system prompt (ai_operator_notes()).
- One Tickets page (any staff) lists ALL tickets with status workflow:
  under_review -> proceed -> done.

Screenshots are stored as a downscaled data URL in the `screenshot` TEXT column (kept
small client-side to stay under nginx's body limit). Table auto-creates on import.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, SessionLocal
from auth import get_current_user
from portal_router import get_current_client

VALID_CRIT = ("low", "medium", "high", "critical")
# 'answered' = action taken / replied, waiting on the ticket maker. Only the MAKER closes (done).
# 'rejected' = an admin declined the request (approval workflow).
VALID_STATUS = ("under_review", "proceed", "answered", "done", "rejected")
ADMIN_ROLES = ("super_admin", "admin", "director")


def _is_admin(user) -> bool:
    return getattr(user, "role", "") in ADMIN_ROLES


# Customer-care handlers: a staff member who fully handles (sees / replies / closes) the
# tickets raised by specific CLIENT creators — even though they didn't create them and they
# weren't transferred. Maps staff email -> the client emails whose tickets they own.
# (bakera@tnfx.co handles baker@tnfx.co's tickets — requested by the desk.)
CARE_HANDLERS = {
    "bakera@tnfx.co": ["baker@tnfx.co"],
}

# Manual ticket creation is DISABLED for everyone (tickets come via the assistant chat / WhatsApp
# '#' path) EXCEPT these allowlisted staff emails — a desk-granted exception. Lowercase.
TICKET_CREATE_ALLOW = {"abbask@tnfx.co"}


def can_create_ticket(user) -> bool:
    """True if this staff user is allowed to create tickets manually (allowlist exception)."""
    return (getattr(user, "email", "") or "").lower() in TICKET_CREATE_ALLOW


def _handled_creator_ids(db, user) -> list:
    """Client creator_ids whose tickets `user` may handle (review/reply/close). Resolved
    from CARE_HANDLERS by email at call time, so it tracks the live clients table."""
    emails = CARE_HANDLERS.get((getattr(user, "email", "") or "").lower())
    if not emails:
        return []
    rows = db.execute(text(
        "SELECT id FROM clients WHERE LOWER(email) = ANY(:e)"
    ), {"e": [x.lower() for x in emails]}).fetchall()
    return [int(r[0]) for r in rows]


def _handles_ticket(db, user, tid) -> bool:
    """True if `user` is a designated care handler for THIS ticket's client creator —
    so they get the same approve/review/close rights an admin has, but only on the
    specific clients assigned to them (e.g. bakera@tnfx.co on baker@tnfx.co's tickets)."""
    handled = _handled_creator_ids(db, user)
    if not handled:
        return False
    row = db.execute(text("SELECT creator_type, creator_id FROM tickets WHERE id=:i"), {"i": tid}).fetchone()
    return bool(row and row[0] == "client" and int(row[1] or 0) in handled)


def _ensure_table():
    db = SessionLocal()
    try:
        # Fail fast on lock contention so a backend restart can never hang here (steady state
        # the tables/cols already exist, so any timeout is harmless — except() rolls back).
        db.execute(text("SET lock_timeout = '4s'"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                source VARCHAR(12) DEFAULT 'admin',        -- admin | portal | chat
                creator_type VARCHAR(12),                  -- staff | client | bot
                creator_id INT,
                creator_name VARCHAR(160),
                section VARCHAR(120),
                note TEXT,
                critical VARCHAR(12) DEFAULT 'medium',     -- low|medium|high|critical
                route VARCHAR(12),                         -- review | fix  (creator chooses; no default)
                screenshot TEXT,                           -- downscaled data URL (nullable)
                page_url VARCHAR(400),
                for_ai BOOLEAN DEFAULT FALSE,
                status VARCHAR(16) DEFAULT 'under_review', -- under_review|proceed|done
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS route VARCHAR(12)"))
        db.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS admin_unread BOOLEAN DEFAULT FALSE"))
        db.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS needs_approval BOOLEAN DEFAULT FALSE"))
        db.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT FALSE"))
        db.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS assigned_to INT"))        # transferred-to staff user id
        db.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS assigned_to_name VARCHAR(160)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_tickets_forai ON tickets(for_ai, status)"))
        # conversation thread on each ticket (staff/AI replies + maker replies)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS ticket_replies (
                id SERIAL PRIMARY KEY,
                ticket_id INT NOT NULL,
                author_type VARCHAR(12),   -- staff | client | ai
                author_name VARCHAR(160),
                body TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_treplies_tid ON ticket_replies(ticket_id)"))
        # staff can attach a photo to a reply (downscaled data URL), like the ticket screenshot
        db.execute(text("ALTER TABLE ticket_replies ADD COLUMN IF NOT EXISTS image TEXT"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_ensure_table()


def _clean_crit(c):
    c = (c or "medium").lower()
    return c if c in VALID_CRIT else "medium"


def _clean_route(r):
    r = (r or "").lower()
    return r if r in ("review", "fix") else None


def _replies(db, tid):
    rows = db.execute(text("""
        SELECT author_type, author_name, body, created_at, image
        FROM ticket_replies WHERE ticket_id=:t ORDER BY id ASC
    """), {"t": tid}).fetchall()
    return [{"author_type": r[0], "author": r[1] or "", "body": r[2] or "",
             "at": str(r[3])[:16] if r[3] else None, "image": r[4]} for r in rows]


def _add_reply(db, tid, author_type, author_name, body, image=None):
    db.execute(text("""
        INSERT INTO ticket_replies (ticket_id, author_type, author_name, body, image)
        VALUES (:t,:at,:an,:b,:img)
    """), {"t": tid, "at": author_type, "an": author_name, "b": body, "img": image})
    # a reply from the maker (client) or from the AI/dev raises the red dot for the admin
    if author_type in ("client", "ai"):
        db.execute(text("UPDATE tickets SET admin_unread=TRUE WHERE id=:t"), {"t": tid})


def _insert(db, **kw):
    kw.setdefault("route", None)
    rid = db.execute(text("""
        INSERT INTO tickets (source, creator_type, creator_id, creator_name, section, note,
                             critical, route, screenshot, page_url, for_ai)
        VALUES (:source,:ctype,:cid,:cname,:section,:note,:crit,:route,:shot,:url,:ai)
        RETURNING id
    """), kw).scalar()
    db.commit()
    return rid


# ═════════════════════════ STAFF (CRM) ═════════════════════════
tickets_admin = APIRouter(prefix="/tickets", tags=["tickets"])


@tickets_admin.get("/can-create")
def can_create(user=Depends(get_current_user)):
    """Lets the UI show/hide the 'New ticket' control without hardcoding the allowlist."""
    return {"can_create": can_create_ticket(user)}


@tickets_admin.post("")
@tickets_admin.post("/")
def create_ticket(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # MANUAL ticket creation is DISABLED (desk decision, Jun 2026) — tickets are opened through the
    # assistant chat / WhatsApp by starting a message with '#'. EXCEPTION: allowlisted staff
    # (TICKET_CREATE_ALLOW) may still create tickets directly. The existing-ticket workflow
    # (reply / approve / close) is unaffected.
    if not can_create_ticket(user):
        raise HTTPException(status_code=403,
            detail="Manual ticket creation is disabled. To open a ticket, message the assistant (chat or WhatsApp) starting with '#'.")
    note = (payload.get("note") or payload.get("text") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Ticket note cannot be empty.")
    rid = _insert(
        db,
        source="staff",
        ctype="staff",
        cid=user.id,
        cname=(getattr(user, "full_name", None) or getattr(user, "email", "") or "Staff"),
        section=payload.get("section") or None,
        note=note,
        crit=_clean_crit(payload.get("critical")),
        route=_clean_route(payload.get("route")),
        shot=payload.get("screenshot") or None,
        url=payload.get("page_url") or None,
        ai=bool(payload.get("for_ai", False)),
    )
    return {"ok": True, "id": rid}


@tickets_admin.get("")
@tickets_admin.get("/")
def list_tickets(status: str = None, critical: str = None, section: str = None,
                 source: str = None, mine: str = None, limit: int = 300,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    is_admin = _is_admin(user)
    where, params = [], {"lim": min(limit, 1000), "uid": user.id}
    if status in VALID_STATUS: where.append("status=:s"); params["s"] = status
    if critical in VALID_CRIT: where.append("critical=:c"); params["c"] = critical
    if section: where.append("section=:sec"); params["sec"] = section
    if source: where.append("source=:src"); params["src"] = source
    # "My Tickets" tab: a user's own tickets + tickets transferred TO them; an ADMIN also sees
    # tickets needing review/action.
    if mine in ("1", "true", "yes"):
        if is_admin:
            # admin "My tickets": own + transferred-to-me + needs-approval + any UNASSIGNED open
            # ticket (new incoming tickets nobody has taken yet — e.g. clients' portal notes), so
            # they're visible by default. Tickets assigned to someone else live in that person's tab.
            where.append("(creator_id=:uid OR assigned_to=:uid OR COALESCE(needs_approval,FALSE)=TRUE "
                         "OR (assigned_to IS NULL AND status <> 'done'))")
        else:
            # non-admin My-tickets: own + transferred-to-me + any client whose tickets this
            # staff member is designated to handle (e.g. Bakera handles Baker's tickets).
            handled = _handled_creator_ids(db, user)
            if handled:
                where.append("(creator_id=:uid OR assigned_to=:uid "
                             "OR (creator_type='client' AND creator_id = ANY(:handled)))")
                params["handled"] = handled
            else:
                where.append("(creator_id=:uid OR assigned_to=:uid)")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(text(f"""
        SELECT id, source, creator_type, creator_name, section, note, critical,
               (screenshot IS NOT NULL) AS has_shot, page_url, for_ai, status, created_at, updated_at, route,
               COALESCE(admin_unread, FALSE) AS unread,
               (SELECT COUNT(*) FROM ticket_replies r WHERE r.ticket_id=t.id) AS n_replies,
               COALESCE(needs_approval, FALSE), COALESCE(approved, FALSE),
               (creator_id=:uid) AS is_mine, assigned_to, assigned_to_name, (assigned_to=:uid) AS assigned_me
        FROM tickets t {w}
        ORDER BY COALESCE(needs_approval,FALSE) DESC, COALESCE(admin_unread,FALSE) DESC, (status='done') ASC,
                 CASE critical WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                 id DESC
        LIMIT :lim
    """), params).fetchall()
    return {"tickets": [{
        "id": r[0], "source": r[1], "creator_type": r[2], "creator": r[3] or "", "section": r[4] or "",
        "note": r[5] or "", "critical": r[6], "has_screenshot": bool(r[7]), "page_url": r[8] or "",
        "for_ai": bool(r[9]), "status": r[10], "created_at": str(r[11])[:16] if r[11] else None,
        "updated_at": str(r[12])[:16] if r[12] else None, "route": r[13],
        "unread": bool(r[14]), "replies": int(r[15] or 0),
        "needs_approval": bool(r[16]), "approved": bool(r[17]), "is_mine": bool(r[18]),
        "assigned_to": r[19], "assigned_to_name": r[20] or "", "assigned_to_me": bool(r[21]),
    } for r in rows], "is_admin": is_admin}


@tickets_admin.get("/stats")
def ticket_stats(db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE status='under_review'),
               COUNT(*) FILTER (WHERE status='proceed'),
               COUNT(*) FILTER (WHERE status='done'),
               COUNT(*) FILTER (WHERE critical IN ('high','critical') AND status<>'done')
        FROM tickets
    """)).fetchone()
    return {"under_review": r[0], "proceed": r[1], "done": r[2], "urgent_open": r[3]}


@tickets_admin.get("/members")
def list_members(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Staff members a ticket can be transferred to (for the transfer picker).
    Defined BEFORE /{tid} so 'members' isn't parsed as a ticket id."""
    rows = db.execute(text("""
        SELECT id, COALESCE(full_name, email) AS name, role FROM users
        WHERE is_active IS NOT FALSE ORDER BY full_name NULLS LAST, email
    """)).fetchall()
    return {"members": [{"id": r[0], "name": r[1] or "", "role": r[2] or ""} for r in rows]}


@tickets_admin.get("/{tid}")
def ticket_detail(tid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.execute(text("""
        SELECT id, source, creator_type, creator_name, section, note, critical, screenshot,
               page_url, for_ai, status, created_at, updated_at, route,
               COALESCE(needs_approval,FALSE), COALESCE(approved,FALSE), creator_id,
               assigned_to, assigned_to_name
        FROM tickets WHERE id=:i
    """), {"i": tid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Ticket not found")
    replies = _replies(db, tid)
    # admin opened it -> clear the red dot
    db.execute(text("UPDATE tickets SET admin_unread=FALSE WHERE id=:i"), {"i": tid})
    db.commit()
    return {"id": r[0], "source": r[1], "creator_type": r[2], "creator": r[3] or "",
            "section": r[4] or "", "note": r[5] or "", "critical": r[6], "screenshot": r[7],
            "page_url": r[8] or "", "for_ai": bool(r[9]), "status": r[10],
            "created_at": str(r[11])[:16] if r[11] else None,
            "updated_at": str(r[12])[:16] if r[12] else None, "route": r[13],
            "needs_approval": bool(r[14]), "approved": bool(r[15]), "replies": replies,
            "is_admin": _is_admin(user), "is_mine": (r[16] == user.id),
            # a designated care handler (e.g. bakera on baker's tickets) gets admin-like
            # approve/reject/send-back/close rights on this specific ticket.
            "can_handle": _is_admin(user) or _handles_ticket(db, user, tid),
            "assigned_to": r[17], "assigned_to_name": r[18] or "", "assigned_to_me": (r[17] == user.id)}


@tickets_admin.post("/{tid}/approve")
def approve_ticket(tid: int, payload: dict = None, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    """Super-admin approves a risky action the auto-worker flagged. Only role='super_admin'
    OR a designated care handler for this ticket's client (e.g. bakera for baker)."""
    if getattr(user, "role", "") != "super_admin" and not _handles_ticket(db, user, tid):
        raise HTTPException(status_code=403, detail="Only a Super Admin or the designated handler can approve this risky action.")
    row = db.execute(text("SELECT needs_approval FROM tickets WHERE id=:i"), {"i": tid}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _add_reply(db, tid, "staff", getattr(user, "full_name", "Super Admin"),
               "✅ APPROVED by Super Admin — the auto-worker may now perform the risky action.")
    db.execute(text("""
        UPDATE tickets SET approved=TRUE, needs_approval=FALSE, admin_unread=TRUE, updated_at=NOW()
        WHERE id=:i
    """), {"i": tid})
    db.commit()
    return {"ok": True}


@tickets_admin.post("/{tid}/reply")
def staff_reply(tid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Staff/AI replies to a ticket. Default status -> 'answered' (awaiting the maker).
    Staff do NOT close tickets — only the ticket maker closes (done)."""
    body = (payload.get("body") or "").strip()
    image = payload.get("image") or None   # optional downscaled data URL (staff photo reply)
    if not body and not image:
        raise HTTPException(status_code=400, detail="Reply cannot be empty")
    _add_reply(db, tid, "staff", getattr(user, "full_name", None) or getattr(user, "email", "Staff"), body, image)
    st = (payload.get("status") or "answered").lower()
    if st not in VALID_STATUS or st == "done":   # staff can't close; maker does
        st = "answered"
    db.execute(text("UPDATE tickets SET status=:s, updated_at=NOW() WHERE id=:i"), {"s": st, "i": tid})
    db.commit()
    return {"ok": True}


@tickets_admin.post("/{tid}/escalate")
def escalate_ticket(tid: int, payload: dict = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Send the ticket to Admin for review: status -> under_review, route -> review, flag admin.
    Includes the staff member's typed note (if any) as a reply first."""
    row = db.execute(text("SELECT id FROM tickets WHERE id=:i"), {"i": tid}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    name = getattr(user, "full_name", None) or getattr(user, "email", "Staff")
    body = ((payload or {}).get("body") or "").strip()
    if body:
        _add_reply(db, tid, "staff", name, body)
    _add_reply(db, tid, "staff", name, "📤 Sent to Admin for review.")
    db.execute(text("""
        UPDATE tickets SET status='under_review', route='review', needs_approval=TRUE,
                           approved=FALSE, admin_unread=TRUE, updated_at=NOW()
        WHERE id=:i
    """), {"i": tid})
    db.commit()
    return {"ok": True}


@tickets_admin.post("/{tid}/decision")
def admin_decision(tid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Admin decision on a ticket sent for review. action: approve | reject | send_back.
    send_back returns it to the creator with the admin's comments to edit/clarify."""
    if not _is_admin(user) and not _handles_ticket(db, user, tid):
        raise HTTPException(status_code=403, detail="Only an Admin or the designated handler can approve / reject / send back a ticket.")
    row = db.execute(text("SELECT id FROM tickets WHERE id=:i"), {"i": tid}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    action = (payload.get("action") or "").lower()
    comment = (payload.get("comment") or "").strip()
    name = getattr(user, "full_name", None) or getattr(user, "email", "Admin")
    if action == "approve":
        _add_reply(db, tid, "staff", name, "✅ APPROVED by " + name + (" — " + comment if comment else "") + ". Proceeding.")
        db.execute(text("""UPDATE tickets SET approved=TRUE, needs_approval=FALSE, status='proceed',
                           admin_unread=TRUE, updated_at=NOW() WHERE id=:i"""), {"i": tid})
    elif action == "reject":
        if not comment:
            comment = "no reason given"
        _add_reply(db, tid, "staff", name, "❌ REJECTED by " + name + " — " + comment)
        db.execute(text("""UPDATE tickets SET approved=FALSE, needs_approval=FALSE, status='rejected',
                           admin_unread=TRUE, updated_at=NOW() WHERE id=:i"""), {"i": tid})
    elif action == "send_back":
        if not comment:
            raise HTTPException(status_code=400, detail="Please add a comment telling the creator what to change.")
        _add_reply(db, tid, "staff", name, "↩️ SENT BACK by " + name + " — please edit your request: " + comment)
        db.execute(text("""UPDATE tickets SET needs_approval=FALSE, status='under_review',
                           admin_unread=TRUE, updated_at=NOW() WHERE id=:i"""), {"i": tid})
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    db.commit()
    return {"ok": True}


@tickets_admin.post("/{tid}/transfer")
def transfer_ticket(tid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Transfer/assign a ticket to another staff member — it shows in THEIR My-tickets with a
    'Transferred to you' tag. Any staff can transfer; the assignee gets the red-dot notification."""
    to_id = payload.get("to_user_id")
    if not to_id:
        raise HTTPException(status_code=400, detail="Pick a member to transfer to.")
    m = db.execute(text("SELECT COALESCE(full_name, email) FROM users WHERE id=:i"), {"i": to_id}).fetchone()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    if not db.execute(text("SELECT id FROM tickets WHERE id=:i"), {"i": tid}).fetchone():
        raise HTTPException(status_code=404, detail="Ticket not found")
    to_name = m[0] or "member"
    by = getattr(user, "full_name", None) or getattr(user, "email", "Staff")
    comment = (payload.get("comment") or "").strip()
    db.execute(text("UPDATE tickets SET assigned_to=:a, assigned_to_name=:an, admin_unread=TRUE, updated_at=NOW() WHERE id=:i"),
               {"a": to_id, "an": to_name, "i": tid})
    _add_reply(db, tid, "staff", by, f"🔀 Transferred to {to_name} by {by}." + (f" Note: {comment}" if comment else ""))
    db.commit()
    return {"ok": True, "assigned_to": to_id, "assigned_to_name": to_name}


@tickets_admin.patch("/{tid}")
def edit_ticket(tid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Amend the request itself. Allowed for: an Admin, the ticket's CREATOR, or the staff member
    the ticket is ASSIGNED/transferred to (so e.g. Bakera can amend Baker's tickets assigned to her)."""
    row = db.execute(text("SELECT id, creator_id, assigned_to FROM tickets WHERE id=:i"), {"i": tid}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not (_is_admin(user) or row[1] == user.id or row[2] == user.id):
        raise HTTPException(status_code=403, detail="Only an Admin, the ticket's creator, or its assignee can amend it.")
    sets, params = [], {"i": tid}
    if "note" in payload and (payload.get("note") or "").strip():
        sets.append("note=:note"); params["note"] = payload["note"].strip()
    if "section" in payload and (payload.get("section") or "").strip():
        sets.append("section=:sec"); params["sec"] = payload["section"].strip()
    if "critical" in payload:
        sets.append("critical=:cr"); params["cr"] = _clean_crit(payload.get("critical"))
    if not sets:
        raise HTTPException(status_code=400, detail="Nothing to update")
    db.execute(text(f"UPDATE tickets SET {', '.join(sets)}, updated_at=NOW() WHERE id=:i"), params)
    name = getattr(user, "full_name", None) or getattr(user, "email", "Admin")
    _add_reply(db, tid, "staff", name, "✏️ The request was edited by " + name + " (Admin).")
    db.commit()
    return {"ok": True}


@tickets_admin.get("/{tid}/image")
def ticket_image(tid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from fastapi.responses import Response
    import base64
    shot = db.execute(text("SELECT screenshot FROM tickets WHERE id=:i"), {"i": tid}).scalar()
    if not shot:
        raise HTTPException(status_code=404, detail="No image")
    # data URL -> bytes
    try:
        header, b64 = shot.split(",", 1)
        mime = header.split(";")[0].replace("data:", "") or "image/jpeg"
        return Response(content=base64.b64decode(b64), media_type=mime)
    except Exception:
        raise HTTPException(status_code=415, detail="Bad image data")


@tickets_admin.patch("/{tid}/status")
def set_status(tid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    st = (payload.get("status") or "").lower()
    if st not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="Invalid status")
    if st == "done":
        # admins can close ANY ticket; otherwise the ticket's own staff creator OR the staff member
        # it's been ASSIGNED/transferred to can close it (so Bakera can close Baker's assigned tickets).
        if not _is_admin(user):
            owner = db.execute(text("SELECT creator_type, creator_id, assigned_to FROM tickets WHERE id=:i"), {"i": tid}).fetchone()
            handled = _handled_creator_ids(db, user)
            can = owner and ((owner[0] == "staff" and owner[1] == user.id) or owner[2] == user.id
                             or (owner[0] == "client" and int(owner[1] or 0) in handled))
            if not can:
                raise HTTPException(status_code=403,
                    detail="Only the ticket's creator, its assignee, a designated handler, or an admin can close it.")
    db.execute(text("UPDATE tickets SET status=:s, updated_at=NOW() WHERE id=:i"), {"s": st, "i": tid})
    db.commit()
    return {"ok": True}


@tickets_admin.delete("/{tid}")
def delete_ticket(tid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    db.execute(text("DELETE FROM tickets WHERE id=:i"), {"i": tid})
    db.commit()
    return {"ok": True}


# ═════════════════════════ PORTAL (client) ═════════════════════════
tickets_portal = APIRouter(prefix="/portal/tickets", tags=["portal-tickets"])


@tickets_portal.post("")
@tickets_portal.post("/")
def portal_create(payload: dict, db: Session = Depends(get_db),
                  client_id: int = Depends(get_current_client)):
    # MANUAL ticket creation is DISABLED (desk decision, Jun 2026). Portal clients open tickets
    # ONLY through the assistant chat by starting a message with '#' (see portal /chat).
    raise HTTPException(status_code=403,
        detail="To open a ticket, message the assistant and start your message with '#'.")


@tickets_portal.get("")
@tickets_portal.get("/")
def portal_my_tickets(db: Session = Depends(get_db), client_id: int = Depends(get_current_client)):
    rows = db.execute(text("""
        SELECT id, section, note, critical, route, status, created_at, updated_at,
               (SELECT COUNT(*) FROM ticket_replies r WHERE r.ticket_id=t.id) AS n_replies
        FROM tickets t WHERE creator_type='client' AND creator_id=:c
        ORDER BY (status='done') ASC, id DESC
    """), {"c": client_id}).fetchall()
    return {"tickets": [{
        "id": r[0], "section": r[1] or "", "note": r[2] or "", "critical": r[3], "route": r[4],
        "status": r[5], "created_at": str(r[6])[:16] if r[6] else None,
        "updated_at": str(r[7])[:16] if r[7] else None, "replies": int(r[8] or 0),
    } for r in rows]}


@tickets_portal.get("/{tid}")
def portal_ticket_detail(tid: int, db: Session = Depends(get_db), client_id: int = Depends(get_current_client)):
    r = db.execute(text("""
        SELECT id, section, note, critical, route, status, for_ai, screenshot, created_at
        FROM tickets WHERE id=:i AND creator_type='client' AND creator_id=:c
    """), {"i": tid, "c": client_id}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"id": r[0], "section": r[1] or "", "note": r[2] or "", "critical": r[3], "route": r[4],
            "status": r[5], "for_ai": bool(r[6]), "screenshot": r[7],
            "created_at": str(r[8])[:16] if r[8] else None, "replies": _replies(db, tid)}


@tickets_portal.post("/{tid}/reply")
def portal_reply(tid: int, payload: dict, db: Session = Depends(get_db),
                 client_id: int = Depends(get_current_client)):
    """The ticket MAKER replies and/or closes. close=true -> done; otherwise re-opens for staff."""
    own = db.execute(text("SELECT creator_name FROM tickets WHERE id=:i AND creator_type='client' AND creator_id=:c"),
                     {"i": tid, "c": client_id}).fetchone()
    if not own:
        raise HTTPException(status_code=404, detail="Ticket not found")
    body = (payload.get("body") or "").strip()
    close = bool(payload.get("close"))
    if not body and not close:
        raise HTTPException(status_code=400, detail="Write a reply or close the ticket")
    if body:
        _add_reply(db, tid, "client", own[0] or f"Client #{client_id}", body)
    new_status = "done" if close else "under_review"   # maker's reply re-opens for staff
    db.execute(text("UPDATE tickets SET status=:s, updated_at=NOW() WHERE id=:i"), {"s": new_status, "i": tid})
    db.commit()
    return {"ok": True, "status": new_status}


# ── helper consumed by chat_router: active operator notes to steer the bot ──
def ai_operator_notes(db: Session, limit: int = 8) -> str:
    try:
        rows = db.execute(text("""
            SELECT note FROM tickets
            WHERE for_ai=TRUE AND status<>'done'
            ORDER BY id DESC LIMIT :l
        """), {"l": limit}).fetchall()
    except Exception:
        db.rollback()
        return ""
    notes = [r[0].strip() for r in rows if r[0] and r[0].strip()]
    if not notes:
        return ""
    body = "\n".join(f"- {n}" for n in notes)
    return ("\n\n=== OPERATOR INSTRUCTIONS (from TNFX staff — HOW TO ANSWER) ===\n"
            "Staff have left these notes on how you should respond. Follow them carefully, "
            "treat them as higher priority than your defaults, but never break the security/"
            "honesty rules:\n" + body)
