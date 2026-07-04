"""
sync_transactions.py — converts deals to transactions
Run: python sync_transactions.py
"""
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
    """Build MT5 balance/credit/bonus deals (action 2/3/6) into the transactions table.

    Set-based, idempotent INSERT of ONLY the deals that aren't already transactions
    (NOT EXISTS on deal_id) — covers actions 2,3,6, immune to the old `deal_id > MAX`
    bug that broke once MT4 transactions (deal_id +4e9 offset) raised the max above every
    new MT5 deal_id. Mirrors build_transactions.py so the two stay consistent.
    """
    db = SessionLocal()
    try:
        db.execute(text("""CREATE UNIQUE INDEX IF NOT EXISTS transactions_deal_id_uq
                           ON transactions(deal_id) WHERE deal_id IS NOT NULL"""))
        db.commit()
        res = db.execute(text("""
            INSERT INTO transactions
                (deal_id, login, client_id, tx_type, amount, currency, method, status,
                 notes, tx_date, tx_month, created_at, updated_at)
            SELECT
                d.deal_id, d.login, d.client_id,
                -- FULL classifier, kept in sync with build_transactions.py: reverts, abuse clawbacks,
                -- internal fixes/negative-cover/sync are NOT deposits/withdrawals (else they leak in
                -- via this real-time sync). A comment that NAMES a real payment method wins (real deposit).
                CASE
                    WHEN d.action = 2 AND d.comment ILIKE '%transfer%' THEN 'internal_transfer'
                    WHEN d.action = 2 AND d.comment ~* 'revert.*withdraw' THEN 'withdrawal_revert'
                    WHEN d.action = 2 AND d.comment ~* 'abus' THEN 'abuse_clawback'
                    WHEN d.action = 2
                         AND d.comment !~* '(qi ?card|zain\w*|asiapay|asiahawala|usdt|tether|al ?taif|sham|perfect ?money|wallet|advcash|airtm|paymaxis|bridger|ptop|web ?money|cryptomus|payeer|fasapay)'
                         AND (COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'),' - ',2)),''), d.platform) = 'MT5'
                              OR COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'),' - ',2)),''), d.platform)
                                 ~* '(deposit\s*[/ ]?\s*fix|withdraw\w*\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back|credit\s*(in|out)|bonus\s*adjustment|\ysync\y)')
                         THEN CASE WHEN d.comment ~* 'negative\s*balance' THEN 'negative_cover' ELSE 'balance_fix' END
                    WHEN d.action = 2 AND d.profit > 0 THEN 'deposit'
                    WHEN d.action = 2 AND d.profit < 0 THEN 'withdrawal'
                    WHEN d.action IN (3,6) AND d.profit > 0 THEN 'bonus_deposit'
                    WHEN d.action IN (3,6) AND d.profit < 0 THEN 'bonus_withdrawal'
                END,
                ABS(d.profit),
                COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'), ' - ', 3)), ''), 'USD'),
                CASE
                    WHEN d.action = 2 AND d.comment ILIKE '%transfer%' THEN
                        'Transfer ' ||
                        CASE WHEN d.comment ILIKE '%from%' THEN 'from'
                             WHEN d.comment ILIKE '%to %'  THEN 'to'
                             WHEN d.profit > 0 THEN 'in' ELSE 'out' END ||
                        COALESCE(' #' || substring(d.comment from '([0-9]{4,})'), '')
                    WHEN d.action = 2 THEN COALESCE(
                         NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'), ' - ', 2)), ''),
                         (regexp_match(d.comment,'(qi ?card|zain\w*|asiapay|asiahawala|usdt|tether|al ?taif|sham|perfect ?money|wallet|advcash|airtm|paymaxis|bridger|ptop|web ?money|cryptomus|payeer|fasapay)','i'))[1],
                         d.platform)
                    WHEN d.action = 6 THEN 'Bonus'
                    WHEN d.action = 3 THEN 'Credit'
                END,
                'approved',
                COALESCE(d.comment, '') || ' [' || COALESCE(d.platform,'') || ']',
                to_char(to_timestamp(d.deal_time), 'YYYY-MM-DD HH24:MI:SS'),
                NULLIF(d.deal_month, ''),
                to_timestamp(d.deal_time),
                NOW()
            FROM deals d
            WHERE d.action IN (2,3,6) AND d.profit <> 0
              -- exclude internal MT5 profit-settlement micro-ops ("PP on <pos>|<deal>") — these
              -- are NOT client deposits (avg ~$0.7) and flooded the deposit count with ~1M rows.
              AND COALESCE(d.comment,'') NOT ILIKE 'PP on%'
              AND NOT EXISTS (SELECT 1 FROM transactions t WHERE t.deal_id = d.deal_id)
            ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING
        """))
        inserted = res.rowcount
        db.commit()
        log.info(f"Transaction sync: {inserted} new transaction(s)")
        return inserted
    except Exception as e:
        db.rollback()
        log.error(f"Error: {e}")
        import traceback; traceback.print_exc()
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    sync()
