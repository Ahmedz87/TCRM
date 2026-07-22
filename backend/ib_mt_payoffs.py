"""
ib_mt_payoffs.py — deduct IB payouts made DIRECTLY on the MT agent accounts after the
last Plugit Operation-Log excel (desk: last report received 29 Jun 2026).

Rule (desk, Jul 15 2026): after the cutoff, any BALANCE-OUT operation (deals action=2,
profit<0) on an IB agent account is an IB payout:
  · comment mentions a transfer / target account  -> "Internal Wallet Transfer"
  · otherwise                                     -> "Wallet Withdrawal"
Each is mirrored ONCE into ib_operations as an APPROVED op (order_id 'MTD<deal_id>' is the
idempotency key), then ibs.total_payoff is recomputed for the affected IBs — the
enforce_ib_commission trigger then refreshes unpaid_commission automatically.

Run standalone (`python ib_mt_payoffs.py`) or via the ib_trades 30-min refresh (hooked
at the end of ib_trades.main()).
"""
import db_config

CUTOFF = "2026-06-29"   # last Plugit Operation Log received — ops after this come from MT


def capture(cn) -> int:
    cur = cn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ib_operations(id SERIAL PRIMARY KEY, ext_ib_id INTEGER,
        ib_id INTEGER, account VARCHAR, name VARCHAR, email VARCHAR, request_type VARCHAR, amount DOUBLE PRECISION,
        converted_amount DOUBLE PRECISION, payment_type VARCHAR, status VARCHAR, to_account VARCHAR,
        referral_id VARCHAR, comment TEXT, op_date TIMESTAMPTZ, action_date TIMESTAMPTZ, order_id VARCHAR, note TEXT)""")
    cur.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name='deals' AND column_name='comment' LIMIT 1""")
    ccol = "COALESCE(d.comment,'')" if cur.fetchone() else "''"

    cur.execute(f"""
        SELECT d.login, d.deal_id, ABS(d.profit), {ccol}, NULLIF(d.deal_date,''),
               i.id, i.ext_ib_id, COALESCE(i.name,''), COALESCE(i.email,'')
        FROM deals d
        JOIN ibs i ON i.agent_id = d.login
        WHERE d.action = 2 AND d.profit < 0
          AND NULLIF(d.deal_date,'') > %(cut)s
          AND NOT EXISTS (SELECT 1 FROM ib_operations o WHERE o.order_id = 'MTD' || d.deal_id::text)
    """, {"cut": CUTOFF})
    rows = cur.fetchall()

    ins, affected = 0, set()
    for login, deal_id, amt, cmt, ddate, ib_id, ext, name, email in rows:
        low = (cmt or "").lower()
        rtype = ("Internal Wallet Transfer"
                 if ("transfer" in low or "to #" in low or "->" in low or "t/o" in low)
                 else "Wallet Withdrawal")
        cur.execute("""INSERT INTO ib_operations(ext_ib_id, ib_id, account, name, email, request_type,
            amount, converted_amount, payment_type, status, to_account, comment, op_date, action_date, order_id, note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'MT balance op','Approved','',%s,
                    COALESCE(%s::timestamptz, NOW()), NOW(), %s, 'auto-captured from MT (post-Plugit cutoff)')""",
            (ext, ib_id, str(login), name, email, rtype, float(amt or 0), float(amt or 0),
             cmt or "", ddate, f"MTD{deal_id}"))
        ins += 1
        affected.add((ib_id, ext))

    for ib_id, ext in affected:
        cur.execute("""UPDATE ibs SET total_payoff = (
            SELECT COALESCE(SUM(o.amount),0) FROM ib_operations o
            WHERE o.status = 'Approved'
              AND (o.ib_id = %(id)s OR (%(ext)s::bigint IS NOT NULL AND o.ext_ib_id = %(ext)s))
        ) WHERE id = %(id)s""", {"id": ib_id, "ext": ext})
    cn.commit()
    return ins


def main():
    cn = db_config.connect()
    try:
        n = capture(cn)
        print(f"[ib_mt_payoffs] captured {n} MT payout op(s) after {CUTOFF}")
    finally:
        cn.close()


if __name__ == "__main__":
    main()
