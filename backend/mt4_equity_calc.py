def update_equity_from_trades(open_trades: list):
    """Equity = Balance + Credit + sum(open trade floating PnL). Every 30s."""
    from sqlalchemy import text
    if not open_trades:
        return
    pnl_by_login = {}
    for t in open_trades:
        login = t["login"]
        floating = t.get("profit", 0) + t.get("swap", 0) + t.get("commission", 0)
        pnl_by_login[login] = pnl_by_login.get(login, 0) + floating
    db = get_db()
    try:
        count = 0
        for login, floating_pnl in pnl_by_login.items():
            row = db.execute(text(
                "SELECT balance, credit FROM trading_accounts WHERE login=:l AND platform='MT4'"
            ), {"l": login}).fetchone()
            if not row:
                continue
            balance = float(row[0] or 0)
            credit  = float(row[1] or 0)
            equity  = balance + credit + floating_pnl
            db.execute(text("""
                UPDATE trading_accounts SET equity=:eq, free_margin=:fm, updated_at=NOW()
                WHERE login=:l AND platform='MT4'
            """), {"eq": equity, "fm": floating_pnl, "l": login})
            db.execute(text("UPDATE clients SET equity=:eq WHERE login=:l"),
                       {"eq": equity, "l": login})
            count += 1
        db.commit()
        log.info("MT4 equity updated for %d accounts (from open trades)", count)
    except Exception as e:
        db.rollback()
        log.error("update_equity_from_trades: %s", e)
    finally:
        db.close()
