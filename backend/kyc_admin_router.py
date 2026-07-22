"""
kyc_admin_router.py — staff KYC review console (the verification team's "KYC" sidebar section).

Surfaces every registration that uploaded KYC documents, with the AI verdict + reason, the
document images, and one-click Approve / Reject (with a comment). Data lives in `registrations`
(verify_status / verify_reason / ocr_fields / network_json) + `reg_kyc_documents`, written by
kyc_engine. Approve/Reject mirrors the status onto clients.kyc_status + leads.kyc_status so the
client portal updates immediately (same mapping kyc_engine uses).
"""
import os
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/kyc-admin", tags=["kyc-admin"])

# raw verify_status/status -> the label the team sees
STATUS_LABEL = {
    "verified": "approved",
    "rejected": "rejected",
    "exists": "duplicate",           # the ID already has an account
    "docs_needed": "docs_needed",    # ID approved, another document still needed
    "review": "admin_review",         # AI couldn't auto-decide -> needs a human
    "pending": "pending",
    "under_review": "under_review",
    "pending_kyc": "pending",
}


def _status_of(verify_status, status):
    raw = (verify_status or status or "").lower()
    return STATUS_LABEL.get(raw, "under_review")


@router.get("/counts")
def counts(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Per-status counts for the filter chips (only registrations that uploaded documents)."""
    rows = db.execute(text("""
        SELECT COALESCE(r.verify_status, r.status) AS st, COUNT(*) AS n
        FROM registrations r
        WHERE EXISTS (SELECT 1 FROM reg_kyc_documents d WHERE d.registration_id = r.id)
        GROUP BY COALESCE(r.verify_status, r.status)
    """)).fetchall()
    out = {"all": 0, "under_review": 0, "admin_review": 0, "rejected": 0, "approved": 0, "pending": 0}
    for r in rows:
        lbl = _status_of(r.st, None)
        out[lbl] = out.get(lbl, 0) + int(r.n)
        out["all"] += int(r.n)
    return out


@router.get("/list")
def kyc_list(status: str = "", search: str = "",
             current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """KYC submissions for the review queue. status filter: ''/all | under_review | admin_review |
    rejected | approved | pending."""
    rows = db.execute(text("""
        SELECT r.id, r.first_name, r.last_name, r.email, r.phone, r.country, r.state, r.city,
               COALESCE(r.verify_status, r.status) AS st, r.verify_reason, r.created_at, r.processed_at,
               r.lead_id, r.face_verdict, r.name_match, r.network_json,
               (SELECT COUNT(*) FROM reg_kyc_documents d WHERE d.registration_id = r.id) AS n_docs
        FROM registrations r
        WHERE EXISTS (SELECT 1 FROM reg_kyc_documents d WHERE d.registration_id = r.id)
          AND (:s = '' OR LOWER(r.first_name||' '||r.last_name) LIKE :slike
               OR LOWER(COALESCE(r.email,'')) LIKE :slike OR COALESCE(r.phone,'') LIKE :slike)
        ORDER BY r.processed_at DESC NULLS FIRST, r.id DESC
        LIMIT 500
    """), {"s": (search or "").strip(), "slike": f"%{(search or '').strip().lower()}%"}).fetchall()
    items = []
    want = (status or "all").lower()
    for r in rows:
        lbl = _status_of(r.st, None)
        if want not in ("", "all") and lbl != want:
            continue
        nj = r.network_json if isinstance(r.network_json, dict) else {}
        poa = nj.get("poa") or {}
        poa_review = bool(poa.get("manual_review")) or (poa.get("verdict") == "need_family_id")
        items.append({
            "registration_id": r.id,
            "name": ((r.first_name or "") + " " + (r.last_name or "")).strip() or "—",
            "email": r.email, "phone": r.phone,
            "country": r.country, "state": r.state, "city": r.city,
            "status": lbl, "reason": r.verify_reason,
            "n_docs": int(r.n_docs or 0),
            "created_at": str(r.created_at) if r.created_at else None,
            "processed_at": str(r.processed_at) if r.processed_at else None,
            "lead_id": r.lead_id,
            "poa_review": poa_review,
            "poa_holder": poa.get("holder_name") if poa_review else None,
        })
    return {"items": items, "count": len(items)}


@router.get("/{registration_id}")
def detail(registration_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.execute(text("""
        SELECT id, first_name, last_name, email, phone, country, state, city, address, nationality,
               date_of_birth, COALESCE(verify_status, status) AS st, verify_reason, ocr_fields,
               network_json, face_verdict, face_score, name_match, doc_expired, id_number,
               created_at, processed_at
        FROM registrations WHERE id=:r
    """), {"r": registration_id}).fetchone()
    if not r:
        return {"error": "not found"}
    docs = db.execute(text("""
        SELECT id, doc_type, side, status FROM reg_kyc_documents WHERE registration_id=:r ORDER BY id
    """), {"r": registration_id}).fetchall()
    m = r._mapping
    return {
        "registration_id": r.id,
        "name": ((m["first_name"] or "") + " " + (m["last_name"] or "")).strip(),
        "email": m["email"], "phone": m["phone"], "country": m["country"], "state": m["state"],
        "city": m["city"], "address": m["address"], "nationality": m["nationality"],
        "date_of_birth": m["date_of_birth"],
        "status": _status_of(m["st"], None), "reason": m["verify_reason"],
        "ocr_fields": m["ocr_fields"] if isinstance(m["ocr_fields"], dict) else {},
        "network": m["network_json"] if isinstance(m["network_json"], dict) else {},
        "poa": (m["network_json"].get("poa") if isinstance(m["network_json"], dict) else None) or {},
        "face_verdict": m["face_verdict"], "face_score": m["face_score"],
        "name_match": m["name_match"], "doc_expired": m["doc_expired"], "id_number": m["id_number"],
        "created_at": str(m["created_at"]) if m["created_at"] else None,
        "processed_at": str(m["processed_at"]) if m["processed_at"] else None,
        "documents": [{"id": d.id, "doc_type": d.doc_type, "side": d.side, "status": d.status} for d in docs],
    }


@router.get("/{registration_id}/doc/{doc_id}")
def doc_image(registration_id: int, doc_id: int,
              current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT file_path FROM reg_kyc_documents WHERE id=:d AND registration_id=:r
    """), {"d": doc_id, "r": registration_id}).fetchone()
    if not row or not row[0] or not os.path.exists(row[0]):
        return {"error": "file not found"}
    return FileResponse(row[0])


