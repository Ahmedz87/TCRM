"""
payment_cards_router.py — company manual-payment cards (Qi card / Zain Cash / Fastpay / Sham Cash)
distributed to back-office members with ACTIVE HOURS, + the client manual-deposit flow with AI
screenshot OCR + fraud checks (deposit_fraud.py).

  admin  (prefix /payments,  staff auth):  cards CRUD, txid-series training, manual-deposit review
  portal (prefix /portal,    client auth): get an available card NOW, submit a manual deposit + proof
"""
import os, base64, json
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import deposit_fraud as DF

try:
    from portal_router import get_current_client
except Exception:
    def get_current_client():  # fallback if import order differs
        raise RuntimeError("client auth unavailable")

admin = APIRouter(prefix="/payments", tags=["Payment cards"])
portal = APIRouter(prefix="/portal", tags=["Portal deposit"])

# Only the back-office team (they physically hold the Q/ZC/Fastpay/ShamCash cards) + admins may
# view/change payment cards & gateway settings and review manual deposits.
BACKOFFICE_EMAILS = {"jwanf@tnfx.co", "matt@tnfx.co", "jenina@tnfx.co", "mustafam@tnfx.co",
                     "mustafaf@tnfx.co", "ibrahimm@tnfx.co", "ihsana@tnfx.co", "ahmedas@tnfx.co",
                     "mohammedm@tnfx.co", "hussain@tnfx.co"}
_ADMIN_ROLES = {"admin", "super_admin", "director"}


def require_backoffice(current_user=Depends(get_current_user)):
    role = (getattr(current_user, "role", "") or "").lower()
    email = (getattr(current_user, "email", "") or "").lower()
    if role in _ADMIN_ROLES or role == "backoffice" or email in BACKOFFICE_EMAILS:
        return current_user
    raise HTTPException(status_code=403, detail="Payment settings are restricted to the back-office team.")

PROOF_DIR = r"C:\Broker-crm\backend\deposit_proofs"
# portal method label -> card_type
METHOD_TYPE = {"qi card": "qcard", "q card": "qcard", "qcard": "qcard", "qi_card": "qcard", "qicard": "qcard",
               "zain cash": "zaincash", "zaincash": "zaincash", "zc": "zaincash", "zain_cash": "zaincash",
               "fastpay": "fastpay", "fast pay": "fastpay", "fast_pay": "fastpay",
               "sham cash": "shamcash", "shamcash": "shamcash", "sham_cash": "shamcash"}


