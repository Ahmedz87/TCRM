"""
sync_mt4_trade_history_chunked.py — Pull ALL MT4 closed trade history from the
journal by walking backwards in small time windows to avoid the server's
per-request record cap (~250-300k records).

The MT4 server caps a single JournalRequest and returns only the most recent
records. At ~45k trade-journal records/day, we use a 2-day window per request
to stay safely under the cap, and walk backwards until we stop finding data.

Run:  python sync_mt4_trade_history_chunked.py                 (walk back 10 years)
      python sync_mt4_trade_history_chunked.py --days=730       (walk back 2 years)
      python sync_mt4_trade_history_chunked.py --window=1       (1-day chunks)
"""
import sys, os, re, time
import db_config
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, string_at
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAX_DAYS_BACK = 3650
WINDOW_DAYS   = 2          # chunk size; keep well under the cap
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
OFFSET_TIME    = 4
OFFSET_MSG     = 284

RE_CLOSE = re.compile(
    r"'(\d+)':\s*close order #(\d+)\s*\((buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)\)\s+at\s+([\d.]+)"
)
CMD_MAP = {"buy": 0, "sell": 1}


def fetch_window(man, vcall, from_t, to_t):
    """Fetch and parse one journal window. Returns list of trade dicts."""
    total = c_int(0)
    ptr = vcall(man, V_JOURNAL_REQUEST, c_void_p,
                [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                LOG_TYPE_TRADES, from_t, to_t, b"", byref(total))
    if not ptr or total.value <= 0:
        return [], 0
    n = total.value
    trades = []
    for i in range(n):
        moff = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
        msg = string_at(moff, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
        m = RE_CLOSE.search(msg)
        if not m:
            continue
        toff = ptr + i * SERVERLOG_SIZE + OFFSET_TIME
        tstr = string_at(toff, 24).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
        try:
            dt = datetime.strptime(tstr[:19], "%Y.%m.%d %H:%M:%S")
        except Exception:
            dt = None
        trades.append({
            "order":       int(m.group(2)),
            "login":       int(m.group(1)),
            "symbol":      m.group(5),
            "cmd":         CMD_MAP[m.group(3)],
            "direction":   m.group(3),
            "volume":      float(m.group(4)),
            "open_price":  float(m.group(6)),
            "close_price": float(m.group(7)),
            "dt":          dt,
        })
    vcall(man, V_MEM_FREE, None, [c_void_p], ptr)
    return trades, n


def save_batch(cur, trades, login_client):
    rows = []
    for t in trades:
        dt = t["dt"]
        deal_time  = int(dt.timestamp()) if dt else None
        deal_date  = dt.strftime("%Y-%m-%d") if dt else None
        deal_month = dt.strftime("%Y-%m")    if dt else None
        deal_year  = dt.year                 if dt else None
        rows.append((
            t["order"], t["login"], login_client.get(t["login"]), t["symbol"],
            t["cmd"], "trade", t["direction"],
            t["volume"], t["close_price"], 0.0, 0.0, 0.0,
            "", deal_time, deal_date, deal_month, deal_year,
            0.0, "MT4"
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO deals (
            deal_id, login, client_id, symbol,
            action, deal_type, direction,
            volume, price, profit, commission, swap,
            comment, deal_time, deal_date, deal_month, deal_year,
            balance_after, platform
        ) VALUES %s
        ON CONFLICT (deal_id) DO NOTHING
    """, rows,
    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    page_size=2000)
    return len(rows)


def main():
    from bridge_mt4 import load_dll, connect, get_manager, vcall

    print("=" * 60)
    print(f"MT4 CHUNKED TRADE HISTORY SYNC")
    print(f"  Walk back: {MAX_DAYS_BACK} days   Window: {WINDOW_DAYS} day(s)")
    print("=" * 60)

    load_dll()
    connect()
    man = get_manager()

    conn_db = psycopg2.connect(**DB)
    cur     = conn_db.cursor()
    cur.execute("ALTER TABLE deals ADD COLUMN IF NOT EXISTS platform VARCHAR(10) DEFAULT 'MT5'")
    conn_db.commit()
    cur.execute("SELECT login, client_id FROM trading_accounts WHERE platform='MT4'")
    login_client = {r[0]: r[1] for r in cur.fetchall()}

    now          = int(time.time())
    oldest_limit = now - MAX_DAYS_BACK * 86400
    window_sec   = WINDOW_DAYS * 86400

    to_t          = now
    total_parsed  = 0
    total_saved   = 0
    empty_streak  = 0
    chunk_no      = 0

    while to_t > oldest_limit:
        from_t = max(to_t - window_sec, oldest_limit)
        chunk_no += 1
        trades, raw = fetch_window(man, vcall, from_t, to_t)
        d_from = datetime.fromtimestamp(from_t).strftime("%Y-%m-%d")
        d_to   = datetime.fromtimestamp(to_t).strftime("%Y-%m-%d")

        if raw == 0:
            empty_streak += 1
            print(f"  [{chunk_no:4d}] {d_from}..{d_to}: 0 raw  (empty streak {empty_streak})")
            # If we hit many empty windows in a row, we've passed the server's
            # retention horizon — stop.
            if empty_streak >= 10:
                print("  10 consecutive empty windows — reached end of server history.")
                break
        else:
            empty_streak = 0
            saved = save_batch(cur, trades, login_client)
            conn_db.commit()
            total_parsed += len(trades)
            total_saved  += saved
            print(f"  [{chunk_no:4d}] {d_from}..{d_to}: {raw:>7,} raw, {len(trades):>6,} trades  (cum {total_parsed:,})")

        to_t = from_t
        if from_t <= oldest_limit:
            break

    cur.execute("SELECT COUNT(*) FROM deals WHERE platform='MT4'")
    n = cur.fetchone()[0]
    conn_db.close()

    print("\n" + "=" * 60)
    print(f"DONE.  Parsed this run: {total_parsed:,}")
    print(f"       MT4 deals in DB: {n:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
