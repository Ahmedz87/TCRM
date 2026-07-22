"""comment_notify.py — email the account manager when SOMEONE ELSE comments on their lead/client.

Ticket #222: if a comment/note is added by a user who is NOT the record's assigned agent, email the
assigned agent — "<commenter> from the <department> department added a comment on your <lead|client>
<name>: <note>". Best-effort and OFF the request thread; never raises into the caller.
"""
import threading
from sqlalchemy import text


def _dept_of(db, user) -> str:
    d = (getattr(user, "department", None) or "").strip()
    if d:
        return d
    role = (getattr(user, "role", "") or "").replace("_", " ").title()
    return role or "Staff"


def notify_cross_agent_comment(db, kind: str, entity_id: int, commenter, note: str):
    """kind: 'client' (entity_id = login) | 'lead' (entity_id = lead id).
    Emails the assigned agent when a DIFFERENT user comments on their record. No-op on any problem."""
    try:
        note = (note or "").strip()
        if not note or note.lower() == "called":
            return
        if kind == "client":
            row = db.execute(text("""
                SELECT c.name, c.assigned_agent_id, u.email, u.full_name
                FROM clients c LEFT JOIN users u ON u.id = c.assigned_agent_id
                WHERE c.login = :i LIMIT 1"""), {"i": entity_id}).fetchone()
            label = "client"
        else:
            row = db.execute(text("""
                SELECT l.full_name, l.assigned_agent_id, u.email, u.full_name
                FROM leads l LEFT JOIN users u ON u.id = l.assigned_agent_id
                WHERE l.id = :i LIMIT 1"""), {"i": entity_id}).fetchone()
            label = "lead"
        if not row:
            return
        ent_name, owner_id, owner_email, owner_name = row
        if not owner_id or int(owner_id) == int(getattr(commenter, "id", 0) or 0):
            return   # no owner, or the owner commented on their own record
        if not owner_email:
            return

        commenter_name = getattr(commenter, "full_name", None) or "A colleague"
        commenter_dept = _dept_of(db, commenter)
        ent = ent_name or f"#{entity_id}"
        owner_first = (owner_name or "").split(" ")[0] or "there"

        subject = f"New comment on your {label}: {ent}"
        body = (f"Dear {owner_first},\n\n"
                f"{commenter_name} from the {commenter_dept} department has added a comment on your "
                f"{label} \"{ent}\":\n\n"
                f"    “{note}”\n\n"
                f"Please review it in the CRM under your {label}s.\n\nKind regards,\nTNFX CRM")

        def _send():
            try:
                import email_send
                email_send.send(owner_email, subject, body)
            except Exception:
                pass
        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
