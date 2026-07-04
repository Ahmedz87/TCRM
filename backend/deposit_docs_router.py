"""
deposit_docs_router.py — surface the imported TradeSoft deposit receipts + KYC docs in the CRM.
Read-only. Receipts stream from the DB box (where the 100k+ images live) over key SSH.
Endpoints (prefix /deposit-docs):
  GET /client/{login}          -> all deposit receipts for a client login (+ method, amount, status, fraud verdict)
  GET /{doc_id}/image          -> stream one receipt image
  GET /methods/{method}        -> paginated per-method rows (qi_card|zaincash|sham_cash) with OCR + fraud
  GET /fraud/summary           -> suspect counts per method
  GET /kyc/client/{login}      -> KYC docs (typed) for a client login
"""
import io, threading
import paramiko
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/deposit-docs", tags=["deposit-docs"])

DBBOX = "199.247.6.189"; KEY = r"C:\Users\Administrator\.ssh\id_ed25519"
BASE = "/var/lib/broker_docs/deposits"
_lock = threading.Lock(); _sftp = {"c": None, "s": None}

def _get_sftp():
    with _lock:
        if _sftp["s"] is not None:
            try:
                _sftp["s"].stat("/var/lib/broker_docs"); return _sftp["s"]
            except Exception:
                _sftp["s"] = None
        c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(DBBOX, username="root", key_filename=KEY, timeout=20)
        _sftp["c"] = c; _sftp["s"] = c.open_sftp()
        return _sftp["s"]

def _read_receipt(filename, folder=None):
    s = _get_sftp()
    folders = [folder] if folder else []
    folders += [f for f in ("f1", "f2") if f != folder]
    for fo in folders:
        try:
            buf = io.BytesIO(); s.getfo(f"{BASE}/{fo}/{filename}", buf); return buf.getvalue()
        except Exception:
            continue
    return None

MTABLE = {"qi_card": "pay_qi_card", "zaincash": "pay_zaincash", "sham_cash": "pay_sham_cash"}

@router.get("/client/{login}")
def client_receipts(login: int, db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT id, ts_txn_id, payment_method, amount, currency, status, tx_date,
               receipt_filename, folder, ocr_status
        FROM deposit_documents WHERE client_login=:l ORDER BY tx_date DESC NULLS LAST"""),
        {"l": login}).mappings().all()
    return {"login": login, "count": len(rows), "receipts": [dict(r) for r in rows]}

@router.get("/{doc_id}/image")
def receipt_image(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    r = db.execute(text("SELECT receipt_filename, folder FROM deposit_documents WHERE id=:i"),
                   {"i": doc_id}).mappings().first()
    if not r:
        raise HTTPException(404, "not found")
    b = _read_receipt(r["receipt_filename"], r["folder"])
    if not b:
        raise HTTPException(404, "image not downloaded yet")
    ct = "image/png" if r["receipt_filename"].lower().endswith(".png") else "image/jpeg"
    return StreamingResponse(io.BytesIO(b), media_type=ct)

@router.get("/methods/{method}")
def method_rows(method: str, limit: int = Query(100, le=500), offset: int = 0,
                fraud: str = Query(None), db=Depends(get_db), user=Depends(get_current_user)):
    t = MTABLE.get(method)
    if not t:
        raise HTTPException(404, "unknown method")
    where = "WHERE 1=1" + (" AND fraud_verdict=:f" if fraud else "")
    rows = db.execute(text(f"""
        SELECT id, client_login, person_name, sys_amount, status, tx_date, receipt_filename,
               ocr_txid, ocr_sender_acct, ocr_receiver_acct, ocr_amount, ocr_datetime,
               amount_match, ocr_status, fraud_verdict, fraud_reasons
        FROM {t} {where} ORDER BY tx_date DESC NULLS LAST LIMIT :lim OFFSET :off"""),
        {"f": fraud, "lim": limit, "off": offset}).mappings().all()
    return {"method": method, "rows": [dict(r) for r in rows]}

@router.get("/fraud/summary")
def fraud_summary(db=Depends(get_db), user=Depends(get_current_user)):
    out = {}
    for m, t in MTABLE.items():
        r = db.execute(text(f"""SELECT count(*) total,
              count(*) FILTER (WHERE ocr_status='done') ocrd,
              count(*) FILTER (WHERE fraud_verdict='suspect') suspects,
              count(*) FILTER (WHERE fraud_verdict='clean') clean
              FROM {t}""")).mappings().first()
        out[m] = dict(r)
    return out

@router.get("/kyc/client/{login}")
def kyc_docs(login: int, db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT id, doc_type, filename, ocr_status,
               ocr_json->>'full_name_latin' AS name, ocr_json->>'id_number' AS id_number,
               ocr_json->>'date_of_birth' AS dob, ocr_json->>'mother_name' AS mother,
               ocr_json->>'expiry_date' AS expiry
        FROM ts_kyc_documents WHERE client_login=:l ORDER BY doc_type"""),
        {"l": login}).mappings().all()
    return {"login": login, "docs": [dict(r) for r in rows]}
