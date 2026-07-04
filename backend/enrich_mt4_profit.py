"""
enrich_mt4_profit.py — Re-parse MT4 trade journal to capture open_price and
compute profit for all MT4 deals.

The original backfill stored only close price in `deals.price` and discarded
the open price, leaving profit=0. This:
  1. Adds an open_price column to deals
  2. Re-walks the journal in safe windows, extracting BOTH open and close price
  3. Updates each deal's open_price
  4. Computes profit = (close - open) * volume * contract_size * direction_sign

Profit is in the symbol's quote currency. For USD-quoted symbols (XAUUSD,
EURUSD, BTCUSD) this is USD. For cross pairs it's approximate (quote-ccy),
which is fine for relative hedge-impact scoring.

Run:  python enrich_mt4_profit.py              (10 years, 2-day windows)
      python enrich_mt4_profit.py --days=400
"""
import sys, os, re, time
import db_config
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, string_at
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAX_DAYS_BACK = 3650
WINDOW_DAYS   = 2
for arg in sys.argv:
    if arg.startswith("--days="):
        MAX_DAYS_BACK = int(arg.split("=")[1])
    if arg.startswith("--window="):
        WINDOW_DAYS = int(arg.split("=")[1])

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

V_JOURNAL_REQUEST = 96
V_MEM_FREE        = 3
LOG_TYPE_TRADES   = 2
SERVERLOG_SIZE = 796
OFFSET_MSG     = 284

RE_CLOSE = re.compile(
    r"'(\d+)':\s*close order #(\d+)\s*\((buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)\)\s+at\s+([\d.]+)"
)


def contract_size(symbol):
    s = symbol.upper().split(".")[0].strip()
    if s.startswith("XAU"): return 100.0
    if s.startswith("XAG"): return 5000.0
    if s.startswith("XPT") or s.startswith("XPD"): return 100.0
    if s in ("USOIL","UKOIL","WTI","BRENT","XBRUSD","XTIUSD"): return 1000.0
    crypto = ("BTC","ETH","XRP","LTC","BCH","XMR","XTZ","DSH","BSV","ADA","DOT","EOS","XLM","UNI")
    if any(s.startswith(c) for c in crypto): return 1.0
    fx = ("USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","SEK","NOK","DKK",
          "TRY","ZAR","MXN","SGD","HKD","PLN","CNH","CZK","HUF")
    if len(s) == 6 and s[:3] in fx and s[3:] in fx: return 100000.0
    return 1.0  # indices, stocks


def main():
    from bridge_mt4 import load_dll, connect, get_manager, vcall

    print("=" * 60)
    print("MT4 PROFIT ENRICHMENT")
    print("=" * 60)

    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    cur.execute("ALTER TABLE deals ADD COLUMN IF NOT EXISTS open_price DOUBLE PRECISION")
    conn.commit()

    load_dll(); connect()
    man = get_manager()

    now          = int(time.time())
    oldest_limit = now - MAX_DAYS_BACK * 86400
    window_sec   = WINDOW_DAYS * 86400

    to_t         = now
    empty_streak = 0
    chunk_no     = 0
    total_updated = 0

    while to_t > oldest_limit:
        from_t = max(to_t - window_sec, oldest_limit)
        chunk_no += 1
        total = c_int(0)
        ptr = vcall(man, V_JOURNAL_REQUEST, c_void_p,
                    [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                    LOG_TYPE_TRADES, from_t, to_t, b"", byref(total))
        d_from = datetime.fromtimestamp(from_t).strftime("%Y-%m-%d")
        d_to   = datetime.fromtimestamp(to_t).strftime("%Y-%m-%d")

        if not ptr or total.value <= 0:
            empty_streak += 1
            print(f"  [{chunk_no:4d}] {d_from}..{d_to}: empty ({empty_streak})")
            if empty_streak >= 10:
                print("  Reached end of server history.")
                break
            to_t = from_t
            continue

        empty_streak = 0
        updates = []  # (open_price, profit, deal_id)
        for i in range(total.value):
            moff = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
            msg = string_at(moff, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
            m = RE_CLOSE.search(msg)
            if not m:
                continue
            order      = int(m.group(2))
            direction  = m.group(3)
            volume     = float(m.group(4))
            symbol     = m.group(5)
            open_price = float(m.group(6))
            close_price= float(m.group(7))
            cs   = contract_size(symbol)
            sign = 1.0 if direction == "buy" else -1.0
            profit = (close_price - open_price) * sign * volume * cs
            updates.append((open_price, round(profit, 2), order))

        vcall(man, V_MEM_FREE, None, [c_void_p], ptr)

        if updates:
            execute_values(cur, """
                UPDATE deals AS d SET
                    open_price = v.open_price,
                    profit     = v.profit
                FROM (VALUES %s) AS v(open_price, profit, deal_id)
                WHERE d.deal_id = v.deal_id AND d.platform='MT4'
            """, updates, template="(%s,%s,%s)", page_size=2000)
            conn.commit()
            total_updated += len(updates)
            print(f"  [{chunk_no:4d}] {d_from}..{d_to}: {len(updates):>6,} updated  (cum {total_updated:,})")

        to_t = from_t

    cur.execute("SELECT COUNT(*) FROM deals WHERE platform='MT4' AND profit != 0")
    n = cur.fetchone()[0]
    conn.close()
    print("\n" + "=" * 60)
    print(f"DONE.  Updated this run: {total_updated:,}")
    print(f"       MT4 deals with profit now: {n:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
