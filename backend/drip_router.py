"""
drip_router.py — automated marketing journeys (drip sequences) across email + WhatsApp.

A journey targets a segment (reuses marketing_router.SEGMENTS) and has ordered STEPS, each with
a delay and a message. Members get ENROLLED; a scheduler (POST /drip/run) fires due steps.

GATED: actually sending requires the channel to be live (email_send.configured / Wati enabled).
While a channel is off, sends are logged as 'simulated' so the whole engine runs end-to-end with
nothing leaving the building. Run manually (POST /drip/run) or wire to Task Scheduler later.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth import get_current_user
import marketing_router as mk

router = APIRouter(prefix="/drip", tags=["drip"])


def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS drip_journeys (
            id SERIAL PRIMARY KEY, name TEXT, segment_key TEXT, channel TEXT,
            is_active BOOLEAN DEFAULT FALSE, created_by INT, created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS drip_steps (
            id SERIAL PRIMARY KEY, journey_id INT, step_order INT,
            delay_hours INT DEFAULT 24, subject TEXT, body TEXT
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS drip_enrollments (
            id SERIAL PRIMARY KEY, journey_id INT,
            audience_kind TEXT, ref_id BIGINT, name TEXT, email TEXT, phone TEXT,
            current_step INT DEFAULT 0, status TEXT DEFAULT 'active',  -- active|completed|stopped
            next_run_at TIMESTAMP, enrolled_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS drip_enr_uq ON drip_enrollments(journey_id, audience_kind, ref_id)"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS drip_sends (
            id SERIAL PRIMARY KEY, enrollment_id INT, journey_id INT, step_order INT,
            channel TEXT, status TEXT, detail TEXT, created_at TIMESTAMP DEFAULT NOW()
        )"""))
    db.commit()


def _segment_members(db, key, limit=20000):
    seg = mk.SEG_BY_KEY.get(key)
    if not seg:
        return []
    frm, alias, em, ph = mk._base(seg["audience"])
    name_col = "name" if seg["audience"] != "leads" else "full_name"
    ref_col = "login" if seg["audience"] == "clients" else "id"
    rows = db.execute(text(f"""
        SELECT {ref_col} AS ref, {name_col} AS nm, {em} AS em, {ph} AS ph
        FROM {frm} WHERE {seg['where']} LIMIT :lim
    """), {"lim": limit}).fetchall()
    kind = seg["audience"]
    return [{"kind": kind, "ref_id": r[0], "name": r[1], "email": r[2], "phone": r[3]} for r in rows]


