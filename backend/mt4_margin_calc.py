def _contract_size(symbol):
    s = symbol.upper().split(".")[0].strip()
    if s.startswith("XAU"): return 100.0
    if s.startswith("XAG"): return 5000.0
    if s.startswith("XPT") or s.startswith("XPD"): return 100.0
    if s in ("USOIL","UKOIL","WTI","BRENT","XBRUSD","XTIUSD"): return 1000.0
    crypto = ("BTC","ETH","XRP","LTC","BCH","XMR","XTZ","DSH","BSV","ADA","DOT","EOS","XLM")
    if any(s.startswith(c) for c in crypto): return 1.0
    fx = ("USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","SEK","NOK","DKK","TRY","ZAR","MXN","SGD","HKD","PLN","CNH","CZK","HUF")
    if len(s)==6 and s[:3] in fx and s[3:] in fx: return 100000.0
    indices = ("US30","NAS100","SPX500","US500","JP225","GER40","GER30","UK100","SPAIN35","FRA40","AUS200","HK50","EU50","NAS","DAX")
    if any(s.startswith(idx) for idx in indices): return 1.0
    return 1.0


def update_margin_levels(open_trades):
    from sqlalchemy import text
    if not open_trades:
        return
    agg = {}
    for t in open_trades:
        login = t["login"]
        a = agg.setdefault(login, {"pnl": 0.0, "margin_base": 0.0})
        a["pnl"] += t.get("profit",0) + t.get("swap",0) + t.get("commission",0)
        cs = _contract_size(t["symbol"])
        a["margin_base"] += t["volume"] * cs * t["open_price"]
    db = get_db()
    try:
        count=0; margin_calls=0
        for login, a in agg.items():
            row = db.execute(text(
                "SELECT balance, credit, leverage FROM trading_accounts WHERE login=:l AND platform='MT4'"
            ), {"l": login}).fetchone()
            if not row:
                continue
            balance=float(row[0] or 0); credit=float(row[1] or 0)
            leverage=float(row[2] or 100) or 100
            equity = balance + credit + a["pnl"]
            used_margin = a["margin_base"] / leverage
            margin_level = (equity/used_margin*100.0) if used_margin>0 else 0.0
            is_mc = used_margin>0 and margin_level<100.0
            db.execute(text("""
                UPDATE trading_accounts SET equity=:eq, margin_level=:ml, free_margin=:fm, updated_at=NOW()
                WHERE login=:l AND platform='MT4'
            """), {"eq":equity,"ml":margin_level,"fm":equity-used_margin,"l":login})
            db.execute(text("UPDATE clients SET equity=:eq, margin_level=:ml WHERE login=:l"),
                       {"eq":equity,"ml":margin_level,"l":login})
            count+=1
            if is_mc: margin_calls+=1
        db.commit()
        log.info("MT4 margin: %d accounts updated, %d in margin call", count, margin_calls)
    except Exception as e:
        db.rollback()
        log.error("update_margin_levels: %s", e)
    finally:
        db.close()
