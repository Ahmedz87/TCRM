"""
deposit_fraud.py — manual-deposit screenshot OCR + fraud checks (Qi card / Zain Cash / Fastpay /
Sham Cash, etc.). The desk's rules:
  • OCR the uploaded proof → extract sender Wallet ID, receiver Card number, amount, transaction ID, date.
  • Reject if the transaction ID was already used (duplicate).
  • Reject + flag if the date is in the FUTURE (faked-forward).
  • Validate the transaction-ID SERIES — Q-card IDs share a fixed series; an ID that doesn't match the
    learned pattern is fake. The pattern is configurable (refined from the desk's 50 sample IDs).
  • Cross-check the OCR'd amount / txid against what the client typed.
Verdict: 'approve' | 'review' | 'reject' with reasons. AI OCR uses the same Claude key as the KYC/chat
bot (gitignored ai_config.py) — gated off until the key is present, like the rest of the AI features.
"""
import re
from datetime import datetime, timezone, timedelta
from sqlalchemy import text


def ensure_tables(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS deposit_proofs (
        id SERIAL PRIMARY KEY, request_id INT, client_id INT, login BIGINT, method VARCHAR(40),
        amount NUMERIC, card_id INT,
        entered_txid TEXT, entered_wallet_id TEXT,
        ocr_txid TEXT, ocr_wallet_id TEXT, ocr_card TEXT, ocr_amount NUMERIC, ocr_date TEXT,
        image_path TEXT, verdict VARCHAR(16), reasons TEXT, ocr_raw JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS deposit_txid_series (
        method VARCHAR(40) PRIMARY KEY, pattern TEXT, sample TEXT, min_len INT, max_len INT,
        updated_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.commit()


# ---- AI OCR (Claude) — extract the payment fields from the screenshot --------------------------
def _detect_mime(image_bytes: bytes) -> str:
    """Real media type from the magic bytes. Phone screenshots are usually PNG/WebP, NOT JPEG —
    declaring the wrong type makes the Anthropic vision API reject the image (400), which used to
    make every PNG receipt silently skip OCR and slip through as 'needs manual review'."""
    sig = image_bytes[:12]
    if sig[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if sig[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if sig[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if sig[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def ocr_deposit_proof(image_bytes: bytes, mime: str = None, model: str = "claude-opus-4-8") -> dict:
    """Returns {txid, wallet_id, card, amount, date, is_receipt, doc_type} or {'_unavailable': reason}.
    `model` lets the bulk fraud-scan use a cheaper/faster vision model (e.g. claude-sonnet-4-6) for the
    digits-heavy receipt fields; the live approval path keeps the Opus default. `mime` is auto-detected
    from the image bytes when not given (screenshots are commonly PNG)."""
    try:
        import ai_config
        key = getattr(ai_config, "ANTHROPIC_API_KEY", "") or getattr(ai_config, "CLAUDE_API_KEY", "")
    except Exception:
        key = ""
    if not key:
        return {"_unavailable": "AI key not configured (paste it into ai_config.py to enable OCR)"}
    if not mime:
        mime = _detect_mime(image_bytes)
    import base64, json, anthropic
    b64 = base64.standard_b64encode(image_bytes).decode()
    prompt = ("You are verifying a DEPOSIT PROOF for a broker. Look at the image and return ONLY JSON with keys: "
              "is_receipt (true ONLY if this is a genuine bank/e-wallet MONEY-TRANSFER or PAYMENT receipt "
              "showing a completed transaction; false for anything else — a selfie, an ID, a random photo, a "
              "blank/irrelevant screenshot, a chat, a webpage, etc.), "
              "doc_type (a 2-4 word description of what the image actually is, e.g. 'Qi transfer receipt', "
              "'national ID card', 'random photo'), "
              "transaction_id (the reference/transaction number), wallet_id (the SENDER card/account number), "
              "receiver (the RECEIVER card/account number), amount (number), date (YYYY-MM-DD HH:MM if visible). "
              "Use null for anything not visible. Be strict: if it is NOT clearly a payment/transfer receipt, "
              "set is_receipt=false.")
    try:
        cli = anthropic.Anthropic(api_key=key)
        msg = cli.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
            {"type": "text", "text": prompt}]}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        j = json.loads(m.group(0)) if m else {}
        return {"txid": str(j.get("transaction_id") or "").strip(), "wallet_id": str(j.get("wallet_id") or "").strip(),
                "card": str(j.get("receiver") or "").strip(), "amount": j.get("amount"),
                "date": str(j.get("date") or "").strip(),
                "is_receipt": (None if j.get("is_receipt") is None else bool(j.get("is_receipt"))),
                "doc_type": str(j.get("doc_type") or "").strip(), "_raw": j}
    except Exception as e:
        return {"_unavailable": f"OCR error: {str(e)[:120]}"}


# ---- Fraud checks ------------------------------------------------------------------------------
def run_fraud_checks(db, *, method: str, entered_txid: str, entered_amount: float, ocr: dict,
                     entered_wallet_id: str = "", assigned_card: str = "",
                     entered_local_amount: float = 0, currency: str = "USD", client_id: int = 0) -> dict:
    """Returns {verdict, reasons[]}. verdict: approve | review | reject.
    assigned_card = the company card/account the client was shown (comma-joined number,account)."""
    reasons, hard_reject = [], False
    is_dup = is_fake = False
    txid = (ocr.get("txid") or entered_txid or "").strip()

    # 0a) IS THIS EVEN A RECEIPT? An arbitrary/unrelated image (the OCR says it isn't a receipt, or it
    #     has none of the receipt fields) must be REJECTED — never silently queued for review.
    if not ocr.get("_unavailable"):
        _recv = re.sub(r"\D", "", str(ocr.get("card") or ""))
        has_fields = bool(txid) or bool(_recv) or (ocr.get("amount") not in (None, "", 0))
        if ocr.get("is_receipt") is False or not has_fields:
            what = ocr.get("doc_type") or "the uploaded image"
            reasons.append(f"This doesn't look like a valid payment receipt ({what}). Please upload the actual "
                           "transfer receipt clearly showing the Transaction ID, amount and date.")
            return {"verdict": "reject", "reasons": reasons, "case": "invalid"}

    # 0) RECEIVER match — the receipt's beneficiary account must be a COMPANY card.
    #    • paid the card we SHOWED this client  -> fine
    #    • paid a DIFFERENT but still-real company card (client reused a card from a previous deposit)
    #        -> NOT forgery: WARN the client (may delay / risk rejection), keep it for human review
    #    • paid an account that is NOT any company card -> wrong/forged -> hard reject
    ocr_recv = re.sub(r"\D", "", str(ocr.get("card") or ""))

    def _match(x, y):
        return x == y or (len(x) >= 6 and len(y) >= 6 and (x.endswith(y) or y.endswith(x)))
    if ocr_recv and assigned_card:
        accepted = {re.sub(r"\D", "", a) for a in assigned_card.split(",") if re.sub(r"\D", "", a)}
        if accepted and not any(_match(ocr_recv, a) for a in accepted):
            # is the receiver ANY of our company cards (active or historical)?
            try:
                allc = db.execute(text("SELECT number, account_number FROM payment_cards")).fetchall()
            except Exception:
                allc = []
            company_nums = set()
            for cn, an in allc:
                for v in (cn, an):
                    dd = re.sub(r"\D", "", str(v or ""))
                    if dd:
                        company_nums.add(dd)
            is_company = any(_match(ocr_recv, cnum) for cnum in company_nums)
            if is_company:
                shown = ", ".join(sorted(accepted)) if accepted else "the card we showed you"
                reasons.append(f"You transferred to a DIFFERENT company card ({ocr_recv}) than the one we asked "
                               f"you to use ({shown}). Your deposit will still be reviewed, but paying the wrong "
                               "card can DELAY approval or cause it to be REJECTED and the funds lost — please "
                               "always use the exact card we show you for each deposit.")  # soft warning, no hard_reject
            else:
                reasons.append(f"Receipt was sent to account {ocr_recv}, which is NOT one of our company cards — wrong/forged.")
                hard_reject = True

    # 1) duplicate receipt — the SAME transaction id was already submitted. Tell the client exactly
    #    what happened (already credited, or still under review) + how long ago, so it's not a blunt
    #    "fake" accusation. The earliest prior proof + its money-request status drive the message.
    if txid:
        prev = db.execute(text("""
            SELECT dp.created_at, LOWER(COALESCE(pmr.status,'')), COALESCE(dp.amount, pmr.amount), dp.client_id
            FROM deposit_proofs dp
            LEFT JOIN portal_money_requests pmr ON pmr.id = dp.request_id
            WHERE (dp.entered_txid=:t OR dp.ocr_txid=:t)
              -- only receipts that were actually SUBMITTED count as a prior use; audit-only
              -- rows from earlier failed attempts (request_id NULL) must NOT flag a corrected
              -- re-upload with the same txid as a "duplicate".
              AND dp.request_id IS NOT NULL
            ORDER BY dp.created_at ASC NULLS LAST LIMIT 1
        """), {"t": txid}).fetchone()
        if prev:
            when, status, pamt, prev_cid = prev[0], (prev[1] or ""), (prev[2] or 0), prev[3]
            # elapsed since the ORIGINAL upload, friendly "X hours Y minutes ago" (minute precision)
            ago = ""
            try:
                if when:
                    w = when if getattr(when, "tzinfo", None) else when.replace(tzinfo=timezone.utc)
                    d = datetime.now(timezone.utc) - w
                    days, hrs, mins = d.days, int(d.seconds // 3600), int((d.seconds % 3600) // 60)
                    if days:
                        ago = f"{days} day{'s' if days != 1 else ''} {hrs} hour{'s' if hrs != 1 else ''} ago"
                    elif hrs:
                        ago = f"{hrs} hour{'s' if hrs != 1 else ''} {mins} minute{'s' if mins != 1 else ''} ago"
                    else:
                        ago = f"{mins} minute{'s' if mins != 1 else ''} ago"
            except Exception:
                ago = ""
            same_user = bool(client_id) and bool(prev_cid) and int(prev_cid) == int(client_id)
            is_approved = status in ("approved", "completed", "credited", "done", "success")
            is_pending = status in ("pending_admin_review", "pending", "review", "processing", "pending_simulation")
            # A matched receipt is always blocked from double-crediting; the MESSAGE differs by who sent it.
            if same_user:
                # the SAME client re-sent their OWN receipt — reassure, never accuse of fraud.
                if is_approved:
                    reasons.append(f"This receipt has already been used to fund your account (+${float(pamt):,.0f}). "
                                   "Each receipt can be used for one deposit only — please upload a new receipt for your next deposit.")
                    return {"verdict": "reject", "reasons": reasons, "case": "duplicate", "dup": "approved"}
                elif is_pending:
                    reasons.append(f"You have already submitted this receipt {ago} and it is currently under review. "
                                   "There is no need to resend it — we have notified our team to prioritise your pending deposit.")
                    return {"verdict": "reject", "reasons": reasons, "case": "duplicate", "dup": "pending"}
                else:
                    reasons.append("This receipt has already been used. Please upload a new receipt for a new deposit.")
                    return {"verdict": "reject", "reasons": reasons, "case": "duplicate", "dup": "used"}
            else:
                # a DIFFERENT account already used this exact receipt -> reuse / forgery.
                reasons.append("This receipt has already been used by another account and cannot be reused. "
                               "Please upload your own, unused transfer receipt.")
                return {"verdict": "reject", "reasons": reasons, "case": "fake"}

    # 2) future / altered date
    ds = (ocr.get("date") or "").strip()
    if ds:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(ds[:16], fmt)
                if dt.date() > (datetime.now(timezone.utc) + timedelta(days=1)).date():
                    reasons.append(f"Receipt date {ds} is in the FUTURE — forged."); hard_reject = True
                break
            except Exception:
                continue

    # 2b) date EMBEDDED in the transaction id (first 8 digits = YYYYMMDD). Qi/SuperQi txids encode the
    #     real transfer date, so a forged visible date won't match it, and a future txid-date is a fake.
    digits = re.sub(r"\D", "", txid)
    if len(digits) >= 8:
        try:
            tdt = datetime.strptime(digits[:8], "%Y%m%d")
            if 2020 <= tdt.year <= 2035:                      # plausible -> treat as the embedded txid date
                if tdt.date() > (datetime.now(timezone.utc) + timedelta(days=1)).date():
                    reasons.append(f"Transaction-ID date {tdt.date()} is in the FUTURE — forged."); hard_reject = True
                if ds:                                        # cross-check vs the visible/OCR date
                    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y/%m/%d"):
                        try:
                            vdt = datetime.strptime(ds[:16], fmt)
                            if abs((vdt.date() - tdt.date()).days) > 1:
                                reasons.append(f"Visible date {vdt.date()} doesn't match the transaction-ID date {tdt.date()} — altered receipt."); hard_reject = True
                            break
                        except Exception:
                            continue
        except Exception:
            pass

    # 3) transaction-id SERIES pattern (per method) — learned from the desk's samples
    if txid:
        row = db.execute(text("SELECT pattern, min_len, max_len FROM deposit_txid_series WHERE method=:m"),
                         {"m": method}).fetchone()
        if row and row[0]:
            ok = True
            if not re.match(row[0], txid):
                ok = False
            if row[1] and len(re.sub(r"\D", "", txid)) < row[1]:
                ok = False
            if not ok:
                reasons.append(f"Transaction ID doesn't match the known {method} series — likely fake."); hard_reject = True

    # 4b) per-sender COUNTER — the 12-digit tail (after date+fixed block) is a monotonically-INCREASING
    #     counter per sender (PROVEN: one sender's 12 deposits over 3 months were perfectly ordered, 0
    #     violations, even across 3 of his accounts). So a new deposit whose counter is LOWER than that
    #     sender's highest recorded counter is an OLD / reused / forged receipt. Keyed on the sender's
    #     wallet (a per-account subsequence of a monotonic sequence is still monotonic). FLAG for now
    #     (reference values are photo-transcribed) — promote to auto-reject once clean samples accrue.
    if txid and method == "qcard":
        d = re.sub(r"\D", "", txid)
        if len(d) == 37 and d[8:25] == "10121420010100166":
            wallet = (ocr.get("wallet_id") or entered_wallet_id or "").strip()
            if wallet:
                try:
                    cur = int(d[25:])
                    mx_app = db.execute(text("SELECT MAX(CAST(sender_id||txn_part AS BIGINT)) FROM "
                        "qi_txid_samples WHERE sender_acct=:w AND source='approved'"), {"w": wallet}).scalar()
                    mx_ref = db.execute(text("SELECT MAX(CAST(sender_id||txn_part AS BIGINT)) FROM "
                        "qi_txid_samples WHERE sender_acct=:w AND COALESCE(source,'seed')<>'rejected'"), {"w": wallet}).scalar()
                    if mx_app is not None and cur < int(mx_app):
                        # reference is a CLEAN approved deposit -> confident hard reject
                        reasons.append(f"Counter {d[25:]} is LOWER than this sender's last APPROVED deposit ({mx_app}) — reused/old receipt."); hard_reject = True
                    elif mx_ref is not None and cur < int(mx_ref):
                        reasons.append(f"Counter {d[25:]} is lower than this sender's last seen ({mx_ref}) — possible old/reused receipt, verify carefully.")
                except Exception:
                    pass

    # 4c) GLOBAL-SEQUENCE vs DATE (Jul 2026 study, 3,382 clean receipts): the last 8 digits of a Qi
    #     txid are a SYSTEM-WIDE counter advancing ~25.5k/day (2.63M Oct-25 -> 6.61M Jun-26); 99% of
    #     genuine receipts sit within ±256k of their day's median (qi_seq_curve). A forged txid, or an
    #     old receipt with BOTH dates photoshopped (which beats check 2b), lands far off the curve:
    #     ~16 days of drift (>400k) -> review flag; ~40+ days (>1M) -> hard reject.
    if txid and method == "qcard":
        d = re.sub(r"\D", "", txid)
        if len(d) == 37 and d[8:25] == "10121420010100166":
            try:
                tdt = datetime.strptime(d[:8], "%Y%m%d").date()
                seq = int(d[29:])
                lo = db.execute(text("SELECT day, median_seq FROM qi_seq_curve WHERE day<=:d "
                                     "ORDER BY day DESC LIMIT 1"), {"d": tdt}).fetchone()
                hi = db.execute(text("SELECT day, median_seq FROM qi_seq_curve WHERE day>=:d "
                                     "ORDER BY day ASC LIMIT 1"), {"d": tdt}).fetchone()
                expected = slack = None
                if lo and hi and hi[0] != lo[0]:      # interpolate between the two nearest curve days
                    frac = (tdt - lo[0]).days / (hi[0] - lo[0]).days
                    expected, slack = lo[1] + frac * (hi[1] - lo[1]), 0
                elif lo and hi:                        # exact curve day
                    expected, slack = lo[1], 0
                elif lo or hi:                         # extrapolate at ~25.5k/day, widening the band
                    ref = lo or hi
                    gap = abs((tdt - ref[0]).days)
                    expected = ref[1] + (25500 * gap if lo else -25500 * gap)
                    slack = 40000 * gap
                if expected is not None:
                    dev = abs(seq - expected)
                    if dev > 1_000_000 + slack:
                        reasons.append(f"Transaction-ID sequence {seq:,} is impossible for {tdt} "
                                       f"(Qi system was at ~{int(expected):,} that day) — forged/reused receipt.")
                        hard_reject = True
                    elif dev > 400_000 + slack:
                        reasons.append(f"Transaction-ID sequence {seq:,} is unusual for {tdt} "
                                       f"(expected ~{int(expected):,}) — possible old/edited receipt, verify.")
            except Exception:
                pass

    # 4d) 4-digit SENDER-BLOCK (Jul 2026 study: tail[:4] is deterministic per sender wallet — 100%
    #     across 211 senders). If this wallet's known block differs, the txid wasn't generated by
    #     this sender -> strong forgery signal (review, not auto-reject: 4 digits can collide and
    #     references may be OCR'd).
    if txid and method == "qcard":
        d = re.sub(r"\D", "", txid)
        if len(d) == 37 and d[8:25] == "10121420010100166":
            wallet = (ocr.get("wallet_id") or entered_wallet_id or "").strip()
            if wallet:
                try:
                    blocks = [r[0] for r in db.execute(text(
                        "SELECT DISTINCT substr(sender_id||txn_part,1,4) FROM qi_txid_samples "
                        "WHERE sender_acct=:w AND length(txid)=37 AND COALESCE(source,'seed')<>'rejected'"),
                        {"w": wallet}).fetchall() if r[0]]
                    if blocks and d[25:29] not in blocks:
                        reasons.append(f"Transaction-ID sender-block {d[25:29]} doesn't match this "
                                       f"sender's known block ({'/'.join(blocks[:3])}) — txid likely not "
                                       f"from this wallet, verify the receipt.")
                except Exception:
                    pass

    # 4e) per-CLIENT sender-block registry (Jul 2026 — the strongest everyday check). Each client's
    #     Qi history has known sender-blocks: the txid's digits 25-29 (4) = the sender WALLET's fixed
    #     id, digit 29 (5th) = the top of the global sequence (rolls +1 only every ~4 months, UP only),
    #     digit 30 (6th) rolls ~every 39 days. So: a deposit whose 4-block this client has NEVER used
    #     = a new/unknown wallet — could be a legit new exchanger OR a receipt copied from someone else
    #     -> FLAG. If the 4-block IS theirs but the 5-digit is BELOW their last from that wallet -> an
    #     old/backdated receipt -> FLAG. (client_id is always known at deposit time, unlike the wallet.)
    if txid and method == "qcard" and client_id:
        d = re.sub(r"\D", "", txid)
        if len(d) == 37 and d[8:25] == "10121420010100166":
            b4, b5 = d[25:29], d[25:30]
            try:
                login = db.execute(text("SELECT login FROM clients WHERE id=:i"), {"i": client_id}).scalar()
                known = db.execute(text("SELECT block4, max_seq FROM client_sender_blocks "
                                        "WHERE client_login=:c"), {"c": login}).fetchall() if login else []
                if known:
                    # tolerate single-digit OCR misreads of the client's real block: a candidate is
                    # "known" if it exactly matches, OR differs from a known block by just one digit.
                    blocks4 = {r[0] for r in known}
                    def _one_off(a, b):
                        return len(a) == len(b) == 4 and sum(x != y for x, y in zip(a, b)) <= 1
                    if b4 not in blocks4 and not any(_one_off(b4, k) for k in blocks4):
                        reasons.append(f"Sender-block {b4} is NEW for this client (they've only ever "
                                       f"used {'/'.join(sorted(blocks4)[:3])}) — verify it's really their "
                                       f"wallet and not a receipt copied from another person.")
                    # 4f) the 8-digit sequence only ever INCREASES over time. This deposit is newer than
                    #     everything in the client's history, so its sequence must be >= their highest
                    #     ON-CURVE sequence from the same wallet. Lower = an OLD receipt of their own,
                    #     reused (and small enough to slip inside the curve's ±400k band). Reference is
                    #     built only from on-curve deposits, so a misread can't inflate it.
                    seq = int(d[29:])
                    ref = None
                    for bk, ms in known:
                        if ms is not None and (bk == b4 or _one_off(bk, b4)):
                            ref = ms if ref is None else max(ref, ms)
                    if ref is not None and seq < ref - 50_000:
                        reasons.append(f"Transfer sequence {seq:,} is LOWER than this client's most "
                                       f"recent transfer from the same wallet ({ref:,}) — an older/"
                                       f"already-used receipt (Qi sequence numbers only go up). Verify.")
            except Exception:
                pass

    # 4) amount mismatch (what the client said they sent vs the receipt). For a LOCAL-currency method
    #    the receipt is in local units (IQD/SYP), so compare to the local amount — NOT the USD value.
    try:
        oa = float(ocr.get("amount")) if ocr.get("amount") not in (None, "") else None
        local = currency and currency != "USD" and float(entered_local_amount or 0) > 0
        compare_to = float(entered_local_amount) if local else float(entered_amount or 0)
        unit = currency if local else "$"
        tol = max(1.0, 0.02 * compare_to)   # 2% tolerance (rounding / partial fees)
        if oa is not None and compare_to and abs(oa - compare_to) > tol:
            reasons.append(f"Amount mismatch: you entered {compare_to:,.0f} {unit} but the receipt shows {oa:,.0f} {unit}.")
    except Exception:
        pass

    # The AI ONLY rejects fakes — it NEVER auto-approves. A human (back-office) always does the
    # final approval. So a clean pass returns 'review' (queued for a person), not 'approve'.
    if hard_reject:
        txt = " ".join(reasons).lower()
        if any(k in txt for k in ("forged", "altered", "future", "doesn't match", "wrong", "series",
                                  "lower than", "reused", "old receipt", "not the company card")):
            case = "fake"
        elif any(k in txt for k in ("already", "under review", "used again", "already submitted")):
            case = "duplicate"
        else:
            case = "fake"
        return {"verdict": "reject", "reasons": reasons, "case": case}
    if ocr.get("_unavailable"):
        return {"verdict": "review", "reasons": reasons + ["OCR unavailable — needs manual review."]}
    if reasons:
        return {"verdict": "review", "reasons": reasons}
    return {"verdict": "review", "reasons": ["Passed automated fraud checks — awaiting back-office approval."]}


def _common_prefix(strs):
    if not strs:
        return ""
    pref = strs[0]
    for d in strs[1:]:
        i = 0
        while i < len(pref) and i < len(d) and pref[i] == d[i]:
            i += 1
        pref = pref[:i]
    return pref


def _looks_dated(d):
    """True if the first 8 digits parse as a plausible YYYYMMDD date (Qi/SuperQi txids embed the date)."""
    if len(d) < 8:
        return False
    try:
        y = int(d[:4])
        dt = datetime.strptime(d[:8], "%Y%m%d")
        return 2020 <= y <= 2035 and dt is not None
    except Exception:
        return False


def learn_series(db, method: str, sample_ids: list):
    """Build a regex/length pattern for a method's transaction IDs from sample IDs (the desk's 50).
    DATE-AWARE: if the IDs embed an 8-digit YYYYMMDD date prefix (Qi/SuperQi), the fixed series block
    sits AFTER the date — so we strip the date before finding the common block, then the learned
    pattern allows ANY 8-digit date followed by that fixed block (e.g. ^\\d{8}10121420010100166...)."""
    digits = [re.sub(r"\D", "", s) for s in sample_ids if s and s.strip()]
    if not digits:
        return
    lens = [len(d) for d in digits]
    dated = sum(1 for d in digits if _looks_dated(d)) >= max(1, int(0.8 * len(digits)))
    if dated:
        block = _common_prefix([d[8:] for d in digits if len(d) > 8])   # fixed block after the date
        pattern = r"^\d{8}" + re.escape(block) + r"\d*$" if block else r"^\d{8}\d+$"
        learned_prefix = "<YYYYMMDD>" + block
    else:
        pref = _common_prefix(digits)
        pattern = "^" + re.escape(pref) + r"\d*$" if pref else r"^\d+$"
        learned_prefix = pref
    db.execute(text("""INSERT INTO deposit_txid_series (method, pattern, sample, min_len, max_len, updated_at)
        VALUES (:m,:p,:s,:lo,:hi,NOW())
        ON CONFLICT (method) DO UPDATE SET pattern=:p, sample=:s, min_len=:lo, max_len=:hi, updated_at=NOW()"""),
        {"m": method, "p": pattern, "s": sample_ids[0], "lo": min(lens), "hi": max(lens)})
    db.commit()
    return {"method": method, "pattern": pattern, "common_prefix": learned_prefix,
            "dated": dated, "len": [min(lens), max(lens)], "count": len(digits)}


def _ensure_samples(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS qi_txid_samples (
        id SERIAL PRIMARY KEY, txid TEXT UNIQUE, txn_at TIMESTAMP, amount NUMERIC,
        sender_name TEXT, sender_acct TEXT, receiver_name TEXT, receiver_acct TEXT,
        date_part TEXT, fixed_part TEXT, sender_id TEXT, txn_part TEXT,
        source TEXT DEFAULT 'seed', created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.execute(text("ALTER TABLE qi_txid_samples ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'seed'"))


def record_sample(db, *, method="", txid="", sender_acct="", sender_name="", receiver_acct="",
                  receiver_name="", amount=None, txn_at=None, source="approved"):
    """Feed a DECIDED deposit into the learning set (qi_txid_samples). source='approved' = a clean,
    human-verified GENUINE reference (extends the per-sender counter / series); 'rejected' is kept for
    analysis but never used as a genuine reference. Idempotent per txid. Auto-retrains the qcard series
    once enough approved samples exist. Safe to call inside the approval txn (own try/except)."""
    if not txid:
        return
    try:
        _ensure_samples(db)
        d = re.sub(r"\D", "", txid)
        dp = fx = sid = tp = None
        if len(d) == 37:
            dp, fx, sid, tp = d[:8], d[8:25], d[25:31], d[31:]
        db.execute(text("""INSERT INTO qi_txid_samples
            (txid,txn_at,amount,sender_name,sender_acct,receiver_name,receiver_acct,date_part,fixed_part,sender_id,txn_part,source)
            VALUES (:t,:at,:amt,:sn,:sa,:rn,:ra,:dp,:fx,:sid,:tp,:src)
            ON CONFLICT (txid) DO UPDATE SET source=EXCLUDED.source,
              sender_acct=COALESCE(NULLIF(EXCLUDED.sender_acct,''), qi_txid_samples.sender_acct),
              receiver_acct=COALESCE(NULLIF(EXCLUDED.receiver_acct,''), qi_txid_samples.receiver_acct)"""),
            {"t": txid.strip(), "at": txn_at, "amt": amount, "sn": sender_name, "sa": sender_acct,
             "rn": receiver_name, "ra": receiver_acct, "dp": dp, "fx": fx, "sid": sid, "tp": tp, "src": source})
        db.commit()
        # self-improve the qcard series from approved samples once there are enough clean ones
        if source == "approved" and method == "qcard":
            n = db.execute(text("SELECT COUNT(*) FROM qi_txid_samples WHERE source='approved' AND length(txid)=37")).scalar() or 0
            if n >= 30:
                ids = [r[0] for r in db.execute(text(
                    "SELECT txid FROM qi_txid_samples WHERE source='approved' AND length(txid)=37")).fetchall()]
                learn_series(db, "qcard", ids)
    except Exception:
        db.rollback()
