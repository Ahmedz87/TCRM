def get_open_trades():
    """Fetch all currently open MT4 trades."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ADM_TRADES_REQUEST, c_void_p,
                  [c_char_p, c_int, POINTER(c_int)], b"*", 1, byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(TradeRecord)
    result = []
    for i in range(total.value):
        rec    = TradeRecord.from_address(ptr + i * stride)
        if rec.cmd not in (0, 1, 2, 3, 4, 5):
            continue
        symbol  = rec.symbol.decode("utf-8", errors="ignore").strip()
        comment = rec.comment.decode("utf-8", errors="ignore").strip()
        result.append({
            "order":      rec.order,
            "login":      rec.login,
            "symbol":     symbol,
            "cmd":        rec.cmd,
            "volume":     rec.volume / 100.0,
            "open_price": rec.open_price,
            "open_time":  rec.open_time,
            "profit":     rec.profit,
            "swap":       rec.storage,
            "commission": rec.commission,
            "comment":    comment,
        })
    mem_free(ptr)
    log.info("AdmTradesRequest open: %d trades", len(result))
    return result


def save_open_trades(trades: list):
    """Upsert currently open MT4 trades into a tracking table."""
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mt4_open_trades (
                order_id    INTEGER PRIMARY KEY,
                login       INTEGER,
                symbol      VARCHAR(32),
                cmd         INTEGER,
                direction   VARCHAR(8),
                volume      DOUBLE PRECISION,
                open_price  DOUBLE PRECISION,
                open_time   INTEGER,
                profit      DOUBLE PRECISION,
                swap        DOUBLE PRECISION,
                commission  DOUBLE PRECISION,
                comment     VARCHAR(64),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.commit()

        # Clear old open trades and replace with current snapshot
        db.execute(text("DELETE FROM mt4_open_trades"))
        count = 0
        for t in trades:
            direction = "buy" if t["cmd"] in (0, 2, 4) else "sell"
            db.execute(text("""
                INSERT INTO mt4_open_trades
                    (order_id, login, symbol, cmd, direction, volume,
                     open_price, open_time, profit, swap, commission, comment, updated_at)
                VALUES
                    (:order_id, :login, :symbol, :cmd, :direction, :volume,
                     :open_price, :open_time, :profit, :swap, :commission, :comment, NOW())
                ON CONFLICT (order_id) DO UPDATE SET
                    profit=EXCLUDED.profit, swap=EXCLUDED.swap,
                    updated_at=NOW()
            """), {
                "order_id":   t["order"],
                "login":      t["login"],
                "symbol":     t["symbol"],
                "cmd":        t["cmd"],
                "direction":  direction,
                "volume":     t["volume"],
                "open_price": t["open_price"],
                "open_time":  t["open_time"],
                "profit":     t["profit"],
                "swap":       t["swap"],
                "commission": t["commission"],
                "comment":    t["comment"],
            })
            count += 1
        db.commit()
        log.info("MT4 open trades saved: %d", count)
    except Exception as e:
        db.rollback()
        log.error("save_open_trades: %s", e)
    finally:
        db.close()
