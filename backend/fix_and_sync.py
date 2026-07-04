import sys, logging
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync_tx")

def get_tx_type(profit, comment):
    comment = (comment or "").lower()
    if "transfer" in comment:
        return "internal_transfer"
    if "credit" in comment:
        return "credit_in" if profit > 0 else "credit_out"
    if "bonus" in comment:
        return "bonus_deposit" if profit > 0 else "bonus_withdrawal"
    if profit > 0:
        return "deposit"
    if profit < 0:
        return "withdrawal"
    return None

def get_method(comment):
    comment = comment or ""
    if " - " in comment:
        parts = comment.split(" - ")
        if len(parts) >= 2:
            return parts[1].strip()
    return ""

def sync():
    db = SessionLocal()
    try:
        # Add unique constraint on deal_id if not exists
        log.info("Adding unique constraint on deal_id...")
        try:
            db.execute(text("""
                ALTER TABLE transactions 
                ADD CONSTRAINT transactions_deal_id_unique UNIQUE (deal_id)
            """))
            db.commit()
            log.info("Constraint added!")
        except Exception as e:
            db.rollback()
            log.info(f"Constraint already exists or skipped: {e}")

        max_tx = db.execute(text(
            "SELECT MAX(deal_id) FROM transactions WHERE deal_id IS NOT NULL"
        )).scalar() or 0
        log.info(f"Syncing deals after deal_id={max_tx}")

        rows = db.execute(text("""
            SELECT deal_id, login, action, profit, comment, deal_time
            FROM deals
            WHERE action IN (2, 3)
            AND profit != 0
            AND deal_id > :last
            ORDER BY deal_time ASC
        """), {"last": max_tx}).fetchall()

        log.info(f"Found {len(rows)} deals to process")

        count = 0
        skipped = 0
        for deal_id, login, action, profit, comment, deal_time in rows:
            profit = float(profit or 0)
            tx_type = get_tx_type(profit, comment)
            if not tx_type:
                skipped += 1
                continue

            amount = abs(profit)
            method = get_method(comment)

            try:
                tx_date = datetime.fromtimestamp(int(deal_time)) if deal_time else None
            except:
                tx_date = None

            db.execute(text("""
                INSERT INTO transactions (deal_id, login, tx_type, amount, method, status, tx_date, notes, created_at)
                VALUES (:did, :login, :tx_type, :amount, :method, 'approved', :tx_date, :notes, NOW())
                ON CONFLICT (deal_id) DO NOTHING
            """), {
                "did": deal_id, "login": login, "tx_type": tx_type,
                "amount": amount, "method": method,
                "tx_date": tx_date, "notes": comment or ""
            })
            count += 1
            if count % 5000 == 0:
                db.commit()
                log.info(f"  Saved {count}...")

        db.commit()
        log.info(f"Done! {count} new transactions, {skipped} skipped")

        latest = db.execute(text(
            "SELECT MAX(tx_date) FROM transactions WHERE tx_type='deposit'"
        )).scalar()
        log.info(f"Latest deposit now: {latest}")

    except Exception as e:
        db.rollback()
        log.error(f"Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    sync()
