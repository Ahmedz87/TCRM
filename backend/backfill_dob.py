"""
backfill_dob.py — populate clients.date_of_birth (empty for almost everyone) from the two places a
birthday actually gets captured today:
  1) registrations.date_of_birth  (portal sign-up form — already 'YYYY-MM-DD')
  2) registrations.ocr_fields->>'date_of_birth'  (KYC ID OCR — normalised to 'YYYY-MM-DD')

Matches a registration to a client by MT login (registrations.mt_login OR account_login = clients.login).
Only writes where clients.date_of_birth is currently empty (additive, idempotent). Safe to re-run.
The birthday bonus (birthday_engine.py) keys off clients.date_of_birth, so this is what makes the
feature light up for real clients as more of them register / verify.

Usage:  python backfill_dob.py [--dry-run]
"""
from __future__ import annotations
import sys
from sqlalchemy import text
from database import SessionLocal
from birthday_engine import _parse_dob

DRY = "--dry-run" in sys.argv


def main():
    db = SessionLocal()
    filled_reg = filled_ocr = 0
    try:
        # ── 1) canonical registrations.date_of_birth → clients (bulk, regex-guarded) ──
        reg_rows = db.execute(text("""
            SELECT c.id, c.login, r.date_of_birth
            FROM clients c
            JOIN registrations r
              ON (r.mt_login = c.login OR r.account_login = c.login)
            WHERE (c.date_of_birth IS NULL OR c.date_of_birth = '')
              AND r.date_of_birth ~ '^\\d{4}-\\d{2}-\\d{2}'
        """)).fetchall()
        seen = set()
        for cid, login, dob in reg_rows:
            if cid in seen:
                continue
            seen.add(cid)
            iso = (dob or "")[:10]
            if not DRY:
                db.execute(text("UPDATE clients SET date_of_birth=:d WHERE id=:id AND (date_of_birth IS NULL OR date_of_birth='')"),
                           {"d": iso, "id": cid})
            filled_reg += 1

        # ── 2) KYC OCR date_of_birth → clients (normalise arbitrary date formats) ──
        ocr_rows = db.execute(text("""
            SELECT c.id, c.login, r.ocr_fields->>'date_of_birth'
            FROM clients c
            JOIN registrations r
              ON (r.mt_login = c.login OR r.account_login = c.login)
            WHERE (c.date_of_birth IS NULL OR c.date_of_birth = '')
              AND COALESCE(r.ocr_fields->>'date_of_birth','') <> ''
        """)).fetchall()
        for cid, login, raw in ocr_rows:
            if cid in seen:
                continue
            d = _parse_dob(raw)
            if not d:
                continue
            seen.add(cid)
            if not DRY:
                db.execute(text("UPDATE clients SET date_of_birth=:d WHERE id=:id AND (date_of_birth IS NULL OR date_of_birth='')"),
                           {"d": d.isoformat(), "id": cid})
            filled_ocr += 1

        if not DRY:
            db.commit()
        total = db.execute(text("SELECT COUNT(*) FROM clients WHERE date_of_birth IS NOT NULL AND date_of_birth<>''")).scalar()
        print(f"{'[DRY-RUN] would fill' if DRY else 'filled'}: {filled_reg} from registrations.date_of_birth, "
              f"{filled_ocr} from KYC OCR. Clients with a DOB now: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