def _ensure(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS payment_cards (
        id SERIAL PRIMARY KEY, card_type VARCHAR(20), number VARCHAR(60), label VARCHAR(80),
        holder_user_id INT, holder_name VARCHAR(80), active_from INT DEFAULT 0, active_to INT DEFAULT 24,
        is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW())"""))
    # extra per-card controls (account number + transaction/monthly limits + round-robin cursor)
    for col, ddl in [
        ("account_number",      "VARCHAR(60)"),
        ("wallet_limit",        "NUMERIC DEFAULT 0"),
        ("max_per_transaction", "NUMERIC DEFAULT 0"),   # 0 = no limit
        ("monthly_limit",       "NUMERIC DEFAULT 0"),   # 0 = no limit
        ("month_deposited",     "NUMERIC DEFAULT 0"),   # running total this month_anchor
        ("month_anchor",        "DATE"),
        ("last_shown_at",       "TIMESTAMPTZ"),         # round-robin cursor
        ("times_shown",         "INT DEFAULT 0"),
        ("card_name",           "VARCHAR(80)"),         # the NAME PRINTED ON THE CARD (from the pic)
        ("daily_limit",         "NUMERIC DEFAULT 0"),   # 0 = no limit
        ("day_deposited",       "NUMERIC DEFAULT 0"),   # running total for day_anchor
        ("day_anchor",          "DATE"),
    ]:
        db.execute(text(f"ALTER TABLE payment_cards ADD COLUMN IF NOT EXISTS {col} {ddl}"))
    db.execute(text("CREATE TABLE IF NOT EXISTS payment_cards_meta (k TEXT PRIMARY KEY, v TEXT)"))
    # v2: (1) the old `holder_name` actually held the name printed on the card -> move it to `card_name`,
    # clear holder_* for the real back-office holder; (2) convert active_from/active_to HOURS -> MINUTES.
    if not db.execute(text("SELECT 1 FROM payment_cards_meta WHERE k='migrated_v2'")).fetchone():
        db.execute(text("UPDATE payment_cards SET card_name=holder_name "
                        "WHERE COALESCE(card_name,'')='' AND COALESCE(holder_name,'')<>''"))
        db.execute(text("UPDATE payment_cards SET holder_name=NULL, holder_user_id=NULL"))
        db.execute(text("UPDATE payment_cards SET active_from=LEAST(active_from,24)*60, "
                        "active_to=LEAST(active_to,24)*60"))
        db.execute(text("INSERT INTO payment_cards_meta(k,v) VALUES('migrated_v2','1') ON CONFLICT (k) DO NOTHING"))
    # v3: the "per-transaction" limit is replaced by a DAILY limit — carry any old value over once.
    if not db.execute(text("SELECT 1 FROM payment_cards_meta WHERE k='migrated_v3'")).fetchone():
        db.execute(text("UPDATE payment_cards SET daily_limit=COALESCE(max_per_transaction,0) WHERE COALESCE(daily_limit,0)=0"))
        db.execute(text("INSERT INTO payment_cards_meta(k,v) VALUES('migrated_v3','1') ON CONFLICT (k) DO NOTHING"))
    db.commit(); DF.ensure_tables(db)


# ── FX rates (backoffice-editable) — local-currency deposits convert to USD at these ─────────
#   IQD (Qi Card / Zain Cash / Fastpay — Iraq) · SYP (Sham Cash — Syria). Default IQD 1550 = $1.
_FX = {"IQD": ("fx_rate_iqd", 1550.0), "SYP": ("fx_rate_syp", 15000.0)}


def fx_rates(db) -> dict:
    """{'IQD': 1550.0, 'SYP': 15000.0} — how many local units = $1."""
    try:
        _ensure(db)
    except Exception:
        db.rollback()
    out = {}
    for cur, (k, dflt) in _FX.items():
        v = db.execute(text("SELECT v FROM payment_cards_meta WHERE k=:k"), {"k": k}).scalar()
        try:
            out[cur] = float(v) if v not in (None, "") else dflt
        except Exception:
            out[cur] = dflt
    return out


@admin.get("/fx-rates")
def get_fx_rates(db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    return {"rates": fx_rates(db)}


@admin.post("/fx-rates")
def set_fx_rates(data: dict, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    for cur, (k, _d) in _FX.items():
        val = data.get(cur, data.get(cur.lower()))
        if val in (None, ""):
            continue
        try:
            rate = float(val)
            if rate <= 0:
                continue
            db.execute(text("INSERT INTO payment_cards_meta(k,v) VALUES(:k,:v) "
                            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v"), {"k": k, "v": str(rate)})
        except Exception:
            db.rollback()
    db.commit()
    return {"ok": True, "rates": fx_rates(db)}


def _downgrade_loyalty(db, client_id) -> bool:
    """Repeat fake-deposit penalty: reset the client's loyalty points/streak and drop the tier one step."""
    tiers = ["bronze", "silver", "gold", "platinum", "diamond"]
    try:
        row = db.execute(text("SELECT tier FROM loyalty_accounts WHERE client_id=:c"), {"c": client_id}).fetchone()
        if not row:
            return False
        cur_t = (row[0] or "bronze").lower()
        idx = tiers.index(cur_t) if cur_t in tiers else 0
        new_t = tiers[max(0, idx - 1)]
        db.execute(text("""UPDATE loyalty_accounts SET points_balance=0, current_streak=0, tier=:t, updated_at=NOW()
                           WHERE client_id=:c"""), {"t": new_t, "c": client_id})
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def _type_of(method: str) -> str:
    m = (method or "").strip().lower()
    if m in METHOD_TYPE:
        return METHOD_TYPE[m]
    mn = m.replace("_", " ").replace("-", " ")          # payment_methods codes like 'qi_card'
    if mn in METHOD_TYPE:
        return METHOD_TYPE[mn]
    mc = m.replace("_", "").replace("-", "").replace(" ", "")
    return METHOD_TYPE.get(mc, m)


# ───────────────────────── ADMIN: cards CRUD ─────────────────────────
@admin.get("/holders")
def list_holders(db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    """The back-office team members who can hold a card (role='backoffice' + admins in the list)."""
    rows = db.execute(text("""SELECT id, full_name, email FROM users
        WHERE role='backoffice' OR lower(email) = ANY(:e) ORDER BY full_name"""),
        {"e": list(BACKOFFICE_EMAILS)}).fetchall()
    return {"holders": [{"id": r[0], "name": r[1], "email": r[2]} for r in rows]}


@admin.get("/cards")
def list_cards(db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    _ensure(db)
    from datetime import datetime
    now = datetime.now()
    cur_min = now.hour * 60 + now.minute
    rows = db.execute(text("""SELECT id, card_type, number, label, holder_user_id, holder_name,
        active_from, active_to, is_active, account_number, wallet_limit, daily_limit,
        monthly_limit, month_deposited, month_anchor, times_shown, card_name, day_deposited, day_anchor
        FROM payment_cards ORDER BY card_type, card_name, id""")).fetchall()
    today = now.date()
    out = []
    for r in rows:
        af, at = int(r[6] or 0), int(r[7] or 1440)
        in_hours = (af <= at and af <= cur_min < at) or (af > at and (cur_min >= af or cur_min < at))
        month_used = float(r[13] or 0) if (r[14] and r[14].year == now.year and r[14].month == now.month) else 0.0
        day_used = float(r[17] or 0) if (r[18] and r[18] == today) else 0.0
        out.append({"id": r[0], "card_type": r[1], "number": r[2], "label": r[3] or "",
            "holder_user_id": r[4], "holder_name": r[5] or "", "card_name": r[16] or "",
            "active_from": af, "active_to": at,       # MINUTES since midnight
            "is_active": bool(r[8]), "account_number": r[9] or "", "wallet_limit": float(r[10] or 0),
            "daily_limit": float(r[11] or 0), "day_used": day_used,
            "monthly_limit": float(r[12] or 0), "month_used": month_used, "times_shown": r[15] or 0,
            "available_now": bool(r[8]) and in_hours})
    return {"cards": out, "available_now": sum(1 for c in out if c["available_now"]),
            "server_minute": cur_min}


@admin.post("/cards")
def add_card(data: dict, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    _ensure(db)
    # active_from/active_to are MINUTES-since-midnight (0..1440); default full-day.
    rid = db.execute(text("""INSERT INTO payment_cards (card_type, number, card_name, holder_user_id,
        holder_name, active_from, active_to, is_active, account_number, wallet_limit,
        daily_limit, monthly_limit)
        VALUES (:t,:n,:cn,:hu,:hn,:af,:at,:a,:acct,:wl,:dl,:ml) RETURNING id"""), {
        "t": _type_of(data.get("card_type") or data.get("method") or ""), "n": data.get("number") or "",
        "cn": data.get("card_name") or data.get("label") or "", "hu": data.get("holder_user_id") or None,
        "hn": data.get("holder_name") or "",
        "af": int(data.get("active_from") or 0), "at": int(data.get("active_to") or 1440),
        "a": bool(data.get("is_active", True)), "acct": data.get("account_number") or "",
        "wl": float(data.get("wallet_limit") or 0), "dl": float(data.get("daily_limit") or 0),
        "ml": float(data.get("monthly_limit") or 0)}).scalar()
    db.commit(); return {"ok": True, "id": rid}


@admin.put("/cards/{cid}")
def update_card(cid: int, data: dict, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    fields = {k: data[k] for k in ("number", "card_name", "holder_user_id", "holder_name", "active_from",
              "active_to", "is_active", "account_number", "wallet_limit", "daily_limit",
              "monthly_limit") if k in data}
    if fields.get("holder_user_id") in ("", 0):
        fields["holder_user_id"] = None
    if "card_type" in data: fields["card_type"] = _type_of(data["card_type"])
    if not fields: return {"ok": False}
    sets = ", ".join(f"{k}=:{k}" for k in fields); fields["id"] = cid
    db.execute(text(f"UPDATE payment_cards SET {sets} WHERE id=:id"), fields); db.commit()
    return {"ok": True}


@admin.delete("/cards/{cid}")
def delete_card(cid: int, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    db.execute(text("DELETE FROM payment_cards WHERE id=:i"), {"i": cid}); db.commit(); return {"ok": True}


@admin.post("/txid-series")
def train_series(data: dict, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    """Train the transaction-ID series for a method from the desk's sample IDs (the last 50 Q-card txids)."""
    _ensure(db)
    method = _type_of(data.get("method") or "qcard")
    samples = data.get("samples") or []
    if isinstance(samples, str):
        samples = [s for s in samples.replace(",", "\n").splitlines() if s.strip()]
    res = DF.learn_series(db, method, samples)
    return {"ok": True, "learned": res, "count": len(samples)}


REJECT_REASONS = ["Duplicate receipt / transaction ID", "Altered / edited receipt",
                  "Amount does not match", "Wrong receiver card", "Fake / unreadable receipt",
                  "Transaction not found", "Wrong sender name", "Other"]


def _deposit_dict(r):
    return {"id": r[0], "login": r[1], "method": r[2], "amount": float(r[3] or 0),
        "entered_txid": r[4], "ocr_txid": r[5], "ocr_wallet_id": r[6], "ocr_card": r[7],
        "ocr_amount": float(r[8] or 0) if r[8] is not None else None, "ocr_date": r[9],
        "verdict": r[10], "reasons": r[11], "date": str(r[12])[:16], "name": r[13] or "",
        "request_id": r[14], "entered_wallet_id": r[15], "has_image": bool(r[16]),
        "status": r[17] or "pending_admin_review",
        "phone": r[18] or "", "email": r[19] or "",
        # company card the client paid TO (the RECEIVER)
        "company_card": r[20] or "", "company_card_name": r[21] or "", "company_account": r[22] or ""}


_DEP_COLS = """p.id, p.login, p.method, p.amount, p.entered_txid, p.ocr_txid,
    p.ocr_wallet_id, p.ocr_card, p.ocr_amount, p.ocr_date, p.verdict, p.reasons, p.created_at, c.name,
    p.request_id, p.entered_wallet_id, COALESCE(p.image_path,'')<>'' AS has_img, r.status,
    c.phone, c.email, pc.number, pc.card_name, pc.account_number"""
_DEP_FROM = """FROM deposit_proofs p LEFT JOIN clients c ON c.login=p.login
    LEFT JOIN portal_money_requests r ON r.id=p.request_id
    LEFT JOIN payment_cards pc ON pc.id=p.card_id"""


@admin.get("/manual-deposits")
def manual_deposits(db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    _ensure(db)
    # Only SUBMITTED deposits (those that passed the client-side checks and created a money
    # request) are listed for review. Audit-only proofs from failed attempts (request_id NULL)
    # are never shown here.
    rows = db.execute(text(f"SELECT {_DEP_COLS} {_DEP_FROM} WHERE p.request_id IS NOT NULL ORDER BY p.id DESC LIMIT 300")).fetchall()
    return {"deposits": [_deposit_dict(r) for r in rows], "reject_reasons": REJECT_REASONS}


@admin.get("/manual-deposits/{pid}/detail")
def manual_deposit_detail(pid: int, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    """Full case-file for the review popup: payment/OCR details + client info + last 10 timeline comments."""
    _ensure(db)
    r = db.execute(text(f"SELECT {_DEP_COLS} {_DEP_FROM} WHERE p.id=:i"), {"i": pid}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    d = _deposit_dict(r)
    # last 10 comments/actions on this client's timeline
    comments = db.execute(text("""SELECT a.action, a.note, a.created_at, u.full_name
        FROM call_actions a LEFT JOIN users u ON u.id=a.agent_id
        WHERE a.login=:l ORDER BY a.created_at DESC LIMIT 10"""), {"l": d["login"]}).fetchall()
    d["comments"] = [{"action": c[0], "note": c[1] or "", "date": str(c[2])[:16], "by": c[3] or ""} for c in comments]
    return d


@admin.get("/manual-deposits/{pid}/image")
def manual_deposit_image(pid: int, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    from fastapi.responses import Response, JSONResponse
    p = db.execute(text("SELECT image_path FROM deposit_proofs WHERE id=:i"), {"i": pid}).fetchone()
    if not p or not p[0] or not os.path.exists(p[0]):
        return JSONResponse({"error": "no image"}, status_code=404)
    return Response(open(p[0], "rb").read(), media_type="image/jpeg")


@admin.post("/manual-deposits/{pid}/action")
def manual_deposit_action(pid: int, data: dict, db: Session = Depends(get_db), current_user=Depends(require_backoffice)):
    """Back-office approves (-> ledger) or rejects a manual deposit. AI only flags; a human decides here."""
    _ensure(db)
    p = db.execute(text("""SELECT p.request_id, p.login, p.amount, p.method, r.status,
        p.ocr_txid, p.entered_txid, p.ocr_wallet_id, p.entered_wallet_id, p.ocr_card, p.ocr_date, p.card_id
        FROM deposit_proofs p LEFT JOIN portal_money_requests r ON r.id=p.request_id
        WHERE p.id=:i"""), {"i": pid}).fetchone()
    if not p:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Proof not found")
    rid, login, amount, method, card_id = p[0], p[1], float(p[2] or 0), p[3], p[11]
    feed_txid = (p[5] or p[6] or "").strip()
    feed_wallet = (p[7] or p[8] or "").strip()
    feed_recv = (p[9] or "").strip()
    act = (data.get("action") or "").lower()
    reason = (data.get("reason") or "").strip()
    by = getattr(current_user, "full_name", None) or getattr(current_user, "email", "") or "back-office"
    uid = getattr(current_user, "id", None)
    if act == "reject":
        db.execute(text("UPDATE deposit_proofs SET verdict='reject', reasons=:rs WHERE id=:i"),
                   {"i": pid, "rs": (f"Rejected: {reason}" if reason else "Rejected")})
        if rid:
            db.execute(text("UPDATE portal_money_requests SET status='rejected' WHERE id=:i"), {"i": rid})
        # AUTO-COMMENT on the client's timeline: what/when/who/why
        note = f"Deposit ${amount:,.2f} via {method or 'manual'} REJECTED — {reason or 'no reason given'}"
        db.execute(text("""INSERT INTO call_actions (login, agent_id, action, note, created_at)
            VALUES (:l,:a,'deposit_rejected',:n,NOW())"""), {"l": login, "a": uid, "n": note})
        db.commit()
        DF.record_sample(db, method=_type_of(method), txid=feed_txid, sender_acct=feed_wallet,
                         receiver_acct=feed_recv, amount=amount, source="rejected")
        return {"ok": True, "status": "rejected"}
    if act == "approve":
        # record in the ledger (deal_id 9e9+rid, same offset as portal-approved requests)
        if rid:
            db.execute(text("""INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method,
                  status, notes, tx_date, tx_month, created_at, updated_at)
                VALUES (:d,:l,'deposit',:a,'USD',:m,'approved','Manual deposit approved',
                  to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'), to_char(NOW(),'YYYY-MM'), NOW(), NOW())
                ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING"""),
                {"d": 9_000_000_000 + rid, "l": login, "a": amount, "m": method or "Manual"})
            db.execute(text("UPDATE portal_money_requests SET status='approved' WHERE id=:i"), {"i": rid})
        db.execute(text("UPDATE deposit_proofs SET verdict='approve' WHERE id=:i"), {"i": pid})
        # tick the card's DAILY + MONTHLY deposited counters (reset on day/month rollover) so the
        # daily & monthly limits actually enforce.
        if card_id:
            db.execute(text("""UPDATE payment_cards SET
                day_deposited = CASE WHEN day_anchor = CURRENT_DATE THEN COALESCE(day_deposited,0)+:a ELSE :a END,
                day_anchor = CURRENT_DATE,
                month_deposited = CASE WHEN date_trunc('month',COALESCE(month_anchor,DATE '2000-01-01'))
                                       = date_trunc('month',CURRENT_DATE) THEN COALESCE(month_deposited,0)+:a ELSE :a END,
                month_anchor = CURRENT_DATE
                WHERE id=:cid"""), {"a": amount, "cid": card_id})
        db.execute(text("""INSERT INTO call_actions (login, agent_id, action, note, created_at)
            VALUES (:l,:a,'deposit_approved',:n,NOW())"""),
            {"l": login, "a": uid, "n": f"Deposit ${amount:,.2f} via {method or 'manual'} APPROVED"})
        db.commit()
        # FEED THE DETECTOR: an approved deposit is a clean GENUINE reference — extends the per-sender
        # counter + (once enough) re-trains the txid series, so the AI gets sharper with every approval.
        DF.record_sample(db, method=_type_of(method), txid=feed_txid, sender_acct=feed_wallet,
                         receiver_acct=feed_recv, amount=amount, source="approved")
        return {"ok": True, "status": "approved", "note": "Recorded in ledger (simulation — no live MT move)"}
    return {"ok": False, "error": "unknown action"}


# ───────────────────────── PORTAL: available card + manual deposit ─────────────────────────
@portal.get("/deposit/card")
def available_card(method: str, amount: float = 0, db: Session = Depends(get_db),
                   client_id: int = Depends(get_current_client)):
    """Show ONE company card for this method, active at the current hour (holder on shift),
    chosen ROUND-ROBIN (least-recently-shown) and within its per-transaction / monthly limits."""
    _ensure(db)
    from datetime import datetime
    now = datetime.now()
    cur_min = now.hour * 60 + now.minute          # working hours are MINUTES-since-midnight now
    ct = _type_of(method)
    # ALL active cards for this method (we prefer on-shift, but fall back to any active card so the
    # method is never dead just because no holder is currently on shift — "use whatever we've got").
    rows = db.execute(text("""SELECT id, number, card_name, holder_name, account_number,
        daily_limit, monthly_limit, month_deposited, month_anchor, last_shown_at, times_shown,
        active_from, active_to, day_deposited, day_anchor
        FROM payment_cards WHERE card_type=:t AND is_active=TRUE"""), {"t": ct}).fetchall()
    today = now.date()

    def within_limits(r):
        # DAILY limit: today's total + this amount must not exceed it
        dl = float(r[5] or 0)
        day_used = float(r[13] or 0) if (r[14] and r[14] == today) else 0.0
        if dl > 0 and (day_used + amount) > dl:
            return False
        # MONTHLY limit
        ml = float(r[6] or 0)
        m_used = float(r[7] or 0) if (r[8] and r[8].year == now.year and r[8].month == now.month) else 0.0
        return not (ml > 0 and (m_used + amount) > ml)

    def on_shift(r):
        af, at = int(r[11] or 0), int(r[12] or 1440)
        return (af <= at and af <= cur_min < at) or (af > at and (cur_min >= af or cur_min < at))

    ok = [r for r in rows if within_limits(r)]
    if not ok:
        return {"available": False, "message": "No card is available for this amount right now — please try a smaller amount or another method."}
    on = [r for r in ok if on_shift(r)]
    pool = on if on else ok            # prefer on-shift; else any active card
    # round-robin: never-shown first, then least-recently-shown, then fewest times shown
    pool.sort(key=lambda r: (r[9] is not None, r[9] or now, r[10] or 0))
    pick = pool[0]
    db.execute(text("UPDATE payment_cards SET last_shown_at=NOW(), times_shown=COALESCE(times_shown,0)+1 WHERE id=:id"),
               {"id": pick[0]})
    db.commit()
    # client sees the NAME ON THE CARD (card_name) as the payee — NOT the internal back-office holder.
    return {"available": True, "card_id": pick[0], "number": pick[1], "card_name": pick[2] or "",
            "account_number": pick[4] or "", "on_shift": pick in on}


@portal.post("/deposit/manual")
def manual_deposit(payload: dict, db: Session = Depends(get_db), client_id: int = Depends(get_current_client)):
    """Client submits a manual deposit + screenshot (base64). AI OCRs + fraud-checks → verdict."""
    _ensure(db)
    login = int(payload.get("login") or 0)
    # go-live hardening: the deposit target must be one of THIS client's own accounts
    from portal_router import _assert_owns_login
    _assert_owns_login(db, client_id, login)
    amount = float(payload.get("amount") or 0)
    method = (payload.get("method") or "").strip()
    card_id = int(payload.get("card_id") or 0)
    txid = (payload.get("txid") or "").strip()
    wallet_id = (payload.get("wallet_id") or "").strip()
    image_b64 = payload.get("image") or ""
    img = b""
    if image_b64:
        try:
            img = base64.b64decode(image_b64.split(",")[-1])
        except Exception:
            img = b""
    path = ""
    if img:
        os.makedirs(PROOF_DIR, exist_ok=True)
        path = os.path.join(PROOF_DIR, f"dep_{client_id}_{int(amount)}_{len(img)}.jpg")
        try:
            open(path, "wb").write(img)
        except Exception:
            path = ""
    ocr = DF.ocr_deposit_proof(img) if img else {"_unavailable": "No screenshot uploaded"}
    assigned = ""
    if card_id:
        cr = db.execute(text("SELECT number, account_number FROM payment_cards WHERE id=:i"),
                        {"i": card_id}).fetchone()
        if cr:
            assigned = ",".join([x for x in (cr[0], cr[1]) if x])
    fr = DF.run_fraud_checks(db, method=_type_of(method), entered_txid=txid, entered_amount=amount,
                             ocr=ocr, entered_wallet_id=wallet_id, assigned_card=assigned,
                             entered_local_amount=float(payload.get("local_amount") or 0),
                             currency=(payload.get("currency") or "USD"), client_id=client_id)

    # ══════════════════════════════════════════════════════════════════════════════════════
    # REJECT (fake / duplicate / invalid): the receipt did NOT pass the checks. Per desk policy
    # we DO NOT create any deposit record — no Transactions row, and NOTHING listed for the
    # back-office to review. We only keep a lightweight AUDIT proof (request_id NULL, never
    # shown on the Transactions page / back-office list / to the client) so repeat fakes can
    # still be detected. The client is simply asked to upload a correct receipt.
    # ══════════════════════════════════════════════════════════════════════════════════════
    if fr["verdict"] == "reject":
        case = fr.get("case") or "invalid"
        reasons_txt = "; ".join(fr["reasons"])
        try:
            db.execute(text("""INSERT INTO deposit_proofs (request_id, client_id, login, method, amount, card_id,
                entered_txid, entered_wallet_id, ocr_txid, ocr_wallet_id, ocr_card, ocr_amount, ocr_date,
                image_path, verdict, reasons, ocr_raw) VALUES
                (NULL,:c,:l,:m,:a,:cd,:et,:ew,:ot,:ow,:oc,:oa,:od,:ip,'reject',:rs,:raw)"""), {
                "c": client_id, "l": login, "m": method, "a": amount, "cd": card_id or None,
                "et": txid, "ew": wallet_id, "ot": ocr.get("txid"), "ow": ocr.get("wallet_id"), "oc": ocr.get("card"),
                "oa": ocr.get("amount") if isinstance(ocr.get("amount"), (int, float)) else None, "od": ocr.get("date"),
                "ip": path, "rs": " | ".join(fr["reasons"]), "raw": json.dumps(ocr.get("_raw") or {})})
            db.commit()
        except Exception:
            db.rollback()

        # ── FAKE receipt: no record on the Transactions page — just ask for a real one, and warn
        #    about the loyalty penalty (applied on a repeat offence). ──
        if case == "fake":
            fakes = db.execute(text("""SELECT COUNT(*) FROM deposit_proofs WHERE client_id=:c AND verdict='reject'
                AND (reasons ILIKE '%forged%' OR reasons ILIKE '%altered%' OR reasons ILIKE '%company card%'
                     OR reasons ILIKE '%series%' OR reasons ILIKE '%future%' OR reasons ILIKE '%reused%'
                     OR reasons ILIKE '%old receipt%' OR reasons ILIKE '%fake%')"""), {"c": client_id}).scalar() or 0
            penalty = ""
            if fakes >= 2 and _downgrade_loyalty(db, client_id):
                penalty = " This is a repeat occurrence — your loyalty points have been reset and your tier has been lowered."
            warn = ("This receipt could not be verified as genuine, so it was not saved. "
                    "Please upload a clear photo of your original receipt. "
                    "Repeated invalid receipts may affect your loyalty tier." + penalty)
            return {"ok": False, "verdict": "reupload", "case": "fake", "reasons": fr["reasons"], "message": warn}

        # ── DUPLICATE still pending -> nudge the back-office to speed the ORIGINAL up (no new record) ──
        if case == "duplicate" and any(k in reasons_txt.lower() for k in ("in review", "hurry", "faster", "pending deposit")):
            try:
                cur2 = db.execute(text("""SELECT dp.card_id FROM deposit_proofs dp WHERE (dp.entered_txid=:t OR dp.ocr_txid=:t)
                                          AND dp.request_id IS NOT NULL ORDER BY dp.created_at ASC LIMIT 1"""), {"t": txid}).fetchone()
                hid = db.execute(text("SELECT holder_user_id FROM payment_cards WHERE id=:i"),
                                 {"i": cur2[0]}).scalar() if cur2 and cur2[0] else None
                if hid:
                    db.execute(text("""INSERT INTO notifications (user_id, title, message, type, link, is_read, created_at)
                        VALUES (:uid,:t,:m,'deposit_confirm',:lnk,FALSE,NOW())"""), {
                        "uid": hid, "t": "Please prioritise a pending review",
                        "m": f"A client re-sent a ${amount:,.0f} {method} deposit that is still pending your confirmation. Please review it as soon as possible.",
                        "lnk": "/payment-cards"})
                    db.commit()
            except Exception:
                db.rollback()
        return {"ok": False, "verdict": "reupload", "case": case, "dup": fr.get("dup"), "reasons": fr["reasons"],
                "message": reasons_txt if case == "duplicate"
                           else "We could not read this receipt, so nothing was saved. Please upload a clear photo showing the Transaction ID and date, then try again."}

    # ══════════════════════════════════════════════════════════════════════════════════════
    # PASSED the checks -> NOW create the deposit record (money request + proof) and list it for
    # the back-office to review. This is the ONLY path that writes a reviewable deposit.
    # ══════════════════════════════════════════════════════════════════════════════════════
    rid = db.execute(text("""INSERT INTO portal_money_requests (client_id, login, kind, amount, method, status)
        VALUES (:c,:l,'deposit',:a,:m,'pending_admin_review') RETURNING id"""), {
        "c": client_id, "l": login, "a": amount, "m": method}).scalar()
    db.execute(text("""INSERT INTO deposit_proofs (request_id, client_id, login, method, amount, card_id,
        entered_txid, entered_wallet_id, ocr_txid, ocr_wallet_id, ocr_card, ocr_amount, ocr_date,
        image_path, verdict, reasons, ocr_raw) VALUES
        (:r,:c,:l,:m,:a,:cd,:et,:ew,:ot,:ow,:oc,:oa,:od,:ip,:v,:rs,:raw)"""), {
        "r": rid, "c": client_id, "l": login, "m": method, "a": amount, "cd": card_id or None,
        "et": txid, "ew": wallet_id, "ot": ocr.get("txid"), "ow": ocr.get("wallet_id"), "oc": ocr.get("card"),
        "oa": ocr.get("amount") if isinstance(ocr.get("amount"), (int, float)) else None, "od": ocr.get("date"),
        "ip": path, "v": fr["verdict"], "rs": " | ".join(fr["reasons"]), "raw": json.dumps(ocr.get("_raw") or {})})
    db.commit()
    # passed the auto fraud checks -> alert the back-office member holding the RECEIVER card to
    # check their phone and confirm it. (The AI never auto-approves; a human always confirms.)
    try:
        h = db.execute(text("SELECT holder_user_id, holder_name, number FROM payment_cards WHERE id=:i"),
                       {"i": card_id}).fetchone() if card_id else None
        if h and h[0]:
            db.execute(text("""INSERT INTO notifications (user_id, title, message, type, link, is_read, created_at)
                VALUES (:uid, :t, :m, 'deposit_confirm', :lnk, FALSE, NOW())"""), {
                "uid": h[0], "t": "\U0001F4B0 Confirm a deposit",
                "m": f"Client deposited ${amount:,.0f} via {method} to your card {h[2] or ''}. "
                     f"Check your phone, then confirm it in Payment Cards → Manual deposit review.",
                "lnk": "/payment-cards"})
            db.commit()
    except Exception:
        db.rollback()
    # surface any soft WARNINGS (e.g. paid the wrong company card, small amount mismatch) to the client
    warns = [r for r in fr["reasons"] if r and not r.lower().startswith("passed automated")]
    if warns:
        msg = " ".join(warns) + " We've submitted it for review — approval may take longer."
    else:
        msg = "Deposit submitted — our team will review and approve it shortly."
    return {"ok": True, "verdict": "review", "warning": bool(warns), "reasons": fr["reasons"], "message": msg}
