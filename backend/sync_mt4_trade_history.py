"""
sync_mt4_trade_history.py — Pull MT4 closed trade history from the journal
(LOG_TYPE_TRADES) and save into the deals table.

The MT4 server only exposes closed trades via the trade journal, not via
AdmTradesRequest. This parses journal 'close order' messages.

Message format:
  'LOGIN': close order #ORDER (DIRECTION VOLUME SYMBOL at OPENPRICE) at CLOSEPRICE completed

Run:  python sync_mt4_trade_history.py              (all history, 10 years)
      python sync_mt4_trade_history.py --days=30     (last 30 days)
"""
import sys, os, re, time
import db_config
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, string_at
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DAYS_BACK = 3650
for arg in sys.argv:
    if arg.startswith("--days="):
        DAYS_BACK = int(arg.split("=")[1])

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

V_JOURNAL_REQUEST = 96
V_MEM_FREE        = 3
LOG_TYPE_TRADES   = 2

SERVERLOG_SIZE = 796
OFFSET_TIME    = 4
OFFSET_MSG     = 284

# 'LOGIN': close order #ORDER (DIR VOL SYMBOL at OPEN) at CLOSE completed
RE_CLOSE = re.compile(
    r"'(\d+)':\s*close order #(\d+)\s*\((buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)\)\s+at\s+([\d.]+)"
)

def parse_time(base, i):
    """Parse the time[24] field of ServerLog record i."""
    off = base + i * SERVERLOG_SIZE + OFFSET_TIME
    t   = string_at(off, 24).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
    return t

def main():
    from bridge_mt4 import load_dll, connect, get_manager, vcall

    print("=" * 60)
    print(f"MT4 TRADE HISTORY SYNC  (last {DAYS_BACK} days)")
    print("=" * 60)

    load_dll()
    connect()
    man = get_manager()

    from_time = int(time.time()) - DAYS_BACK * 86400
    to_time   = int(time.time())
    print(f"Journal range: {datetime.fromtimestamp(from_time).date()} -> today")
    print("Requesting trade journal (this may take a minute for full history)...")

    total = c_int(0)
    ptr   = vcall(man, V_JOURNAL_REQUEST, c_void_p,
                  [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  LOG_TYPE_TRADES, from_time, to_time, b"", byref(total))

    if not ptr or total.value <= 0:
        print("No journal records returned.")
        return

    print(f"Journal records: {total.value:,}")
    print("Parsing close orders...")

    cmd_map = {"buy": 0, "sell": 1}
    trades  = []
    parsed  = 0

    for i in range(total.value):
        off = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
        msg = string_at(off, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
        m   = RE_CLOSE.search(msg)
        if not m:
            continue
        login      = int(m.group(1))
        order      = int(m.group(2))
        direction  = m.group(3)
        volume     = float(m.group(4))
        symbol     = m.group(5)
        open_price = float(m.group(6))
        close_price= float(m.group(7))
        time_str   = parse_time(ptr, i)
        # Parse time string like "2026.06.10 23:09:45"
        try:
            dt = datetime.strptime(time_str[:19], "%Y.%m.%d %H:%M:%S")
        except Exception:
            dt = None
        trades.append({
            "order":       order,
            "login":       login,
            "symbol":      symbol,
            "cmd":         cmd_map[direction],
            "direction":   direction,
            "volume":      volume,
            "open_price":  open_price,
            "close_price": close_price,
            "dt":          dt,
        })
        parsed += 1

    vcall(man, V_MEM_FREE, None, [c_void_p], ptr)
    print(f"Parsed close orders: {parsed:,}")

    if not trades:
        print("No closed trades parsed.")
        return

    # ── Save into deals table ─────────────────────────────────────────────────
    conn_db = psycopg2.connect(**DB)
    cur     = conn_db.cursor()

    cur.execute("ALTER TABLE deals ADD COLUMN IF NOT EXISTS platform VARCHAR(10) DEFAULT 'MT5'")
    conn_db.commit()

    # Map login -> client_id for MT4 accounts
    cur.execute("""
        SELECT login, client_id FROM trading_accounts WHERE platform='MT4'
    """)
    login_client = {r[0]: r[1] for r in cur.fetchall()}

    rows = []
    for t in trades:
        dt = t["dt"]
        deal_time  = int(dt.timestamp()) if dt else None
        deal_date  = dt.strftime("%Y-%m-%d") if dt else None
        deal_month = dt.strftime("%Y-%m")    if dt else None
        deal_year  = dt.year                 if dt else None
        client_id  = login_client.get(t["login"])
        rows.append((
            t["order"], t["login"], client_id, t["symbol"],
            t["cmd"], "trade", t["direction"],
            t["volume"], t["close_price"], 0.0, 0.0, 0.0,
            "", deal_time, deal_date, deal_month, deal_year,
            0.0, "MT4"
        ))

    print(f"Inserting {len(rows):,} deals...")
    execute_values(cur, """
        INSERT INTO deals (
            deal_id, login, client_id, symbol,
            action, deal_type, direction,
            volume, price, profit, commission, swap,
            comment, deal_time, deal_date, deal_month, deal_year,
            balance_after, platform
        ) VALUES %s
        ON CONFLICT (deal_id) DO NOTHING
    """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    page_size=2000)
    conn_db.commit()

    cur.execute("SELECT COUNT(*) FROM deals WHERE platform='MT4'")
    n = cur.fetchone()[0]
    print(f"\nDone.")
    print(f"  MT4 deals in DB now: {n:,}")
    conn_db.close()

if __name__ == "__main__":
    main()
