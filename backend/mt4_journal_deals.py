def sync_trade_journal(days: int = 3):
    """Fetch closed trades from MT4 journal (LOG_TYPE_TRADES) and save to deals.
    This is the WORKING method — AdmTradesRequest does not return closed trades
    on this server, but the journal does.
    """
    import re
    from ctypes import string_at
    man = get_manager()
    SERVERLOG_SIZE = 796
    OFFSET_TIME = 4
    OFFSET_MSG  = 284
    RE_CLOSE = re.compile(
        r"'(\d+)':\s*close order #(\d+)\s*\((buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)\)\s+at\s+([\d.]+)"
    )
    from_time = int(time.time()) - days * 86400
    to_time   = int(time.time())
    total = c_int(0)
    ptr = vcall(man, 96, c_void_p,
                [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                2, from_time, to_time, b"", byref(total))
    if not ptr or total.value <= 0:
        return []
    cmd_map = {"buy": 0, "sell": 1}
    trades = []
    for i in range(total.value):
        off = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
        msg = string_at(off, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
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
            "cmd":         cmd_map[m.group(3)],
            "direction":   m.group(3),
            "volume":      float(m.group(4)),
            "open_price":  float(m.group(6)),
            "close_price": float(m.group(7)),
            "dt":          dt,
        })
    mem_free(ptr)
    log.info("sync_trade_journal: %d records, %d closed trades in last %dd",
             total.value, len(trades), days)
    return trades


def save_journal_deals(trades: list):
    """Save journal-parsed closed trades into deals table."""
    from sqlalchemy import text
    if not trades:
        return
    db = get_db()
    import schema_guard
    schema_guard.ensure_column(db, "deals", "platform", "VARCHAR(10) DEFAULT 'MT5'")  # no-op once present, never locks
    try:
        count = 0
        for t in trades:
            dt = t["dt"]
            deal_time  = int(dt.timestamp()) if dt else None
            deal_date  = dt.strftime("%Y-%m-%d") if dt else None
            deal_month = dt.strftime("%Y-%m")    if dt else None
            deal_year  = dt.year                 if dt else None
            row = db.execute(text(
                "SELECT client_id FROM trading_accounts WHERE login=:l AND platform='MT4' LIMIT 1"
            ), {"l": t["login"]}).fetchone()
            client_id = row[0] if row else None
            db.execute(text("""
                INSERT INTO deals (
                    deal_id, login, client_id, symbol, action, deal_type, direction,
                    volume, price, profit, commission, swap, comment,
                    deal_time, deal_date, deal_month, deal_year, balance_after, platform, created_at
                ) VALUES (
                    :deal_id, :login, :client_id, :symbol, :action, 'trade', :direction,
                    :volume, :price, 0, 0, 0, '',
                    :deal_time, :deal_date, :deal_month, :deal_year, 0, 'MT4', NOW()
                )
                ON CONFLICT (deal_id) DO NOTHING
            """), {
                "deal_id":    t["order"],
                "login":      t["login"],
                "client_id":  client_id,
                "symbol":     t["symbol"],
                "action":     t["cmd"],
                "direction":  t["direction"],
                "volume":     t["volume"],
                "price":      t["close_price"],
                "deal_time":  deal_time,
                "deal_date":  deal_date,
                "deal_month": deal_month,
                "deal_year":  deal_year,
            })
            count += 1
            if count % 2000 == 0:
                db.commit()
        db.commit()
        log.info("MT4 journal deals saved: %d", count)
    except Exception as e:
        db.rollback()
        log.error("save_journal_deals: %s", e)
    finally:
        db.close()
