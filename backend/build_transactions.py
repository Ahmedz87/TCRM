"""
build_transactions.py — backfill the `transactions` table from MT4/MT5 `deals`.

The transactions table starts empty; all real money movement lives in `deals` as
balance operations:
    action=2  balance  -> deposit (profit>0) / withdrawal (profit<0)
    action=6  bonus    -> bonus_deposit / bonus_withdrawal
    action=3  credit   -> bonus_deposit / bonus_withdrawal  (no separate credit tab in UI)

We map each balance/credit/bonus deal to one transactions row, parsing the method +
currency out of the deal comment (e.g. "Deposit - Qi card - USD"). amount is stored
POSITIVE; tx_type carries the direction (matches the Transactions page convention).

Idempotent: a unique index on deal_id + ON CONFLICT DO NOTHING means re-running only
adds NEW deals. Safe to schedule.  Run:  python build_transactions.py
"""
import psycopg2
import db_config

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

SQL = """
INSERT INTO transactions
    (deal_id, login, client_id, tx_type, amount, currency, method, status,
     notes, tx_date, tx_month, created_at, updated_at)
SELECT
    d.deal_id,
    d.login,
    d.client_id,
    CASE
        WHEN d.action = 2 AND d.comment ILIKE '%transfer%' THEN 'internal_transfer'
        -- "Reverting withdraw ..." = a REJECTED withdrawal being refunded to the account. It is NOT
        -- a deposit. Classify it as withdrawal_revert (excluded from deposit totals); the matching
        -- original withdrawal is flagged 'rejected' by reject_reverted_withdrawals() below.
        WHEN d.action = 2 AND d.comment ~* 'revert.*withdraw' THEN 'withdrawal_revert'
        -- Abuse clawbacks (hedge/dividend/bonus abuse) = broker recovering abuse profit. NOT a real
        -- client withdrawal — kept as its own type so the abuse desk can trace it.
        WHEN d.action = 2 AND d.comment ~* 'abus' THEN 'abuse_clawback'
        -- Internal MT balance adjustments (deposit-fix / negative-balance cover / cashback /
        -- stop-out comp …) are NOT real client deposits or withdrawals. Detect by the resolved
        -- payment method: the literal 'MT5' fallback (no payment segment in the comment) or an
        -- internal-label method. Mirrors transactions_router.INTERNAL_LABEL_RE so client totals,
        -- sales and dashboards match the Deposits list / Finance. -> mt_adjustment, not a deposit.
        -- NOTE: normalize hyphens to ' - ' first so a manually-typed comment like 'Deposit-Qi card-USD'
        -- (entered when the gateway API was down) still yields the real method 'Qi card' and counts as a
        -- deposit, instead of falling back to 'MT5' and being misfiled as an internal fix.
        -- ...UNLESS the comment names a real payment method (e.g. 'deposit Qi Card USD (FIX)') — that's a
        -- real deposit that staff manually FIXED, not an internal balance fix. The named method wins.
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
    END                                                          AS tx_type,
    ABS(d.profit)                                                AS amount,
    COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'), ' - ', 3)), ''), 'USD') AS currency,
    CASE
        -- internal transfer: show direction + the counterparty account from the comment
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
    END                                                          AS method,
    'approved'                                                   AS status,
    COALESCE(d.comment, '') || ' [' || COALESCE(d.platform,'') || ']' AS notes,
    -- REAL credit date+time from MT (deal_time epoch), not just the date
    to_char(to_timestamp(d.deal_time), 'YYYY-MM-DD HH24:MI:SS')  AS tx_date,
    NULLIF(d.deal_month, '')                                     AS tx_month,
    to_timestamp(d.deal_time)                                    AS created_at,
    NOW()                                                        AS updated_at
FROM deals d
WHERE d.action IN (2,3,6) AND d.profit <> 0
  AND COALESCE(d.comment,'') NOT ILIKE 'PP on%'   -- skip internal MT5 profit-settlement micro-ops
ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL
DO UPDATE SET tx_type = EXCLUDED.tx_type, method = EXCLUDED.method,
              tx_date = EXCLUDED.tx_date, created_at = EXCLUDED.created_at
"""


def reject_reverted_withdrawals(cur):
    """A 'withdrawal_revert' means the client's withdrawal was REJECTED and the money refunded.
    Flag the matching original withdrawal (same login+amount, most recent one before the revert) as
    'rejected' so it stops counting as a real withdrawal. Idempotent; scans recent reverts each run.
    NOTE: matching is by login+amount+time because the revert comment has no original deal id — if
    that's added later this can key on it directly to avoid any mis-match.
    Fixed Jul 2026: the old DISTINCT ON (rv.id) let many reverts collapse onto the SAME original
    when a client repeats the same amount (twenty $1,500 withdrawals each reverted -> only 1 got
    rejected; July was inflated ~$126k). Delegates to revert_reject_engine (greedy-all 1:1,
    idempotent — see its docstring for why this pairing)."""
    cur.connection.commit()
    import revert_reject_engine
    return revert_reject_engine.run(conn=cur.connection)


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    # dedupe key so re-runs are incremental
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS transactions_deal_id_uq
                   ON transactions(deal_id) WHERE deal_id IS NOT NULL""")
    conn.commit()

    cur.execute("SELECT count(*) FROM transactions"); before = cur.fetchone()[0]
    cur.execute(SQL)
    inserted = cur.rowcount
    conn.commit()
    rej = reject_reverted_withdrawals(cur); conn.commit()
    if rej: print(f"flagged {rej} reverted withdrawal(s) as rejected")

    cur.execute("SELECT count(*) FROM transactions"); after = cur.fetchone()[0]
    print(f"Inserted {inserted} new transaction(s).  total {before} -> {after}")
    cur.execute("""SELECT tx_type, count(*), round(sum(amount)::numeric,2)
                   FROM transactions GROUP BY tx_type ORDER BY count(*) DESC""")
    print("\nBy type (count, total amount):")
    for t, n, s in cur.fetchall():
        print(f"   {t:<18} {n:>7}   ${s:,.2f}")
    cur.execute("SELECT min(tx_date), max(tx_date) FROM transactions WHERE tx_date IS NOT NULL")
    print("\ndate range:", cur.fetchone())
    conn.close()


if __name__ == "__main__":
    main()
