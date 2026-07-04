"""
step_b_mt4_trades.py — Step B for MT4: backfill closed TRADES from the MT4 server journal
(LOG_TYPE_TRADES, vtable 96, "close order" entries) into the deals table, 2023-01 -> now.

Runs on the idle MT4-D login (3028) so it never touches the live mt4_loop (1025) / journal worker
(1026). 2-day chunks (journal has a ~288k-record per-request cap). deal_id = order + 4e9 (MT4 offset,
avoids collision with MT5 deal ids); platform='MT4'; ON CONFLICT DO NOTHING (idempotent, resumable).

NOTE: the MT4 journal only retains back to ~2023 (proven) — MT4 2019-2022 trades are NOT on the
server and TradeSoft carries no trades, so they are unrecoverable. This gets everything that exists.

Run: python step_b_mt4_trades.py [--from 2023-01-01]   (launch in background; runs for a while)
"""
import sys, time, re
import db_config
from ctypes import c_int, c_void_p, byref, POINTER, c_char_p, string_at
from datetime import datetime, timezone, timedelta
import psycopg2
import bridge_mt4 as b
import mt_managers as M

b.MT4_LOGIN, b.MT4_PASSWORD = M.MT4["D"]      # 3028, idle
SERVERLOG_SIZE, OFFSET_TIME, OFFSET_MSG = 796, 4, 284
RE_CLOSE = re.compile(
    r"'(\d+)':\s*close order #(\d+)\s*\((buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)\)\s+at\s+([\d.]+)")
CMD = {"buy": 0, "sell": 1}
OFFSET = 4_000_000_000
STEP = timedelta(days=2)
PG = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)


def fetch(man, frm, to):
    total = c_int(0)
    ptr = b.vcall(man, 96, c_void_p, [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  2, frm, to, b"", byref(total))
    if not ptr or total.value <= 0:
        return []
    out = []
    for i in range(total.value):
        msg = string_at(ptr + i*SERVERLOG_SIZE + OFFSET_MSG, 512).split(b"\x00")[0].decode("utf-8", "ignore")
        m = RE_CLOSE.search(msg)
        if not m:
            continue
        t = string_at(ptr + i*SERVERLOG_SIZE + OFFSET_TIME, 24).split(b"\x00")[0].decode("utf-8", "ignore").strip()
        try:
            dt = datetime.strptime(t[:19], "%Y.%m.%d %H:%M:%S")
        except Exception:
            dt = None
        out.append((int(m.group(2)), int(m.group(1)), m.group(5), CMD[m.group(3)],
                    m.group(3), float(m.group(4)), float(m.group(7)), dt))
    b.mem_free(ptr)
    return out


def save(conn, trades):
    if not trades:
        return 0
    cur = conn.cursor(); n = 0
    for order, login, sym, cmd, direction, vol, price, dt in trades:
        dtime = int(dt.timestamp()) if dt else None
        cur.execute("""INSERT INTO deals (deal_id, login, symbol, action, deal_type, direction,
              volume, price, profit, commission, swap, comment, deal_time, deal_date, deal_month,
              deal_year, balance_after, platform, created_at)
            VALUES (%s,%s,%s,%s,'trade',%s,%s,%s,0,0,0,'',%s,%s,%s,%s,0,'MT4',NOW())
            ON CONFLICT (deal_id) DO NOTHING""",
            (OFFSET + order, login, sym, cmd, direction, vol, price, dtime,
             dt.strftime("%Y-%m-%d") if dt else None, dt.strftime("%Y-%m") if dt else None,
             dt.year if dt else None))
        n += cur.rowcount
    conn.commit()
    return n


def run(start):
    b.connect(); man = b.get_manager()
    conn = psycopg2.connect(**PG)
    end = datetime.now(timezone.utc); cur = start; tot = 0
    print(f"MT4 Step B trades backfill {start:%Y-%m-%d} -> now (2-day chunks) on MT4-D 3028", flush=True)
    while cur < end:
        nxt = min(cur + STEP, end)
        for attempt in range(3):
            try:
                tr = fetch(man, int(cur.timestamp()), int(nxt.timestamp()))
                got = save(conn, tr); tot += got
                if tr:
                    print(f"{cur:%Y-%m-%d}: trades={len(tr)} saved={got} run={tot:,}", flush=True)
                break
            except Exception as e:
                print(f"{cur:%Y-%m-%d}: ERR {str(e)[:80]} (retry {attempt})", flush=True)
                time.sleep(5)
                try:
                    b._manager = None; b.connect(); man = b.get_manager()
                except Exception:
                    pass
        cur = nxt
    print(f"MT4 STEP B DONE: {tot:,} trades saved", flush=True)


if __name__ == "__main__":
    s = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2023-01-01"
    run(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc))
