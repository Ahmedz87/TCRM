"""
fetch_mt4_balance.py — pull MT4 deposit/withdrawal/credit operations from the MT4 server
journal and load them into `transactions`.

WHY the journal: on this server AdmTradesRequest returns 0 trades to manager 1025, so the
journal (LOG_TYPE_TRADES) is the only working source — same approach the existing trade
sync uses. Balance ops appear as:
    'mgr': changed balance #<order> - <amount> for '<login>' - '<comment>'   (deposit/withdrawal)
    'mgr': changed credit  #<order> - <amount> for '<login>' - <comment>      (bonus/credit)
amount > 0 = in, < 0 = out. Comment carries the method ("Deposit - Qi card - USD").

MT4 deal_ids are offset by 4e9 so they never collide with MT5 deal_ids in the same table.
Idempotent (ON CONFLICT on deal_id). Run (only when mt4_loop is stopped — one MT4 conn):
    python fetch_mt4_balance.py [days]
"""
import sys, time, re
import db_config
from ctypes import c_int, c_void_p, byref, POINTER, c_char_p, string_at
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
import bridge_mt4 as b

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
MT4_DEAL_OFFSET = 4_000_000_000          # keep MT4 deal_ids out of MT5's range
SERVERLOG_SIZE, OFFSET_TIME, OFFSET_MSG = 796, 4, 284
RE_BAL = re.compile(r"changed (balance|credit) #(\d+) - (-?[\d.]+) for '(\d+)' - (.+)")
# internal account-to-account transfers carry a transfer comment (NOT a real deposit method).
# Match the specific transfer shapes only — never a real "Bank/Wire transfer" deposit method.
RE_XFER = re.compile(r"^\s*(reverting\s+transfer|transfer\s*-|transfer\s+from|transfer\s+to|(from|to)\s+#?\d+)", re.I)


def _is_transfer(comment: str, method: str) -> bool:
    return bool(RE_XFER.match(comment or "") or RE_XFER.match(method or ""))


# Internal MT balance adjustments (deposit-fix / negative-balance cover / cashback /
# stop-out comp …) are NOT real client deposits/withdrawals — mirrors
# transactions_router.INTERNAL_LABEL_RE so totals stay consistent everywhere.
RE_INTERNAL = re.compile(
    r"(deposit\s*[/ ]?\s*fix|withdraw\w*\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance"
    r"|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back"
    r"|credit\s*(in|out)|bonus\s*adjustment|\bsync\b)", re.I)


def _is_internal(comment: str, method: str) -> bool:
    return bool(RE_INTERNAL.search(comment or "") or RE_INTERNAL.search(method or ""))


def fetch_balance_ops(days=3650):
    b.connect()
    man = b.get_manager()
    frm, to = int(time.time()) - days * 86400, int(time.time())
    total = c_int(0)
    ptr = b.vcall(man, 96, c_void_p, [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  2, frm, to, b"", byref(total))
    print(f"journal records (last {days}d): {total.value}")
    if not ptr or total.value <= 0:
        return []
    ops = []
    for i in range(total.value):
        msg = string_at(ptr + i * SERVERLOG_SIZE + OFFSET_MSG, 512).split(b"\x00")[0].decode("utf-8", "ignore")
        m = RE_BAL.search(msg)
        if not m:
            continue
        tstr = string_at(ptr + i * SERVERLOG_SIZE + OFFSET_TIME, 24).split(b"\x00")[0].decode("utf-8", "ignore").strip()
        try:
            dt = datetime.strptime(tstr[:19], "%Y.%m.%d %H:%M:%S")
        except Exception:
            dt = None
        ops.append((m.group(1), int(m.group(2)), float(m.group(3)), int(m.group(4)), m.group(5).strip().strip("'"), dt))
    b.mem_free(ptr)
    return ops


def save(ops):
    rows = []
    for kind, order, amt, login, comment, dt in ops:
        if amt == 0:
            continue
        # normalize hyphens so a manual-entry comment 'Deposit-Qi card-USD' (gateway API down) still
        # yields the real method 'Qi card' instead of being misfiled as an internal fix
        _norm = re.sub(r"\s*-\s*", " - ", comment or "")
        parts = [x.strip() for x in _norm.split(" - ")]
        method   = parts[1] if len(parts) >= 2 else (comment[:40] if comment else "MT4")
        if kind == "balance":
            # account-to-account transfers + internal balance fixes are NOT deposits/withdrawals
            if _is_transfer(comment, method):
                txt = "internal_transfer"
            elif re.search(r"revert.*withdraw", comment, re.I):
                # rejected-withdrawal refund — NOT a deposit (see build_transactions notes)
                txt = "withdrawal_revert"
            elif _is_internal(comment, method):
                txt = "negative_cover" if re.search(r"negative\s*balance", comment, re.I) else "balance_fix"
            else:
                txt = "deposit" if amt > 0 else "withdrawal"
        else:
            txt = "bonus_deposit" if amt > 0 else "bonus_withdrawal"
        currency = parts[2] if len(parts) >= 3 else "USD"
        txdate = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None
        rows.append((order + MT4_DEAL_OFFSET, login, txt, abs(amt), currency, method,
                     "approved", comment + " [MT4]", txdate, dt.strftime("%Y-%m") if dt else None, txdate))

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS transactions_deal_id_uq ON transactions(deal_id) WHERE deal_id IS NOT NULL")
    conn.commit()
    cur.execute("SELECT count(*) FROM transactions"); before = cur.fetchone()[0]
    execute_values(cur, """
        INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method, status,
                                  notes, tx_date, tx_month, created_at, updated_at)
        VALUES %s
        ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING
    """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())")
    conn.commit()
    cur.execute("SELECT count(*) FROM transactions"); after = cur.fetchone()[0]
    print(f"MT4 balance ops parsed: {len(ops)}  rows offered: {len(rows)}  transactions {before} -> {after}")
    cur.execute("""SELECT tx_type, count(*), round(sum(amount)::numeric,2) FROM transactions
                   WHERE deal_id >= %s GROUP BY tx_type ORDER BY 2 DESC""", (MT4_DEAL_OFFSET,))
    print("MT4 transactions now:")
    for t, n, s in cur.fetchall():
        print(f"   {t:<18} {n:>6}   ${float(s or 0):,.2f}")
    conn.close()


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3650
    save(fetch_balance_ops(days))