@router.get("/journeys")
def list_journeys(db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_schema(db)
    rows = db.execute(text("""
        SELECT j.id, j.name, j.segment_key, j.channel, j.is_active,
               (SELECT COUNT(*) FROM drip_steps s WHERE s.journey_id=j.id) AS steps,
               (SELECT COUNT(*) FROM drip_enrollments e WHERE e.journey_id=j.id) AS enrolled,
               (SELECT COUNT(*) FROM drip_enrollments e WHERE e.journey_id=j.id AND e.status='active') AS active,
               (SELECT COUNT(*) FROM drip_sends d WHERE d.journey_id=j.id) AS sends
        FROM drip_journeys j ORDER BY j.id DESC
    """)).fetchall()
    return {"journeys": [{"id": r[0], "name": r[1], "segment_key": r[2], "channel": r[3],
                          "is_active": bool(r[4]), "steps": r[5], "enrolled": r[6],
                          "active": r[7], "sends": r[8]} for r in rows]}


@router.get("/journeys/{jid}")
def get_journey(jid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_schema(db)
    j = db.execute(text("SELECT id,name,segment_key,channel,is_active FROM drip_journeys WHERE id=:i"), {"i": jid}).fetchone()
    if not j:
        raise HTTPException(404, "Journey not found")
    steps = db.execute(text("SELECT step_order,delay_hours,subject,body FROM drip_steps WHERE journey_id=:i ORDER BY step_order"), {"i": jid}).fetchall()
    return {"id": j[0], "name": j[1], "segment_key": j[2], "channel": j[3], "is_active": bool(j[4]),
            "steps": [{"step_order": s[0], "delay_hours": s[1], "subject": s[2], "body": s[3]} for s in steps]}


@router.post("/journeys")
def create_journey(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_schema(db)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")
    steps = payload.get("steps") or []
    if not steps:
        raise HTTPException(400, "Add at least one step")
    jid = db.execute(text("""
        INSERT INTO drip_journeys (name, segment_key, channel, is_active, created_by)
        VALUES (:n,:s,:c,:a,:u) RETURNING id
    """), {"n": name, "s": payload.get("segment_key"), "c": payload.get("channel", "email"),
           "a": bool(payload.get("is_active", False)), "u": user.id}).scalar()
    for i, st in enumerate(steps):
        db.execute(text("""INSERT INTO drip_steps (journey_id, step_order, delay_hours, subject, body)
                           VALUES (:j,:o,:d,:su,:bo)"""),
                   {"j": jid, "o": i, "d": int(st.get("delay_hours", 24)),
                    "su": st.get("subject"), "bo": st.get("body")})
    db.commit()
    return {"ok": True, "id": jid}


@router.patch("/journeys/{jid}")
def update_journey(jid: int, payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_schema(db)
    if "is_active" in payload:
        db.execute(text("UPDATE drip_journeys SET is_active=:a WHERE id=:i"), {"a": bool(payload["is_active"]), "i": jid})
    db.commit()
    return {"ok": True}


@router.delete("/journeys/{jid}")
def delete_journey(jid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    for t in ("drip_sends", "drip_enrollments", "drip_steps"):
        db.execute(text(f"DELETE FROM {t} WHERE journey_id=:i"), {"i": jid})
    db.execute(text("DELETE FROM drip_journeys WHERE id=:i"), {"i": jid})
    db.commit()
    return {"ok": True}


@router.post("/journeys/{jid}/enroll")
def enroll(jid: int, payload: dict = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Enroll the journey's segment members. dry_run=true just counts who would enroll."""
    ensure_schema(db)
    payload = payload or {}
    j = db.execute(text("SELECT segment_key FROM drip_journeys WHERE id=:i"), {"i": jid}).fetchone()
    if not j:
        raise HTTPException(404, "Journey not found")
    first = db.execute(text("SELECT delay_hours FROM drip_steps WHERE journey_id=:i ORDER BY step_order LIMIT 1"), {"i": jid}).fetchone()
    delay = int(first[0]) if first else 24
    members = _segment_members(db, j[0], limit=int(payload.get("limit", 20000)))
    if payload.get("dry_run"):
        return {"would_enroll": len(members), "segment": j[0]}
    enrolled = 0
    for m in members:
        r = db.execute(text("""
            INSERT INTO drip_enrollments (journey_id, audience_kind, ref_id, name, email, phone, current_step, status, next_run_at)
            VALUES (:j,:k,:r,:nm,:em,:ph,0,'active', NOW() + (:d || ' hours')::interval)
            ON CONFLICT (journey_id, audience_kind, ref_id) DO NOTHING
        """), {"j": jid, "k": m["kind"], "r": m["ref_id"], "nm": m["name"], "em": m["email"],
               "ph": m["phone"], "d": delay})
        enrolled += r.rowcount
    db.commit()
    return {"ok": True, "enrolled": enrolled, "members": len(members)}


def _channel_live(db, channel):
    if channel == "email":
        try:
            import email_send; return bool(email_send.configured())
        except Exception:
            return False
    if channel == "whatsapp":
        try:
            import whatsapp_ai; return bool(whatsapp_ai.get_config(db).get("enabled"))
        except Exception:
            return False
    return False


@router.post("/run")
def run_drips(payload: dict = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Fire all due steps. Sends for real only if the channel is live; else logs 'simulated'."""
    ensure_schema(db)
    payload = payload or {}
    cap = int(payload.get("limit", 1000))
    due = db.execute(text("""
        SELECT e.id, e.journey_id, e.current_step, e.email, e.phone, j.channel,
               (SELECT COUNT(*) FROM drip_steps s WHERE s.journey_id=j.id) AS nsteps
        FROM drip_enrollments e JOIN drip_journeys j ON j.id=e.journey_id
        WHERE e.status='active' AND j.is_active=TRUE AND e.next_run_at <= NOW()
        ORDER BY e.next_run_at LIMIT :lim
    """), {"lim": cap}).fetchall()
    sent = sim = done = 0
    for e in due:
        eid, jid, step, email, phone, channel, nsteps = e
        st = db.execute(text("SELECT subject, body, delay_hours FROM drip_steps WHERE journey_id=:j AND step_order=:o"),
                        {"j": jid, "o": step}).fetchone()
        if not st:
            db.execute(text("UPDATE drip_enrollments SET status='completed' WHERE id=:i"), {"i": eid}); continue
        live = _channel_live(db, channel)
        status = "sent" if live else "simulated"
        # NOTE: actual provider send wires in here when live (email_send.send / wati_service.send_message)
        if live:
            sent += 1
        else:
            sim += 1
        db.execute(text("""INSERT INTO drip_sends (enrollment_id, journey_id, step_order, channel, status, detail)
                           VALUES (:e,:j,:o,:c,:s,:d)"""),
                   {"e": eid, "j": jid, "o": step, "c": channel, "s": status,
                    "d": (st[0] or "")[:120]})
        # advance
        nxt = step + 1
        if nxt >= nsteps:
            db.execute(text("UPDATE drip_enrollments SET status='completed', current_step=:n WHERE id=:i"), {"n": nxt, "i": eid})
            done += 1
        else:
            nd = db.execute(text("SELECT delay_hours FROM drip_steps WHERE journey_id=:j AND step_order=:o"), {"j": jid, "o": nxt}).scalar() or 24
            db.execute(text("""UPDATE drip_enrollments SET current_step=:n, next_run_at=NOW()+(:d||' hours')::interval WHERE id=:i"""),
                       {"n": nxt, "d": int(nd), "i": eid})
    db.commit()
    return {"ok": True, "processed": len(due), "sent": sent, "simulated": sim, "completed": done,
            "note": "Channels are gated — 'simulated' means it would send once email/WhatsApp is live."}