@router.post("/{registration_id}/decision")
def decision(registration_id: int, payload: dict,
             current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Approve or reject a KYC submission. payload: {decision:'approve'|'reject', comment?}."""
    dec = (payload.get("decision") or "").lower()
    comment = (payload.get("comment") or "").strip()
    if dec not in ("approve", "reject"):
        return {"ok": False, "error": "decision must be approve or reject"}
    reg = db.execute(text("SELECT lead_id, mt_login, email FROM registrations WHERE id=:r"),
                     {"r": registration_id}).fetchone()
    if not reg:
        return {"ok": False, "error": "registration not found"}
    by = getattr(current_user, "full_name", None) or getattr(current_user, "email", "staff")
    if dec == "approve":
        vstatus, client_kyc, reason = "verified", "verified", (comment or f"Approved by {by}.")
        new_status = "verified"
    else:
        vstatus, client_kyc = "rejected", "rejected"
        reason = comment or "Your documents were not approved. Please re-upload clear, valid documents."
        new_status = "rejected"
    db.execute(text("""
        UPDATE registrations SET verify_status=:vs, verify_reason=:rsn, status=:st, processed_at=NOW()
        WHERE id=:r
    """), {"vs": vstatus, "rsn": reason, "st": new_status, "r": registration_id})
    if reg[0]:
        db.execute(text("UPDATE leads SET kyc_status=:k WHERE id=:l"), {"k": vstatus, "l": reg[0]})
    if reg[1] is not None:
        db.execute(text("UPDATE clients SET kyc_status=:k WHERE login=:lg"), {"k": client_kyc, "lg": reg[1]})
    db.commit()
    # on manual APPROVE -> provision the trading account + convert lead + notify client/IB/sales
    if dec == "approve":
        try:
            import kyc_postverify
            kyc_postverify.on_verified(db, registration_id)
        except Exception as e:
            print(f"[kyc-admin] post-verify workflow failed for reg {registration_id}: {e}", flush=True)

    # email the client when the team rejects, stating the reason
    if dec == "reject" and reg.email:
        try:
            import email_send
            if email_send.configured():
                email_send.send(reg.email, "Your TNFX verification needs attention", reason,
                                body_html=email_send.notice_html(
                                    "We couldn't verify your documents", reason,
                                    "Please log in and upload clear, valid documents to try again, or contact support."))
        except Exception as e:
            print(f"[kyc-admin] reject email failed for reg {registration_id}: {e}", flush=True)
    return {"ok": True, "status": _status_of(vstatus, None), "reason": reason}


@router.post("/{registration_id}/doc/{doc_id}/decision")
def doc_decision(registration_id: int, doc_id: int, payload: dict,
                 current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Approve or reject ONE document, then recompute the overall verdict. Lets the team approve
    the ID while asking for a new proof of address (status 'docs_needed')."""
    dec = (payload.get("decision") or "").lower()
    comment = (payload.get("comment") or "").strip()
    if dec not in ("approve", "reject"):
        return {"ok": False, "error": "decision must be approve or reject"}
    db.execute(text("UPDATE reg_kyc_documents SET status=:s WHERE id=:d AND registration_id=:r"),
               {"s": "approved" if dec == "approve" else "rejected", "d": doc_id, "r": registration_id})
    db.commit()

    docs = db.execute(text("SELECT side, status FROM reg_kyc_documents WHERE registration_id=:r"),
                      {"r": registration_id}).fetchall()
    st = {d.side: (d.status or "") for d in docs}
    id_rejected = any(st.get(s) == "rejected" for s in ("front", "main", "back"))
    id_approved = st.get("front") == "approved" or st.get("main") == "approved"
    poa_approved = st.get("proof_of_address") == "approved"
    poa_present = "proof_of_address" in st
    if id_rejected:
        overall = "rejected"
        reason = comment or "A required ID document was rejected. Please re-upload a clear, valid document."
    elif id_approved and poa_approved:
        overall, reason = "verified", "Your identity has been verified."
    elif id_approved and (not poa_present or st.get("proof_of_address") == "rejected"):
        overall = "docs_needed"
        reason = comment or "Your ID has been approved. Please upload a valid proof of address to finish verifying your account."
    else:
        overall, reason = "review", "Your documents are being reviewed by our team."

    reg = db.execute(text("SELECT lead_id, mt_login, email FROM registrations WHERE id=:r"),
                     {"r": registration_id}).fetchone()
    client_kyc = {"verified": "verified", "rejected": "rejected", "docs_needed": "docs_needed"}.get(overall, "pending_review")
    db.execute(text("UPDATE registrations SET verify_status=:v, verify_reason=:rsn, status=:stt, processed_at=NOW() WHERE id=:r"),
               {"v": overall, "rsn": reason, "stt": ("verified" if overall == "verified" else overall), "r": registration_id})
    if reg and reg[0]:
        db.execute(text("UPDATE leads SET kyc_status=:k WHERE id=:l"), {"k": overall, "l": reg[0]})
    if reg and reg[1] is not None:
        db.execute(text("UPDATE clients SET kyc_status=:k WHERE login=:lg"), {"k": client_kyc, "lg": reg[1]})
    db.commit()

    if overall == "verified":
        try:
            import kyc_postverify
            kyc_postverify.on_verified(db, registration_id)
        except Exception as e:
            print(f"[kyc-admin] post-verify failed: {e}", flush=True)
    elif overall in ("rejected", "docs_needed") and reg and reg[2]:
        try:
            import email_send
            if email_send.configured():
                subj = "Your TNFX verification — action needed" if overall == "docs_needed" else "Your TNFX verification needs attention"
                head = "One more document needed" if overall == "docs_needed" else "We couldn't verify your documents"
                email_send.send(reg[2], subj, reason,
                                body_html=email_send.notice_html(head, reason, "Log in at https://my1.tnfx.co to upload."))
        except Exception as e:
            print(f"[kyc-admin] doc-decision email failed: {e}", flush=True)
    return {"ok": True, "overall": _status_of(overall, None), "reason": reason}


def _reg_contact(db, registration_id):
    """(name, email) for a registration, or (None, None)."""
    reg = db.execute(text("SELECT first_name, last_name, email FROM registrations WHERE id=:r"),
                     {"r": registration_id}).fetchone()
    if not reg:
        return None, None
    name = ((reg[0] or "") + " " + (reg[1] or "")).strip() or None
    return name, reg[2]


@router.post("/{registration_id}/send-doc-reminder")
def send_doc_reminder(registration_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """KYC team action (ticket 186) — email the client a TNFX-branded reminder to upload their
    outstanding verification documents, spelling out exactly what is still needed."""
    name, email = _reg_contact(db, registration_id)
    if not email:
        return {"ok": False, "error": "No email on file for this registration."}
    docs = db.execute(text("SELECT side, status FROM reg_kyc_documents WHERE registration_id=:r"),
                      {"r": registration_id}).fetchall()
    st = {d.side: (d.status or "") for d in docs}
    missing = []
    if not (st.get("front") == "approved" or st.get("main") == "approved"):
        missing.append("Proof of identity (passport or national ID)")
    if st.get("proof_of_address") != "approved":
        missing.append("Proof of address (utility bill or bank statement, less than 3 months old)")
    import email_send
    if not email_send.configured():
        return {"ok": False, "error": "Email is not configured on the server yet."}
    ok = email_send.send(
        email, "Complete your TNFX verification — documents needed",
        "Please upload your outstanding verification documents at https://my1.tnfx.co",
        body_html=email_send.doc_reminder_html(name, missing or None))
    return {"ok": bool(ok), "sent_to": email, "missing": missing}


@router.post("/{registration_id}/send-verification-email")
def send_verification_email(registration_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """KYC team action (ticket 186) — email the client a TNFX-branded request to confirm their
    email address (they confirm by logging into the portal)."""
    name, email = _reg_contact(db, registration_id)
    if not email:
        return {"ok": False, "error": "No email on file for this registration."}
    import email_send
    if not email_send.configured():
        return {"ok": False, "error": "Email is not configured on the server yet."}
    ok = email_send.send(
        email, "Confirm your TNFX email address",
        "Please confirm your email address by logging in at https://my1.tnfx.co",
        body_html=email_send.verify_email_html(name, verify_url="https://my1.tnfx.co/portal/"))
    return {"ok": bool(ok), "sent_to": email}
