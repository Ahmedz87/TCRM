def get_trade_history(days: int = 3):
    """Fetch actual MT4 trade history (buy/sell deals) via AdmTradesRequest."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ADM_TRADES_REQUEST, c_void_p,
                  [c_char_p, c_int, POINTER(c_int)], b"*", 0, byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(TradeRecord)
    cutoff = int(time.time()) - days * 86400
    result = []
    for i in range(total.value):
        rec = TradeRecord.from_address(ptr + i * stride)
        if rec.cmd not in (0, 1, 2, 3, 4, 5):
            continue
        if rec.close_time <= 0 or rec.close_time < cutoff:
            continue
        symbol  = rec.symbol.decode("utf-8", errors="ignore").strip()
        comment = rec.comment.decode("utf-8", errors="ignore").strip()
        result.append({
            "order":       rec.order,
            "login":       rec.login,
            "symbol":      symbol,
            "cmd":         rec.cmd,
            "volume":      rec.volume / 100.0,
            "open_price":  rec.open_price,
            "close_price": rec.close_price,
            "open_time":   rec.open_time,
            "close_time":  rec.close_time,
            "profit":      rec.profit,
            "commission":  rec.commission,
            "swap":        rec.storage,
            "comment":     comment,
        })
    mem_free(ptr)
    log.info("get_trade_history: %d total, %d trades in last %dd",
             total.value, len(result), days)
    return result


def save_mt4_deals(trades: list):
    """Save MT4 actual trades into the deals table."""
    from sqlalchemy import text
    db = get_db()
    import schema_guard
    schema_guard.ensure_column(db, "deals", "platform", "VARCHAR(10) DEFAULT 'MT5'")  # no-op once present, never locks
    try:
        count = 0
        for t in trades:
            close_dt   = datetime.fromtimestamp(t["close_time"]) if t["close_time"] else None
            deal_date  = close_dt.strftime("%Y-%m-%d") if close_dt else None
            deal_month = close_dt.strftime("%Y-%m")    if close_dt else None
            deal_year  = close_dt.year                 if close_dt else None
            direction  = "buy" if t["cmd"] in (0, 2, 4) else "sell"
            row = db.execute(text(
                "SELECT client_id FROM trading_accounts WHERE login=:l AND platform='MT4' LIMIT 1"
            ), {"l": t["login"]}).fetchone()
            client_id = row[0] if row else None
            db.execute(text("""
                INSERT INTO deals (
                    deal_id, login, client_id, symbol,
                    action, deal_type, direction,
                    volume, price, profit, commission, swap,
                    comment, deal_time, deal_date, deal_month, deal_year,
                    balance_after, platform, created_at
                ) VALUES (
                    :deal_id, :login, :client_id, :symbol,
                    :action, 'trade', :direction,
                    :volume, :price, :profit, :commission, :swap,
                    :comment, :deal_time, :deal_date, :deal_month, :deal_year,
                    0, 'MT4', NOW()
                )
                ON CONFLICT (deal_id) DO NOTHING
            """), {
                "deal_id":    t["order"],
                "login":      t["login"],
                "client_id":  client_id,
                "symbol":     t["symbol"],
                "action":     t["cmd"],
                "direction":  direction,
                "volume":     t["volume"],
                "price":      t["close_price"],
                "profit":     t["profit"],
                "commission": t["commission"],
                "swap":       t["swap"],
                "comment":    t["comment"],
                "deal_time":  t["close_time"],
                "deal_date":  deal_date,
                "deal_month": deal_month,
                "deal_year":  deal_year,
            })
            count += 1
            if count % 2000 == 0:
                db.commit()
                log.info("MT4 deals: %d saved...", count)
        db.commit()
        log.info("MT4: %d deals saved", count)
    except Exception as e:
        db.rollback()
        log.error("save_mt4_deals: %s", e)
    finally:
        db.close()
