"""
MT5 Bridge — fetches from MT5 and stores in PostgreSQL
Run: python bridge.py
Mock: python bridge.py --mock
"""
import argparse, threading, time, random, re, logging, sys, os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from flask import Flask, jsonify, request
from sqlalchemy import text
from flask_cors import CORS

# Add backend path so we can import database
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

app  = Flask(__name__)
CORS(app)

MT5_SERVER   = "192.109.15.62:443"
MT5_LOGIN    = 1025
MT5_PASSWORD = "ZjFb!vA0"

_manager = None

# ── DATABASE ───────────────────────────────────────────────────────────────
def get_db():
    from database import SessionLocal
    return SessionLocal()

def save_identifiers(traders: list):
    """
    Save every CID, IP, MQID for every trading account.
    This builds the full fraud detection network.
    """
    import models
    db = get_db()
    try:
        count = 0
        for t in traders:
            login = t.get("login")
            if not login:
                continue

            identifiers = []
            if t.get("lastIP"):
                identifiers.append(("ip",   t["lastIP"]))
            if t.get("clientID"):
                identifiers.append(("cid",  t["clientID"]))
            if t.get("mqid") and t.get("mqid") != 0:
                identifiers.append(("mqid", str(t["mqid"])))

            for id_type, id_value in identifiers:
                if not id_value:
                    continue
                existing = db.query(models.AccountIdentifier).filter(
                    models.AccountIdentifier.login            == login,
                    models.AccountIdentifier.identifier_type  == id_type,
                    models.AccountIdentifier.identifier_value == str(id_value),
                ).first()
                if existing:
                    existing.seen_count += 1
                    existing.last_seen   = datetime.now(timezone.utc)
                else:
                    db.add(models.AccountIdentifier(
                        login            = login,
                        identifier_type  = id_type,
                        identifier_value = id_value,
                    ))
                count += 1

            if count % 1000 == 0:
                db.commit()

        db.commit()
        log.info("Saved %d identifiers (IPs/CIDs/MQIDs)", count)
    except Exception as e:
        db.rollback()
        log.error("save_identifiers error: %s", e)
    finally:
        db.close()


def build_network_edges(traders: list):
    """
    Pre-compute all network connections and store in DB.
    Groups by IP, CID, MQID, family name, IB.
    """
    import models
    db = get_db()
    try:
        # Clear old edges
        db.query(models.NetworkEdge).delete()
        db.commit()

        by_ip     = defaultdict(list)
        by_cid    = defaultdict(list)
        by_mqid   = defaultdict(list)
        by_family = defaultdict(list)
        by_ib     = defaultdict(list)

        for t in traders:
            login = t.get("login")
            if not login:
                continue
            if t.get("lastIP"):
                by_ip[t["lastIP"]].append(login)
            if t.get("clientID"):
                by_cid[t["clientID"]].append(login)
            if t.get("mqid") and t.get("mqid") != 0:
                by_mqid[str(t["mqid"])].append(login)
            name  = t.get("name","")
            family= name.split()[-1] if name and len(name.split()) > 1 else ""
            if family and len(family) > 2:
                by_family[family.lower()].append(login)
            ib = str(t.get("agent",""))
            if ib and ib not in ["0",""]:
                by_ib[ib].append(login)

        edges_added = 0
        seen = set()

        def add_edges(groups, reason, weight):
            nonlocal edges_added
            for value, logins in groups.items():
                if len(logins) < 2:
                    continue
                for i in range(len(logins)):
                    for j in range(i+1, min(len(logins), i+20)):
                        a, b = min(logins[i],logins[j]), max(logins[i],logins[j])
                        key  = (a, b, reason)
                        if key in seen:
                            continue
                        seen.add(key)
                        db.add(models.NetworkEdge(
                            login_a = a,
                            login_b = b,
                            reason  = reason,
                            value   = str(value),
                            weight  = weight,
                        ))
                        edges_added += 1
                        if edges_added % 500 == 0:
                            db.commit()

        add_edges(by_ip,     "ip",     3)
        add_edges(by_cid,    "cid",    3)
        add_edges(by_mqid,   "mqid",   2)
        add_edges(by_family, "family", 1)
        add_edges(by_ib,     "ib",     1)

        db.commit()
        log.info("Network: %d edges computed", edges_added)
    except Exception as e:
        db.rollback()
        log.error("build_network_edges error: %s", e)
    finally:
        db.close()


def save_trading_accounts(traders: list):
    """Save each MT5 login as a trading account record."""
    import models
    db = get_db()
    try:
        count = 0
        for t in traders:
            login = t.get("login")
            if not login:
                continue
            existing = db.query(models.TradingAccount).filter(
                models.TradingAccount.login == login
            ).first()
            if existing:
                existing.balance     = t.get("balance", 0)
                _eq = t.get("equity", 0)
                existing.equity      = _eq if _eq else t.get("balance", 0)
                existing.credit      = t.get("credit", 0)
                existing.margin_level= t.get("marginLevel", 0)
                existing.agent       = t.get("agent", 0)
            else:
                db.add(models.TradingAccount(
                    login       = login,
                    name        = t.get("name",""),
                    email       = t.get("email",""),
                    phone       = t.get("phone",""),
                    group_name  = t.get("group",""),
                    leverage    = t.get("leverage",100),
                    balance     = t.get("balance",0),
                    equity      = t.get("equity",0) or t.get("balance",0),
                    credit      = t.get("credit",0),
                    margin_level= t.get("marginLevel",0),
                    agent       = t.get("agent",0),
                    reg_date    = t.get("reg_date",""),
                ))
            count += 1
            if count % 500 == 0:
                db.commit()
        db.commit()
        log.info("Trading accounts: %d saved", count)
    except Exception as e:
        db.rollback()
        log.error("save_trading_accounts error: %s", e)
    finally:
        db.close()


def seed_default_symbols():
    """Seed default symbols with markup rates if not already set."""
    import models
    db = get_db()
    try:
        if db.query(models.Symbol).count() > 0:
            db.close()
            return
        defaults = [
            # Forex
            {"name":"EURUSD","category":"forex","markup_per_lot":7.0,"display_name":"Euro vs US Dollar"},
            {"name":"GBPUSD","category":"forex","markup_per_lot":7.0,"display_name":"Pound vs US Dollar"},
            {"name":"USDJPY","category":"forex","markup_per_lot":7.0,"display_name":"US Dollar vs Yen"},
            {"name":"USDCHF","category":"forex","markup_per_lot":7.0,"display_name":"US Dollar vs Franc"},
            {"name":"AUDUSD","category":"forex","markup_per_lot":7.0,"display_name":"Aussie vs US Dollar"},
            {"name":"USDCAD","category":"forex","markup_per_lot":7.0,"display_name":"US Dollar vs CAD"},
            {"name":"NZDUSD","category":"forex","markup_per_lot":7.0,"display_name":"NZD vs US Dollar"},
            {"name":"USDZAR","category":"forex","markup_per_lot":5.0,"display_name":"US Dollar vs Rand"},
            # Metals
            {"name":"XAUUSD","category":"metals","markup_per_lot":12.0,"display_name":"Gold vs US Dollar"},
            {"name":"XAGUSD","category":"metals","markup_per_lot":8.0,"display_name":"Silver vs US Dollar"},
            # Indices
            {"name":"US30","category":"indices","markup_per_lot":5.0,"display_name":"Dow Jones"},
            {"name":"SPX500","category":"indices","markup_per_lot":5.0,"display_name":"S&P 500"},
            {"name":"NAS100","category":"indices","markup_per_lot":5.0,"display_name":"Nasdaq 100"},
            {"name":"GER40","category":"indices","markup_per_lot":5.0,"display_name":"Germany 40"},
            # Crypto
            {"name":"BTCUSD","category":"crypto","markup_per_lot":10.0,"display_name":"Bitcoin vs USD"},
            {"name":"ETHUSD","category":"crypto","markup_per_lot":10.0,"display_name":"Ethereum vs USD"},
            # Energy
            {"name":"XTIUSD","category":"energy","markup_per_lot":4.0,"display_name":"Crude Oil WTI"},
            {"name":"XBRUSD","category":"energy","markup_per_lot":4.0,"display_name":"Brent Crude Oil"},
        ]
        for s in defaults:
            db.add(models.Symbol(**s))
        db.commit()
        log.info("Seeded %d default symbols", len(defaults))
    except Exception as e:
        db.rollback()
        log.error("seed_symbols: %s", e)
    finally:
        db.close()


def save_deals_to_db(deals_list: list):
    """
    Save all deals to database.
    Calculates markup profit per deal using symbol rates.
    """
    import models
    db = get_db()
    try:
        # Build symbol markup map
        symbols = db.query(models.Symbol).all()
        markup_map = {s.name: s.markup_per_lot for s in symbols}

        count = 0
        skipped = 0
        for d in deals_list:
            deal_id = d.get("dealId") or d.get("deal_id")
            if not deal_id:
                continue
            # Skip if already exists
            if db.query(models.Deal).filter(models.Deal.deal_id == deal_id).first():
                skipped += 1
                continue

            symbol   = d.get("symbol","")
            volume   = float(d.get("volume",0) or 0)
            markup   = markup_map.get(symbol, 7.0)  # default $7/lot
            markup_profit = round(volume * markup, 2)

            t_time = d.get("time", 0)
            t_str  = ""
            try:
                from datetime import datetime
                t_str = datetime.fromtimestamp(t_time).strftime("%Y-%m-%d") if t_time else ""
            except:
                pass

            t_dt = None
            try:
                from datetime import datetime
                if t_time:
                    t_dt = datetime.fromtimestamp(t_time)
            except:
                pass

            action = d.get("action", 0)
            deal_type = d.get("type", "trade")
            raw_comment = d.get("comment", "") or ""

            # Extract payment method from comment
            payment_method = ""
            if action == 2 and " - " in raw_comment:
                parts = raw_comment.split(" - ")
                if len(parts) >= 3:
                    payment_method = parts[1].strip()

            db.add(models.Deal(
                deal_id       = deal_id,
                login         = d.get("login",0),
                symbol        = symbol,
                action        = action,
                deal_type     = deal_type,
                entry         = d.get("entry",0),
                direction     = "buy" if action == 0 else "sell" if action == 1 else "",
                volume        = volume,
                price         = float(d.get("price",0) or 0),
                profit        = float(d.get("profit",0) or 0),
                commission    = float(d.get("commission",0) or 0),
                swap          = float(d.get("swap",0) or 0),
                comment       = raw_comment,
                balance_after = float(d.get("balance_after",0) or 0),
                markup_profit = markup_profit,
                deal_time     = t_time,
                deal_date     = t_str,
                deal_month    = t_dt.strftime("%Y-%m") if t_dt else "",
                deal_year     = t_dt.year if t_dt else 0,
            ))
            count += 1
            if count % 1000 == 0:
                db.commit()
                log.info("Saved %d deals...", count)

        db.commit()
        log.info("Deals: %d new saved, %d already existed", count, skipped)
    except Exception as e:
        db.rollback()
        log.error("save_deals_to_db: %s", e)
    finally:
        db.close()


def save_clients_to_db(traders: list):
    """Save/update all clients in PostgreSQL."""
    import models
    db = get_db()
    try:
        count = 0
        for t in traders:
            existing = db.query(models.Client).filter(
                models.Client.login == t["login"]
            ).first()
            if existing:
                # Update existing
                existing.name             = t.get("name","")
                existing.email            = t.get("email","")
                existing.phone            = t.get("phone","")
                existing.city             = t.get("city","")
                existing.country          = t.get("country","")
                existing.last_ip          = t.get("lastIP","")
                existing.cid              = t.get("clientID","")
                existing.balance          = t.get("balance",0)
                _eq2 = t.get("equity",0)
                existing.equity           = _eq2 if _eq2 else t.get("balance",0)
                existing.credit           = t.get("credit",0)
                existing.margin_level     = t.get("marginLevel",0)
                existing.leverage         = t.get("leverage",100)
                existing.group_name       = t.get("group","")
                existing.agent            = t.get("agent",0)
                existing.total_deposits   = t.get("totalDeposits",0)
                existing.total_withdrawals= t.get("totalWithdrawals",0)
                existing.first_deposit_at = t.get("firstDepositAt","")
                existing.first_deposit_amount = t.get("firstDepositAmount",0)
                existing.last_deposit_at  = t.get("lastDepositAt","")
                existing.last_withdraw_at = t.get("lastWithdrawAt","")
                existing.last_trade_at    = t.get("lastTradeAt","")
                existing.reg_date         = t.get("reg_date","")
                # kyc_status is OWNED BY THE KYC ENGINE — never clobber a real verification here.
                # (This line used to reset a freshly-approved account back to 'pending' because its
                # balance was $0, which broke the portal KYC banner + the welcome-bonus state.) Only
                # seed it for a legacy account that has no KYC status at all.
                if not (existing.kyc_status or "").strip():
                    existing.kyc_status   = "verified" if t.get("balance",0) > 0 else "pending"
            else:
                # Insert new
                client = models.Client(
                    login             = t["login"],
                    name              = t.get("name",""),
                    email             = t.get("email",""),
                    phone             = t.get("phone",""),
                    city              = t.get("city",""),
                    country           = t.get("country",""),
                    last_ip           = t.get("lastIP",""),
                    cid               = t.get("clientID",""),
                    balance           = t.get("balance",0),
                    equity            = t.get("equity",0) or t.get("balance",0),
                    credit            = t.get("credit",0),
                    margin_level      = t.get("marginLevel",0),
                    leverage          = t.get("leverage",100),
                    group_name        = t.get("group",""),
                    agent             = t.get("agent",0),
                    total_deposits    = t.get("totalDeposits",0),
                    total_withdrawals = t.get("totalWithdrawals",0),
                    first_deposit_at  = t.get("firstDepositAt",""),
                    first_deposit_amount = t.get("firstDepositAmount",0),
                    last_deposit_at   = t.get("lastDepositAt",""),
                    last_withdraw_at  = t.get("lastWithdrawAt",""),
                    last_trade_at     = t.get("lastTradeAt",""),
                    reg_date          = t.get("reg_date",""),
                    kyc_status        = "verified" if t.get("balance",0) > 0 else "pending",
                    source            = t.get("source","none"),
                )
                db.add(client)
            count += 1
            # Commit in batches of 500
            if count % 500 == 0:
                db.commit()
                log.info("Saved %d/%d clients to database...", count, len(traders))
        db.commit()
        log.info("Database updated: %d clients saved", count)

        # Stamp mt_last_seen for every account present in THIS MT pull — the archive detector
        # (archive_accounts.py) archives accounts that STOP appearing in MT (go stale + balance<$1).
        try:
            from sqlalchemy import text as _sqltext
            seen = [t["login"] for t in traders if t.get("login")]
            if seen:
                db.execute(_sqltext("UPDATE clients SET mt_last_seen=NOW() WHERE login = ANY(:l)"),
                           {"l": seen})
                db.commit()
        except Exception as _e:
            db.rollback(); log.warning("mt_last_seen stamp failed: %s", _e)

        # Log sync
        sync = models.SyncLog(
            sync_type  = "full",
            records    = count,
            status     = "ok",
            finished_at= datetime.now(timezone.utc)
        )
        db.add(sync)
        db.commit()
    except Exception as e:
        db.rollback()
        log.error("DB save error: %s", e)
    finally:
        db.close()

def get_clients_from_db() -> list:
    """Read all clients from PostgreSQL."""
    import models
    db = get_db()
    try:
        clients = db.query(models.Client).all()
        result = []
        for c in clients:
            result.append({
                "login":       c.login,
                "name":        c.name,
                "email":       c.email,
                "phone":       c.phone,
                "city":        c.city,
                "country":     c.country,
                "lastIP":      c.last_ip,
                "clientID":    c.cid,
                "balance":     c.balance,
                "equity":      c.equity,
                "credit":      c.credit,
                "marginLevel": c.margin_level,
                "leverage":    c.leverage,
                "group":       c.group_name,
                "agent":       c.agent,
                "riskScore":   c.risk_score,
                "source":      c.source,
                "totalDeposits":      c.total_deposits,
                "totalWithdrawals":   c.total_withdrawals,
                "firstDepositAt":     c.first_deposit_at,
                "firstDepositAmount": c.first_deposit_amount,
                "lastDepositAt":      c.last_deposit_at,
                "lastWithdrawAt":     c.last_withdraw_at,
                "lastTradeAt":        c.last_trade_at,
                "reg_date":           c.reg_date,
                "abuses":             [],
            })
        return result
    finally:
        db.close()

def get_db_count() -> int:
    import models
    db = get_db()
    try:
        return db.query(models.Client).count()
    finally:
        db.close()

# Serialize ALL native MT manager access — the DLL is NOT thread-safe, and the historical
# backfill endpoint runs in a Flask thread alongside sync_loop's daemon thread.
_MGR_LOCK = threading.Lock()

# ── MT5 CONNECTION ─────────────────────────────────────────────────────────
def get_manager():
    global _manager
    if _manager:
        return _manager
    import MT5Manager as mt5manager
    _manager = mt5manager.ManagerAPI()
    ret = _manager.Connect(MT5_SERVER, MT5_LOGIN, MT5_PASSWORD)
    if not ret:
        _manager = None
        raise Exception(f"MT5 connect failed: {ret}")
    log.info("MT5 connected OK")
    return _manager

def user_to_dict(u):
    return {
        "login":      getattr(u,"Login",0),
        "name":       getattr(u,"Name",""),
        "email":      getattr(u,"EMail","") or getattr(u,"Email",""),  # MT5 field is EMail
        "phone":      getattr(u,"Phone",""),
        "country":    getattr(u,"Country",""),
        "city":       getattr(u,"City",""),
        "group":      getattr(u,"Group",""),
        "leverage":   getattr(u,"Leverage",0),
        "balance":    round(float(getattr(u,"Balance",0) or 0),2),
        "credit":     round(float(getattr(u,"Credit",0) or 0),2),
        "equity":     round(float(getattr(u,"Equity",0) or 0),2),
        "marginLevel":round(float(getattr(u,"MarginLevel",0) or 0),2),
        "agent":      getattr(u,"Agent",0),
        "clientID":   str(getattr(u,"ClientID","") or "").strip(),
        "lastIP":     getattr(u,"LastIP",""),
        "riskScore":  "low",
        "abuses":     [],
        "source":     "none",
        "totalDeposits":0,"totalWithdrawals":0,
        "firstDepositAt":"","firstDepositAmount":0,
        "lastDepositAt":"","lastWithdrawAt":"","lastTradeAt":"",
        "reg_date":"",
    }

def get_journal(manager, days=7):
    """
    Get CIDs and IPs from currently online sessions.
    ComputerID = CID (device fingerprint)
    Requires UserSubscribe() first.
    """
    entries = {}
    try:
        # Subscribe to get online session data
        manager.UserSubscribe()
        time.sleep(1)  # wait for data

        total = manager.OnlineTotal()
        log.info("Online sessions: %d", total)

        if total > 0:
            all_sessions = manager.OnlineGetArray() or []
            for session in all_sessions:
                try:
                    login = getattr(session, "Login", 0)
                    cid   = getattr(session, "ComputerID", "") or ""
                    ip    = getattr(session, "Address", "") or ""
                    if login:
                        if login not in entries:
                            entries[login] = {"ip": ip, "cid": cid}
                        else:
                            if cid:
                                entries[login]["cid"] = cid
                            if ip:
                                entries[login]["ip"] = ip
                except Exception as e:
                    log.warning("Session error: %s", e)
                    continue

        log.info("Sessions: %d unique logins (CIDs found: %d)",
                 len(entries),
                 sum(1 for e in entries.values() if e["cid"]))

    except Exception as e:
        log.warning("Session CID fetch failed: %s", e)

    # Also get LastIP from user records as fallback
    try:
        users = manager.UserGetByGroup("*") or []
        for u in users:
            login = getattr(u, "Login", 0)
            ip    = getattr(u, "LastIP", "") or ""
            if login and ip and login not in entries:
                entries[login] = {"ip": ip, "cid": ""}
            elif login and ip and not entries.get(login, {}).get("ip"):
                if login in entries:
                    entries[login]["ip"] = ip
        log.info("LastIP fallback: added IPs for %d logins", len(entries))
    except Exception as e:
        log.warning("LastIP fallback error: %s", e)

    return entries

def enrich_deals(traders_dict, manager):
    try:
        now = int(datetime.now(timezone.utc).timestamp())
        # Smart fetch - will be overridden by days_back if set
        ft  = now - 86400 * 2190  # default 6 years, overridden below
        deals = manager.DealRequestByGroup("*", ft, now) or []
        log.info("Fetched %d deals", len(deals))

        deposits    = defaultdict(list)
        withdrawals = defaultdict(list)
        for d in deals:
            action = getattr(d,"Action",-1)
            login  = getattr(d,"Login",0)
            profit = round(float(getattr(d,"Profit",0) or 0),2)
            t_time = getattr(d,"Time",0)
            t_str  = datetime.fromtimestamp(t_time).strftime("%Y-%m-%d") if t_time else ""
            if action == 2:
                deposits[login].append({"amount":profit,"date":t_str,"time":t_time})
            elif action == 3:
                withdrawals[login].append({"amount":abs(profit),"date":t_str,"time":t_time})

        for login, t in traders_dict.items():
            # For total deposits/withdrawals use DB values (deals cover last 3 years)
            deps  = sorted(deposits.get(login,[]),    key=lambda x:x["time"])
            withs = sorted(withdrawals.get(login,[]), key=lambda x:x["time"])
            if deps:
                t["lastDepositAt"]  = deps[-1]["date"]
                # Only set first deposit if not already set
                if not t.get("firstDepositAt"):
                    t["firstDepositAt"]     = deps[0]["date"]
                    t["firstDepositAmount"] = deps[0]["amount"]
                # Add to existing totals
                t["totalDeposits"]    = round(t.get("totalDeposits",0) + sum(d["amount"] for d in deps),2)
            if withs:
                t["lastWithdrawAt"]   = withs[-1]["date"]
                t["totalWithdrawals"] = round(t.get("totalWithdrawals",0) + sum(w["amount"] for w in withs),2)
    except Exception as e:
        log.warning("enrich_deals: %s", e)

def load_all():
    try:
        manager = get_manager()
        log.info("Fetching users...")
        all_users = manager.UserGetByGroup("*") or []
        log.info("Got %d users", len(all_users))

        traders_dict = {u_dict["login"]: u_dict for u in all_users for u_dict in [user_to_dict(u)]}

        log.info("Fetching journal...")
        journal = get_journal(manager)
        for login, e in journal.items():
            if login in traders_dict:
                if not traders_dict[login]["lastIP"] and e.get("ip"):
                    traders_dict[login]["lastIP"] = e["ip"]
                if e.get("cid"):
                    traders_dict[login]["clientID"] = e["cid"]

        # Smart deal fetch — never deletes existing data
        from database import SessionLocal as _SL
        _db = _SL()
        last_deal   = _db.query(models.Deal).order_by(models.Deal.deal_time.desc()).first()
        oldest_deal = _db.query(models.Deal).order_by(models.Deal.deal_time.asc()).first()
        _db.close()

        now_ts_check = int(datetime.now(timezone.utc).timestamp())
        cutoff = now_ts_check - 86400 * 120

        if last_deal and last_deal.deal_time and oldest_deal and oldest_deal.deal_time and oldest_deal.deal_time <= cutoff:
            # Have 120 days — only fetch last 1 day for new deals
            days_back = 3
            log.info("Fetching deals (last 3 days — incremental sync)...")
        elif oldest_deal and oldest_deal.deal_time and oldest_deal.deal_time > cutoff:
            # Have deals but not 120 days — backfill
            days_back = 120
            log.info("Fetching deals (last 120 days — backfilling)...")
        else:
            # Fetch 120 days
            days_back = 120
            log.info("Fetching deals (last 120 days)...")

        enrich_deals(traders_dict, manager)
        # Sync balance deals to transactions table
        try:
            from sync_transactions import sync
            new_tx = sync()
            log.info("Transaction sync: done")
        except Exception as e:
            log.error("Transaction sync error: %s", e)

        # Also save raw deals to database for symbol/revenue analysis
        log.info("Saving deals to database...")
        try:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            ft_ts  = now_ts - 86400 * days_back
            raw_deals = manager.DealRequestByGroup("*", ft_ts, now_ts) or []
            # account balance at ingest -> stored as balance_after so credit trades (balance<=0,
            # trading on bonus/credit) can be detected. New deals only (existing are skipped on save).
            try:
                _accts = manager.UserAccountGetByGroup("*") or []
                _balmap = {getattr(a, "Login", 0): round(float(getattr(a, "Balance", 0) or 0), 2) for a in _accts}
            except Exception as _e:
                log.warning("balance map fetch failed: %s", _e); _balmap = {}
            deals_list = []
            for d in raw_deals:
                action = getattr(d,"Action",-1)
                deals_list.append({
                    "dealId":       getattr(d,"Deal",0),
                    "login":        getattr(d,"Login",0),
                    "symbol":       getattr(d,"Symbol",""),
                    "action":       action,
                    "type":         (
                        # Action 2 = balance operation
                        "internal_transfer" if action == 2 and "transfer" in (getattr(d,"Comment","") or "").lower() else
                        "deposit"           if action == 2 and float(getattr(d,"Profit",0) or 0) > 0 else
                        "withdrawal"        if action == 2 and float(getattr(d,"Profit",0) or 0) < 0 else
                        # Action 3 = credit operation
                        "credit_in"         if action == 3 and float(getattr(d,"Profit",0) or 0) >= 0 else
                        "credit_out"        if action == 3 and float(getattr(d,"Profit",0) or 0) < 0 else
                        # Action 6 = bonus operation
                        "bonus_deposit"     if action == 6 and float(getattr(d,"Profit",0) or 0) >= 0 else
                        "bonus_withdrawal"  if action == 6 and float(getattr(d,"Profit",0) or 0) < 0 else
                        # Action 14 = internal transfer
                        "internal_transfer" if action == 14 else
                        "trade"
                    ),
                    "payment_method":   (
                        # Extract method from comment: "Deposit - Qi card - USD" → "Qi card"
                        (getattr(d,"Comment","") or "").split(" - ")[1].strip()
                        if action == 2 and " - " in (getattr(d,"Comment","") or "") and
                           len((getattr(d,"Comment","") or "").split(" - ")) >= 3
                        else ""
                    ),
                    "entry":        getattr(d,"Entry",0),
                    "volume":       float(getattr(d,"Volume",0) or 0),
                    "price":        float(getattr(d,"Price",0) or 0),
                    "profit":       float(getattr(d,"Profit",0) or 0),
                    "commission":   float(getattr(d,"Commission",0) or 0),
                    "swap":         float(getattr(d,"Storage",0) or 0),
                    "comment":      getattr(d,"Comment",""),
                    "time":         getattr(d,"Time",0),
                    "balance_after": _balmap.get(getattr(d,"Login",0), float(getattr(d,"Balance",0) or 0)),
                })
            save_deals_to_db(deals_list)
        except Exception as e:
            log.warning("Deals to DB failed: %s", e)

        traders = list(traders_dict.values())
        log.info("Saving %d traders to database...", len(traders))
        save_clients_to_db(traders)
        log.info("Done! %d traders in database", len(traders))

        log.info("Seeding symbols...")
        seed_default_symbols()

        log.info("Saving trading accounts...")
        save_trading_accounts(traders)

        log.info("Collecting CIDs from online sessions...")
        try:
            collect_sessions(manager)
        except Exception as e:
            log.warning("Session collection error: %s", e)

        log.info("Saving identifiers (IP/CID/MQID)...")
        save_identifiers(traders)

        log.info("Building network edges...")
        build_network_edges(traders)

        return True
    except Exception as e:
        log.error("load_all failed: %s", e)
        return False

def collect_sessions(manager):
    """
    Collect CIDs from currently online sessions and save to DB.
    Uses OnlineGetArray() to get all sessions at once.
    """
    import models
    db = get_db()
    try:
        manager.UserSubscribe()
        time.sleep(0.5)

        sessions = manager.OnlineGetArray()
        if not sessions:
            return

        log.info("Online sessions: %d", len(sessions))
        saved = 0
        seen_pairs = set()

        for session in sessions:
            try:
                login = getattr(session, "Login", 0)
                cid   = getattr(session, "ComputerID", "") or ""
                ip    = getattr(session, "Address", "") or ""
                if not login:
                    continue

                # Save CID
                if cid:
                    pair = (login, "cid", cid)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        existing = db.query(models.AccountIdentifier).filter(
                            models.AccountIdentifier.login == login,
                            models.AccountIdentifier.identifier_type == "cid",
                            models.AccountIdentifier.identifier_value == str(cid),
                        ).first()
                        if existing:
                            existing.seen_count = (existing.seen_count or 0) + 1
                            existing.last_seen = datetime.now(timezone.utc)
                        else:
                            db.add(models.AccountIdentifier(
                                login=login, identifier_type="cid", identifier_value=cid
                            ))
                            saved += 1

                # Save IP
                if ip and ip not in ("127.0.0.1", ""):
                    pair_ip = (login, "ip", ip)
                    if pair_ip not in seen_pairs:
                        seen_pairs.add(pair_ip)
                        existing_ip = db.query(models.AccountIdentifier).filter(
                            models.AccountIdentifier.login == login,
                            models.AccountIdentifier.identifier_type == "ip",
                            models.AccountIdentifier.identifier_value == str(ip),
                        ).first()
                        if existing_ip:
                            existing_ip.seen_count = (existing_ip.seen_count or 0) + 1
                            existing_ip.last_seen = datetime.now(timezone.utc)
                        else:
                            db.add(models.AccountIdentifier(
                                login=login, identifier_type="ip", identifier_value=ip
                            ))
                            saved += 1

            except Exception:
                continue

        db.commit()
        log.info("Sessions: saved %d new CIDs/IPs from %d online users", saved, len(sessions))
    except Exception as e:
        db.rollback()
        log.warning("collect_sessions error: %s", e)
    finally:
        db.close()



def update_live_data(manager, db):
    """Every 30s: update equity and margin_level using UserAccountGetByGroup (real equity).
    Also syncs email and MQID from UserGetByGroup for network detection."""
    try:
        # Use UserAccountGetByGroup for REAL equity/margin (includes floating P&L)
        accounts = manager.UserAccountGetByGroup("*") or []
        if not accounts:
            log.warning("UserAccountGetByGroup returned empty")
            return
        updated = 0
        for a in accounts:
            try:
                login        = getattr(a, 'Login', 0)
                balance      = round(float(getattr(a, 'Balance', 0) or 0), 2)
                equity       = round(float(getattr(a, 'Equity', 0) or 0), 2)
                margin       = round(float(getattr(a, 'Margin', 0) or 0), 2)
                margin_level = round(float(getattr(a, 'MarginLevel', 0) or 0), 2)
                free_margin  = round(float(getattr(a, 'MarginFree', 0) or 0), 2)
                # equity=0 with no positions means no open trades — use balance
                if equity == 0 and margin == 0 and balance > 0:
                    equity = balance
                if not login:
                    continue
                db.execute(
                    text("UPDATE clients SET equity=:eq, margin_level=:ml, balance=:bal WHERE login=:l"),
                    {"eq": equity, "ml": margin_level, "bal": balance, "l": login}
                )
                db.execute(
                    text("UPDATE trading_accounts SET equity=:eq, margin_level=:ml, free_margin=:fm, balance=:bal WHERE login=:l"),
                    {"eq": equity, "ml": margin_level, "fm": free_margin, "bal": balance, "l": login}
                )
                updated += 1
            except Exception:
                continue
        db.commit()
        log.info("Live data updated: %d accounts (equity+margin+balance)", updated)

        # Also save email and MQID from UserGetByGroup for network detection
        try:
            all_users = manager.UserGetByGroup("*") or []
            email_count = 0
            mqid_count  = 0
            for u in all_users:
                login = getattr(u, 'Login', 0)
                email = getattr(u, 'EMail', '') or getattr(u, 'Email', '') or ''  # MT5 field is EMail (capital M)
                mqid  = getattr(u, 'MQID', 0) or getattr(u, 'MQId', 0) or 0
                if not login:
                    continue
                if email and '@' in email:
                    existing = db.query(models.AccountIdentifier).filter(
                        models.AccountIdentifier.login == login,
                        models.AccountIdentifier.identifier_type == 'email',
                        models.AccountIdentifier.identifier_value == email,
                    ).first()
                    if not existing:
                        db.add(models.AccountIdentifier(login=login, identifier_type='email', identifier_value=email))
                        email_count += 1
                    # Save email to clients table
                    db.execute(text("UPDATE clients SET email=:e WHERE login=:l AND (email IS NULL OR email='')"),
                               {"e": email, "l": login})
                if mqid and mqid != 0:
                    mqid_str = str(mqid)
                    existing = db.query(models.AccountIdentifier).filter(
                        models.AccountIdentifier.login == login,
                        models.AccountIdentifier.identifier_type == 'mqid',
                        models.AccountIdentifier.identifier_value == mqid_str,
                    ).first()
                    if not existing:
                        db.add(models.AccountIdentifier(login=login, identifier_type='mqid', identifier_value=mqid_str))
                        mqid_count += 1
            db.commit()
            log.info("Email/MQID sync: %d new emails, %d new MQIDs", email_count, mqid_count)
        except Exception as e:
            db.rollback()
            log.error("Email/MQID sync error: %s", e)

    except Exception as e:
        db.rollback()
        log.error("update_live_data error: %s", e)

def sync_accounts_fast():
    """FAST account-only sync — just the user list -> clients (no deal pull). Lets NEW MT5
    accounts appear within ~2 min instead of ~18. The heavy deal/transaction pull is offloaded
    to the dedicated MT5-B (login 1026) worker (mt5_deal_worker.py), so this never blocks."""
    manager = get_manager()
    users = manager.UserGetByGroup("*") or []
    traders = [user_to_dict(u) for u in users]
    if traders:
        save_clients_to_db(traders)   # also stamps mt_last_seen for archive detection
    log.info("Fast account sync: %d accounts", len(traders))


def sync_loop():
    cycle = 0
    while True:
        # Start timer BEFORE running tasks so next cycle starts exactly 30s later
        next_run = time.time() + 30
        cycle += 1
        # Every 30 seconds: collect CIDs + update live equity/margin
        try:
            with _MGR_LOCK:
                _mgr = get_manager()
                if _mgr:
                    _db = get_db()
                    collect_sessions(_mgr)
                    update_live_data(_mgr, _db)
        except Exception as e:
            log.error("Quick sync error: %s", e)
        # Keep MT5 transactions current EVERY cycle (30s) — cheap DB-only upsert of any new
        # balance/credit/bonus deals (action 2/3/6). sync_transactions only inserts deals not
        # already converted, so it's a no-op when nothing new. (Fixed: was only in the 5-min
        # full sync, and sync_transactions itself had a deal_id>MAX bug that MT4 rows broke.)
        try:
            from sync_transactions import sync as _txsync
            _txsync()
        except Exception as e:
            log.error("tx sync error: %s", e)
        # Every 4 cycles (~2 min): FAST account-only sync so new accounts show quickly.
        # (Deals are pulled by the dedicated MT5-B 1026 worker, not here, so this stays light.)
        if cycle % 4 == 0:
            try:
                with _MGR_LOCK:
                    sync_accounts_fast()
            except Exception as e:
                log.error("Account sync error: %s", e)
        # Sleep only remaining time until next 30s mark
        sleep_time = next_run - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

# ── NETWORK GRAPH ──────────────────────────────────────────────────────────
def build_response(traders):
    by_ip = defaultdict(list)
    for t in traders:
        ip = t.get("lastIP","")
        if ip: by_ip[ip].append(t["login"])

    edges, seen = [], set()
    for logins in by_ip.values():
        if len(logins) >= 2:
            for i in range(len(logins)):
                for j in range(i+1, min(len(logins), i+5)):
                    key = (min(logins[i],logins[j]), max(logins[i],logins[j]))
                    if key not in seen:
                        seen.add(key)
                        edges.append({"a":logins[i],"b":logins[j],"reason":"ip","color":"#3b82f6"})

    nodes = []
    for t in traders:
        shared = [l for l in by_ip.get(t.get("lastIP",""),[]) if l != t["login"]]
        net    = min(10, len(shared)*3)
        color  = "green" if net<=2 else "yellow" if net<=4 else "orange" if net<=6 else "red"
        nodes.append({**t,
            "networkScore":       net,
            "networkColor":       color,
            "networkConnections": [{"login":l,"reasons":["IP"]} for l in shared[:5]]
        })
    return {"nodes": nodes, "edges": edges}

# ── MOCK ───────────────────────────────────────────────────────────────────
def make_mock():
    names=[("Ahmed","Al-Rashid"),("Mohammed","Hassan"),("Fatima","Nasser"),("Omar","Khalil"),("Sara","Ibrahim"),("Khalid","Mansour"),("Nadia","Farouk"),("Yusuf","Zayed"),("Layla","Ahmed"),("Hassan","Omar"),("Rania","Khalil"),("Tariq","Mansour"),("Dana","Hassan"),("Faisal","Nasser"),("Maya","Ibrahim"),("Karim","Zayed"),("Lina","Farouk"),("Samir","Al-Rashid"),("Hana","Ahmed"),("Ziad","Omar")]
    cities=["Dubai","Cairo","Riyadh","Istanbul","Amman","Beirut","Baghdad","Muscat","Kuwait City","Doha"]
    sources=["facebook","instagram","google","organic","referral","tiktok","none"]
    ips=[f"41.234.{random.randint(1,5)}.{random.randint(1,254)}" for _ in range(3)]+[f"{random.randint(80,200)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}" for _ in range(17)]
    out=[]
    for i,(first,last) in enumerate(names):
        bal=round(random.uniform(0,60000),2)
        eq=round(bal*random.uniform(0.5,1.2),2)
        out.append({"login":10000+i*7,"name":f"{first} {last}","email":f"{first.lower()}.{last.lower()}@email.com","phone":f"+971{random.randint(500000000,599999999)}","city":random.choice(cities),"country":random.choice(["UAE","Egypt","Saudi Arabia","Turkey","Jordan"]),"lastIP":ips[i],"clientID":f"C{(100000+i*13):06d}","balance":bal,"equity":eq,"credit":round(random.uniform(0,2000),2),"marginLevel":round(random.uniform(0,500),2) if bal>0 else 0,"leverage":random.choice([100,200,500]),"group":"retail\\usd","agent":random.choice([4421,4422,4423,0]),"riskScore":random.choice(["low","low","medium","high"]),"abuses":[],"source":random.choice(sources),"totalDeposits":round(bal+random.uniform(0,30000),2),"totalWithdrawals":round(random.uniform(0,15000),2),"firstDepositAt":(datetime.now()-timedelta(days=random.randint(1,365))).strftime("%Y-%m-%d") if bal>0 else "","firstDepositAmount":round(random.uniform(500,10000),2) if bal>0 else 0,"lastDepositAt":(datetime.now()-timedelta(days=random.randint(1,60))).strftime("%Y-%m-%d") if bal>0 else "","lastWithdrawAt":(datetime.now()-timedelta(days=random.randint(1,90))).strftime("%Y-%m-%d") if random.random()>0.5 else "","lastTradeAt":(datetime.now()-timedelta(days=random.randint(0,14))).strftime("%Y-%m-%d") if bal>0 else "","reg_date":(datetime.now()-timedelta(days=random.randint(30,730))).strftime("%Y-%m-%d")})
    return out

# ── ENDPOINTS ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    count = get_db_count()
    return jsonify({"status":"ok","traders":count,"timestamp":datetime.utcnow().isoformat()+"Z"})

@app.get("/api/deals-probe")
def api_deals_probe():
    """Diagnostic: does the MT5 server still retain deals for a given window? Pass epoch
    seconds ?from=..&to=.. ; returns count + min/max deal time. Used to test if 2024/2025
    history is recoverable from MT (vs only via the legacy import)."""
    frm = int(request.args.get("from", "0")); to = int(request.args.get("to", "0"))
    mgr = get_manager()
    if not mgr:
        return jsonify({"error": "manager not connected"}), 503
    try:
        with _MGR_LOCK:
            deals = mgr.DealRequestByGroup("*", frm, to) or []
        times = [int(getattr(d, "Time", 0) or 0) for d in deals]
        bal = sum(1 for d in deals if int(getattr(d, "Action", -1)) in (2, 3, 6))
        return jsonify({"from": frm, "to": to, "count": len(deals), "balance_ops": bal,
                        "min_time": min(times) if times else 0,
                        "max_time": max(times) if times else 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/backfill")
def api_backfill():
    """Historical deal backfill for one time window. mode=balance saves ONLY balance/credit/
    bonus ops (action 2/3/6 -> deposits/withdrawals); mode=all saves every deal (trades too).
    Idempotent (save_deals_to_db skips existing deal_id). Drive it in weekly chunks from a
    loader script to dodge the MT 'Memory error (6)' on large windows."""
    frm = int(request.args.get("from", "0")); to = int(request.args.get("to", "0"))
    mode = request.args.get("mode", "balance")
    mgr = get_manager()
    if not mgr:
        return jsonify({"error": "manager not connected"}), 503
    try:
        with _MGR_LOCK:
            raw = mgr.DealRequestByGroup("*", frm, to) or []
        out = []
        for d in raw:
            action = int(getattr(d, "Action", -1))
            if mode == "balance" and action not in (2, 3, 6):
                continue
            prof = float(getattr(d, "Profit", 0) or 0)
            out.append({
                "dealId": getattr(d, "Deal", 0), "login": getattr(d, "Login", 0),
                "symbol": getattr(d, "Symbol", ""), "action": action,
                "type": ("deposit" if action == 2 and prof > 0 else
                         "withdrawal" if action == 2 else
                         "bonus_deposit" if action == 6 and prof >= 0 else
                         "bonus_withdrawal" if action == 6 else
                         "credit_in" if action == 3 and prof >= 0 else
                         "credit_out" if action == 3 else "trade"),
                "entry": getattr(d, "Entry", 0), "volume": float(getattr(d, "Volume", 0) or 0),
                "price": float(getattr(d, "Price", 0) or 0), "profit": prof,
                "commission": float(getattr(d, "Commission", 0) or 0),
                "swap": float(getattr(d, "Storage", 0) or 0),
                "comment": getattr(d, "Comment", ""), "time": getattr(d, "Time", 0),
                "balance_after": 0,
            })
        save_deals_to_db(out)
        return jsonify({"window": [frm, to], "fetched": len(raw), "saved_candidates": len(out)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/traders")
def api_traders():
    traders = get_clients_from_db()
    return jsonify(build_response(traders))

@app.get("/api/status")
def api_status():
    count = get_db_count()
    return jsonify({"connected":True,"traders":count})

@app.get("/api/sync")
def api_sync():
    """Manual sync trigger"""
    threading.Thread(target=load_all, daemon=True).start()
    return jsonify({"message":"Sync started"})

@app.get("/users")
def users():
    page=int(request.args.get("page",1))
    page_size=int(request.args.get("page_size",200))
    traders=get_clients_from_db()
    start=(page-1)*page_size
    return jsonify({"total":len(traders),"page":page,"users":traders[start:start+page_size]})

@app.get("/user/<int:login>")
def user(login):
    import models
    db=get_db()
    try:
        c=db.query(models.Client).filter(models.Client.login==login).first()
        if not c: return jsonify({"error":"not found"}),404
        return jsonify({"login":c.login,"name":c.name,"email":c.email,"phone":c.phone,"city":c.city,"country":c.country,"lastIP":c.last_ip,"clientID":c.cid,"balance":c.balance,"equity":c.equity})
    finally:
        db.close()

@app.get("/api/identifiers/<id_type>/<id_value>")
def get_by_identifier(id_type, id_value):
    """
    Find all trading accounts that used a specific IP, CID, or MQID.
    GET /api/identifiers/ip/1.2.3.4
    GET /api/identifiers/cid/C100021
    GET /api/identifiers/mqid/12345
    """
    import models
    db = get_db()
    try:
        records = db.query(models.AccountIdentifier).filter(
            models.AccountIdentifier.identifier_type  == id_type,
            models.AccountIdentifier.identifier_value == str(id_value),
        ).all()
        logins = [r.login for r in records]
        # Get client data for each login
        clients = db.query(models.Client).filter(
            models.Client.login.in_(logins)
        ).all() if logins else []
        return jsonify({
            "identifier_type":  id_type,
            "identifier_value": id_value,
            "count":            len(logins),
            "logins":           logins,
            "clients":          [{"login":c.login,"name":c.name,"email":c.email,"balance":c.balance,"last_ip":c.last_ip,"cid":c.cid} for c in clients],
        })
    finally:
        db.close()


@app.get("/api/client/<int:login>/identifiers")
def get_client_identifiers(login):
    """
    Get ALL IPs, CIDs, MQIDs ever used by a specific trading account.
    Also returns which OTHER accounts share these identifiers.
    """
    import models
    db = get_db()
    try:
        # All identifiers for this login
        my_ids = db.query(models.AccountIdentifier).filter(
            models.AccountIdentifier.login == login
        ).all()

        result = {"login": login, "identifiers": {}, "connected_accounts": {}}

        for id_rec in my_ids:
            id_type  = id_rec.identifier_type
            id_value = id_rec.identifier_value

            if id_type not in result["identifiers"]:
                result["identifiers"][id_type] = []
            result["identifiers"][id_type].append({
                "value":      id_value,
                "first_seen": id_rec.first_seen.isoformat() if id_rec.first_seen else "",
                "last_seen":  id_rec.last_seen.isoformat()  if id_rec.last_seen  else "",
                "seen_count": id_rec.seen_count,
            })

            # Find OTHER accounts with same identifier
            others = db.query(models.AccountIdentifier).filter(
                models.AccountIdentifier.identifier_type  == id_type,
                models.AccountIdentifier.identifier_value == str(id_value),
                models.AccountIdentifier.login            != login,
            ).all()

            for other in others:
                key = f"{id_type}:{id_value}"
                if key not in result["connected_accounts"]:
                    result["connected_accounts"][key] = []
                result["connected_accounts"][key].append({
                    "login":  other.login,
                    "reason": id_type,
                    "value":  id_value,
                })

        # Get network edges
        edges = db.query(models.NetworkEdge).filter(
            (models.NetworkEdge.login_a == login) |
            (models.NetworkEdge.login_b == login)
        ).all()
        result["network_edges"] = [{
            "connected_to": e.login_b if e.login_a == login else e.login_a,
            "reason":       e.reason,
            "value":        e.value,
            "weight":       e.weight,
        } for e in edges]

        return jsonify(result)
    finally:
        db.close()


@app.get("/api/network/clusters")
def get_network_clusters():
    """Get all groups of accounts connected by IP, CID, or MQID."""
    import models
    db = get_db()
    try:
        # Get all edges grouped by shared value
        edges = db.query(models.NetworkEdge).filter(
            models.NetworkEdge.reason.in_(["ip","cid","mqid"])
        ).all()

        clusters = defaultdict(lambda: {"logins":set(),"reason":"","value":""})
        for e in edges:
            key = f"{e.reason}:{e.value}"
            clusters[key]["logins"].add(e.login_a)
            clusters[key]["logins"].add(e.login_b)
            clusters[key]["reason"] = e.reason
            clusters[key]["value"]  = e.value

        result = []
        for key, cluster in clusters.items():
            if len(cluster["logins"]) >= 2:
                logins = list(cluster["logins"])
                clients = db.query(models.Client).filter(
                    models.Client.login.in_(logins)
                ).all()
                result.append({
                    "reason":  cluster["reason"],
                    "value":   cluster["value"],
                    "count":   len(logins),
                    "logins":  logins,
                    "clients": [{"login":c.login,"name":c.name,"balance":c.balance} for c in clients],
                })

        result.sort(key=lambda x: x["count"], reverse=True)
        return jsonify({"clusters": result, "total": len(result)})
    finally:
        db.close()


@app.get("/deals/financial")
def deals():
    return jsonify({"deals":[],"total":0})

@app.get("/journal/logins")
def journal():
    return jsonify({"logins":[],"total":0})

# ── MAIN ───────────────────────────────────────────────────────────────────


@app.route("/neg-cover/check/<int:login>", methods=["GET"])
def neg_check(login):
    """Check one account: balance, credit, flat status."""
    try:
        mgr = get_manager()
        acc = mgr.UserAccountGet(login)
        if not acc:
            return jsonify({"login": login, "error": "no account"}), 404
        bal, cred = float(acc.Balance), float(acc.Credit)
        pos = mgr.PositionGet(login)
        flat = (pos is None or len(pos) == 0)
        return jsonify({"login": login, "balance": bal, "credit": cred, "flat": flat})
    except Exception as e:
        return jsonify({"login": login, "error": str(e)}), 500

def _pull_credit(mgr, login, want, cred_before, comment="Credit Out"):
    """Reclaim `want` credit off `login`, RETRIED + re-read verified (the old code fired one
    DealerBalance(type 3) and never checked it — credit-outs silently failed, leaving bonus on
    covered accounts). Returns (credit_after, credit_removed, ok). Never pulls below 0 credit."""
    want = round(min(want, cred_before), 2)
    target = round(cred_before - want, 2)
    if want <= 0.01:
        return cred_before, 0.0, True
    for _ in range(3):
        acc = mgr.UserAccountGet(login)
        cur = float(acc.Credit) if acc else 0.0
        shortfall = round(cur - target, 2)
        if shortfall <= 0.01:
            break
        mgr.DealerBalance(login, -shortfall, 3, comment)
    acc = mgr.UserAccountGet(login)
    cred_after = float(acc.Credit) if acc else cred_before
    return cred_after, round(cred_before - cred_after, 2), (cred_after - target) <= 0.05


@app.route("/neg-cover/cover/<int:login>", methods=["POST"])
def neg_cover(login):
    """Cover one account, reclaiming min(credit, deficit). Both legs are return-checked + re-read
    verified, and the credit-out is RETRIED.

    HARD INVARIANT (desk, Jul 1 2026): NEVER pay off the negative unless the credit that funded it is
    taken out in the same operation. If the account still holds credit that MT won't release (it's
    margining OPEN positions), we DO NOT touch the balance — status 'skipped_credit_locked' — and
    retry next cycle once the account frees margin / goes flat. This prevents the '562288' state where
    the loss was absorbed 7x while the $100 bonus stayed live.
      - FLAT accounts: proven order (balance->0, then strip credit — the credit-out reliably succeeds
        when there are no positions holding it as margin).
      - Accounts WITH open positions: credit-out FIRST; only pay off the balance if it fully lands."""
    try:
        mgr = get_manager()
        acc = mgr.UserAccountGet(login)
        if not acc:
            return jsonify({"login": login, "status": "no_data"}), 404
        bal_before, cred_before = float(acc.Balance), float(acc.Credit)
        if bal_before >= 0:
            return jsonify({"login": login, "status": "not_negative",
                            "balance_before": bal_before, "credit_before": cred_before})
        deficit = abs(bal_before)
        pos = mgr.PositionGet(login)
        n_pos = 0 if pos is None else len(pos)
        if n_pos > 0:
            # Model 4: cover if floating PnL < $10 (negative or small positive). Skip if PnL >= $10.
            floating = sum(float(p.Profit) for p in pos)
            if floating >= 10:
                return jsonify({"login": login, "status": "has_positions_positive_pnl", "floating_pnl": floating})
        credit_to_take = round(min(cred_before, deficit), 2) if cred_before > 0 else 0.0

        credit_ok = True
        credit_done = False   # True once the credit-out has been applied (positions path pre-pull)
        if n_pos > 0 and credit_to_take > 0:
            # OPEN POSITIONS: strip the credit BEFORE covering. If MT won't release it (margined),
            # abort WITHOUT touching the balance so we never cover a loss while the bonus stays live.
            _, credit_removed, credit_ok = _pull_credit(mgr, login, credit_to_take, cred_before)
            if not credit_ok:
                acc = mgr.UserAccountGet(login)
                return jsonify({"login": login, "status": "skipped_credit_locked",
                                "deficit": deficit, "credit_to_take": credit_to_take,
                                "credit_removed": credit_removed,
                                "balance_before": bal_before, "credit_before": cred_before,
                                "balance_after": float(acc.Balance) if acc else bal_before,
                                "credit_after": float(acc.Credit) if acc else cred_before})
            credit_done = True

        # Balance payoff -> 0 (verify it landed; retry once if still negative)
        mgr.DealerBalance(login, deficit, 5, "Negative balance payoff")
        acc = mgr.UserAccountGet(login)
        if acc and float(acc.Balance) < -0.01:
            mgr.DealerBalance(login, abs(float(acc.Balance)), 5, "Negative balance payoff")
            acc = mgr.UserAccountGet(login)

        # Credit out for the FLAT path (credit reliably releases with no positions holding it).
        # Skipped if the positions-path pre-pull already took it.
        if credit_to_take > 0 and not credit_done:
            _, _, credit_ok = _pull_credit(mgr, login, credit_to_take, cred_before)

        acc = mgr.UserAccountGet(login)
        bal_after = float(acc.Balance) if acc else None
        cred_after = float(acc.Credit) if acc else None
        credit_removed = round(cred_before - (cred_after if cred_after is not None else cred_before), 2)
        return jsonify({"login": login, "status": "covered",
                        "deficit": deficit, "credit_to_take": credit_to_take,
                        "credit_removed": credit_removed, "credit_ok": bool(credit_ok),
                        "balance_before": bal_before, "credit_before": cred_before,
                        "balance_after": bal_after, "credit_after": cred_after})
    except Exception as e:
        return jsonify({"login": login, "status": "error", "error": str(e)}), 500


@app.route("/neg-cover/reclaim-credit/<int:login>", methods=["POST"])
def neg_reclaim_credit(login):
    """Pull a specific amount of CREDIT off an account (verified + retried). Used by the 15-min
    credit-reclaim sweep to finish credit-outs a prior cover failed to apply. Body: {amount}.
    Only acts on accounts at balance>=0 (negatives go through /cover); never pulls below 0 credit."""
    d = request.get_json(force=True, silent=True) or {}
    want = round(float(d.get("amount") or 0), 2)
    try:
        mgr = get_manager()
        acc = mgr.UserAccountGet(login)
        if not acc:
            return jsonify({"login": login, "status": "no_data"}), 404
        bal_before, cred_before = float(acc.Balance), float(acc.Credit)
        if bal_before < -0.01:
            return jsonify({"login": login, "status": "is_negative", "balance": bal_before})
        cred_after, removed, ok = _pull_credit(mgr, login, want, cred_before, "Credit Out (reclaim)")
        return jsonify({"login": login, "status": "reclaimed", "credit_removed": removed,
                        "credit_ok": bool(ok), "balance_before": bal_before,
                        "credit_before": cred_before, "credit_after": cred_after})
    except Exception as e:
        return jsonify({"login": login, "status": "error", "error": str(e)}), 500




@app.route("/positions/<int:login>", methods=["GET"])
def positions_get(login):
    """Read-only: list an account's current OPEN positions (for copy-trade provider view)."""
    try:
        mgr = get_manager()
        if not mgr:
            return jsonify({"positions": [], "error": "manager not connected"}), 503
        pos = mgr.PositionGet(login) or []
        out = []
        for p in pos:
            def g(a, d=None):
                try: return getattr(p, a)
                except Exception: return d
            action = int(g("Action", 0) or 0)
            out.append({
                "symbol": str(g("Symbol", "") or ""),
                "side": "Buy" if action == 0 else "Sell",
                "lots": round(float(g("Volume", 0) or 0) / 10000.0, 2),
                "open_price": float(g("PriceOpen", 0) or 0),
                "price_current": float(g("PriceCurrent", 0) or 0),
                "profit": float(g("Profit", 0) or 0),
                "ticket": int(g("Position", 0) or 0),
            })
        return jsonify({"login": login, "positions": out})
    except Exception as e:
        return jsonify({"login": login, "positions": [], "error": str(e)}), 500

@app.route("/neg-cover/inspect/<int:login>", methods=["GET"])
def neg_inspect(login):
    """Read-only: show balance, credit, equity, floating PnL for diagnosis."""
    try:
        mgr = get_manager()
        acc = mgr.UserAccountGet(login)
        if not acc:
            return jsonify({"login": login, "error": "no account"}), 404
        out = {"login": login}
        for attr in ["Balance","Credit","Equity","Profit","Margin","MarginFree"]:
            try:
                out[attr] = float(getattr(acc, attr))
            except Exception:
                out[attr] = None
        pos = mgr.PositionGet(login)
        out["positions"] = 0 if pos is None else len(pos)
        if pos:
            out["floating_pnl"] = sum(float(p.Profit) for p in pos)
        else:
            out["floating_pnl"] = 0.0
        return jsonify(out)
    except Exception as e:
        return jsonify({"login": login, "error": str(e)}), 500

# ───────────────────────── PROVISIONING (real MT5 account create / credit) ─────────────────────────
@app.route("/provision/create", methods=["POST"])
def provision_create():
    """Create a real MT5 trading account using the bridge's interactive manager connection.
    Body: group, first, last, leverage, email, phone, country, city, agent."""
    import MT5Manager as mt5m
    import random as _r, string as _s
    d = request.get_json(force=True, silent=True) or {}
    try:
        mgr = get_manager()
        if not mgr:
            return jsonify({"ok": False, "error": "manager not connected"}), 503

        def genpw():
            spec = "!@#$%^&*"
            base = (_r.choice(_s.ascii_uppercase) + _r.choice(_s.ascii_lowercase) +
                    _r.choice(_s.digits) + _r.choice(spec))
            base += "".join(_r.choice(_s.ascii_letters + _s.digits + spec) for _ in range(8))
            return "".join(_r.sample(base, len(base)))

        first = (d.get("first") or "").strip(); last = (d.get("last") or "").strip()
        u = mt5m.MTUser(mgr)
        u.Login = 0
        u.Group = d.get("group") or "demo\\demoforex"
        u.Name = (first + " " + last).strip() or "Client"
        for fld, val in (("FirstName", first), ("LastName", last)):
            try: setattr(u, fld, val)
            except Exception: pass
        try: u.Leverage = int(d.get("leverage") or 500)
        except Exception: pass
        for fld, key in (("EMail", "email"), ("Phone", "phone"), ("Country", "country"), ("City", "city")):
            try: setattr(u, fld, d.get(key) or "")
            except Exception: pass
        try: u.Agent = int(d.get("agent") or 0)
        except Exception: pass
        try:
            R = mt5m.MTUser.EnUsersRights
            u.Rights = getattr(R, "USER_RIGHT_DEFAULT", u.Rights)
        except Exception: pass

        master = d.get("master") or genpw()
        investor = d.get("investor") or genpw()
        res = mgr.UserAdd(u, master, investor)
        login = int(getattr(u, "Login", 0) or 0)
        if not login:
            try: err = str(mt5m.LastError())
            except Exception: err = f"UserAdd returned {res}"
            return jsonify({"ok": False, "error": err or "UserAdd failed"}), 500
        return jsonify({"ok": True, "login": login, "master": master, "investor": investor, "group": u.Group})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/provision/credit/<int:login>", methods=["POST"])
def provision_credit(login):
    """Money operation on an account via DealerBalance. Body: amount, comment, type.
    type 2 = BALANCE (real deposit, default), type 3 = CREDIT (bonus credit — counts toward margin,
    NOT freely withdrawable). The welcome bonus uses type 3 so it shows as Credit on the terminal."""
    d = request.get_json(force=True, silent=True) or {}
    try:
        mgr = get_manager()
        if not mgr:
            return jsonify({"ok": False, "error": "manager not connected"}), 503
        amount = float(d.get("amount") or 0); comment = d.get("comment") or "Deposit"
        ctype = int(d.get("type") or 2)
        ok = mgr.DealerBalance(login, amount, ctype, comment)
        return jsonify({"ok": bool(ok), "login": login, "amount": amount, "type": ctype})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/provision/delete/<int:login>", methods=["POST"])
def provision_delete(login):
    """Delete an account (used to clean up the single-account test)."""
    try:
        mgr = get_manager()
        if not mgr:
            return jsonify({"ok": False, "error": "manager not connected"}), 503
        return jsonify({"ok": bool(mgr.UserDelete(login))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/provision/password/<int:login>", methods=["POST"])
def provision_password(login):
    """Change a trading account's master or investor password. Body: password, kind(master|investor)."""
    import MT5Manager as mt5m
    d = request.get_json(force=True, silent=True) or {}
    pw = (d.get("password") or "").strip()
    kind = (d.get("kind") or "master").lower()
    try:
        mgr = get_manager()
        if not mgr:
            return jsonify({"ok": False, "error": "manager not connected"}), 503
        if not pw:
            return jsonify({"ok": False, "error": "no password"}), 400
        R = mt5m.MTUser.EnUsersPasswords
        ptype = getattr(R, "USER_PASS_INVESTOR") if kind == "investor" else getattr(R, "USER_PASS_MAIN")
        ok = mgr.UserPasswordChange(ptype, int(login), pw)
        if not ok:
            try: err = str(mt5m.LastError())
            except Exception: err = "UserPasswordChange failed"
            return jsonify({"ok": False, "error": err}), 500
        return jsonify({"ok": True, "login": login, "kind": kind})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/provision/leverage/<int:login>", methods=["POST"])
def provision_leverage(login):
    """Change a trading account's leverage. Body: leverage (e.g. 500)."""
    d = request.get_json(force=True, silent=True) or {}
    try:
        lev = int(d.get("leverage") or 0)
        if lev <= 0:
            return jsonify({"ok": False, "error": "bad leverage"}), 400
        mgr = get_manager()
        if not mgr:
            return jsonify({"ok": False, "error": "manager not connected"}), 503
        u = None
        for meth in ("UserRequest", "UserGet"):
            try:
                if hasattr(mgr, meth):
                    u = getattr(mgr, meth)(int(login))
                    if u:
                        break
            except Exception:
                u = None
        if not u:
            return jsonify({"ok": False, "error": "user not found"}), 404
        u.Leverage = lev
        ok = mgr.UserUpdate(u)
        return jsonify({"ok": bool(ok), "login": login, "leverage": lev})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/provision/group/<int:login>", methods=["POST"])
def provision_group(login):
    """Change a trading account's GROUP (used to set the IB rebate tier, e.g. IB\\IB-7).
    Body: group (required). dry=true (default) only echoes the intended change."""
    d = request.get_json(force=True, silent=True) or {}
    grp = (d.get("group") or "").strip()
    dry = d.get("dry", True)
    if not grp:
        return jsonify({"ok": False, "error": "no group"}), 400
    try:
        mgr = get_manager()
        if not mgr:
            return jsonify({"ok": False, "error": "manager not connected"}), 503
        u = None
        for meth in ("UserRequest", "UserGet"):
            try:
                if hasattr(mgr, meth):
                    u = getattr(mgr, meth)(int(login))
                    if u:
                        break
            except Exception:
                u = None
        if not u:
            return jsonify({"ok": False, "error": "user not found"}), 404
        old = getattr(u, "Group", "")
        if dry:
            return jsonify({"ok": True, "dry": True, "login": login, "old_group": old, "new_group": grp})
        u.Group = grp
        ok = mgr.UserUpdate(u)
        return jsonify({"ok": bool(ok), "login": login, "old_group": old, "new_group": grp})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ───────────────────────── COPY-TRADE EXECUTION (gated, real money) ─────────────────────────
# These place/close REAL positions on a client account. TRIPLE-GATED:
#   • env COPY_BRIDGE_TRADING must be "1" (default off -> every call returns a dry echo),
#   • per-request "dry" defaults True (caller must explicitly pass dry=false),
#   • a hard lots cap (COPY_TRADE_MAX_LOTS, default 1.0).
# Built for the supervised ONE-ACCOUNT test. The exact MT5Manager dealer-trade call is
# validated during that test; until then nothing here can fire (dry echo).
import os as _os
COPY_BRIDGE_TRADING = _os.getenv("COPY_BRIDGE_TRADING", "0") == "1"
COPY_TRADE_MAX_LOTS = float(_os.getenv("COPY_TRADE_MAX_LOTS", "1.0"))

def _dealer_trade(mgr, login, symbol, side, lots, position_ticket=None):
    """Open (position_ticket=None) or close (ticket given) via the MT5 manager dealer API.
    Returns (ok, ref, error). Isolated so the supervised test can validate/adjust the exact
    MTRequest fields against the live SDK without touching the route logic."""
    import MT5Manager as mt5m
    req = mt5m.MTRequest(mgr)
    volume = int(round(float(lots) * 10000))   # MT5 native volume = lots*10000 (deals.volume/10000=lots)
    # best-effort field set (mirrors provision_create's defensive setattr style)
    def _set(obj, **kv):
        for k, v in kv.items():
            try: setattr(obj, k, v)
            except Exception: pass
    try:
        ot = mt5m.MTRequest.EnOrderType
        otype = getattr(ot, "OP_BUY" if side == "buy" else "OP_SELL",
                        0 if side == "buy" else 1)
    except Exception:
        otype = 0 if side == "buy" else 1
    try:
        ta = mt5m.MTRequest.EnTradeActions
        action = getattr(ta, "TA_DEALER_POS_EXECUTE", getattr(ta, "TA_DEALER_EXECUTE", 0))
    except Exception:
        action = 0
    _set(req, Action=action, Login=int(login), Symbol=symbol, Type=otype, Volume=volume)
    if position_ticket:
        _set(req, Position=int(position_ticket))
    try:
        confirm = mgr.DealerSend(req)
        if not confirm:
            try: err = str(mt5m.LastError())
            except Exception: err = "DealerSend returned falsy"
            return False, None, err
        ref = None
        for attr in ("Deal", "Order", "Position"):
            try:
                ref = int(getattr(confirm, attr)); break
            except Exception:
                continue
        return True, ref, None
    except Exception as e:
        return False, None, str(e)

@app.route("/trade/open", methods=["POST"])
def trade_open():
    d = request.get_json(force=True, silent=True) or {}
    login = int(d.get("login") or 0); symbol = (d.get("symbol") or "").strip()
    side = (d.get("side") or "").strip().lower(); lots = float(d.get("lots") or 0)
    dry = d.get("dry", True)
    if not login or not symbol or side not in ("buy", "sell") or lots <= 0:
        return jsonify({"ok": False, "error": "bad params"}), 400
    if lots > COPY_TRADE_MAX_LOTS:
        return jsonify({"ok": False, "error": f"lots {lots} exceeds cap {COPY_TRADE_MAX_LOTS}"}), 400
    if dry or not COPY_BRIDGE_TRADING:
        return jsonify({"ok": True, "dry": True, "trading_enabled": COPY_BRIDGE_TRADING,
                        "would": {"login": login, "symbol": symbol, "side": side, "lots": lots}})
    mgr = get_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "manager not connected"}), 503
    ok, ref, err = _dealer_trade(mgr, login, symbol, side, lots)
    return jsonify({"ok": ok, "dry": False, "ref": ref, "error": err}), (200 if ok else 500)

@app.route("/trade/close", methods=["POST"])
def trade_close():
    """Close the (first) open position for login on symbol — mirrors a master's close."""
    d = request.get_json(force=True, silent=True) or {}
    login = int(d.get("login") or 0); symbol = (d.get("symbol") or "").strip()
    dry = d.get("dry", True)
    if not login or not symbol:
        return jsonify({"ok": False, "error": "bad params"}), 400
    mgr = get_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "manager not connected"}), 503
    pos = mgr.PositionGet(login) or []
    target = next((p for p in pos if str(getattr(p, "Symbol", "")) == symbol), None)
    if not target:
        return jsonify({"ok": False, "error": "no open position for symbol"}), 404
    tick = int(getattr(target, "Position", 0) or 0)
    p_side = "sell" if int(getattr(target, "Action", 0)) == 0 else "buy"   # close = opposite
    lots = float(getattr(target, "Volume", 0)) / 10000.0
    if dry or not COPY_BRIDGE_TRADING:
        return jsonify({"ok": True, "dry": True, "trading_enabled": COPY_BRIDGE_TRADING,
                        "would_close": {"login": login, "symbol": symbol, "ticket": tick, "lots": lots}})
    ok, ref, err = _dealer_trade(mgr, login, symbol, p_side, lots, position_ticket=tick)
    return jsonify({"ok": ok, "dry": False, "ref": ref, "error": err}), (200 if ok else 500)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    # Create DB tables
    from database import engine, Base
    import models
    Base.metadata.create_all(bind=engine)
    log.info("Database tables ready")

    if args.mock:
        log.info("MOCK mode — saving 20 fake traders to database")
        save_clients_to_db(make_mock())
    else:
        log.info("Connecting to MT5: %s", MT5_SERVER)
        # Start the live sync loop immediately — do NOT block startup on an initial full
        # load_all(). That synchronous call can hang on the MT manager 'Memory error (6)'
        # during large deal requests and prevent the bridge from EVER binding :5000 or
        # capturing sessions (observed stuck >20 min on 2026-06-22). sync_loop captures
        # sessions/equity every 30s and runs the full deal+transaction load every 5 min on
        # its own thread, so the bridge goes live in seconds regardless of the deal load.
        threading.Thread(target=sync_loop, daemon=True).start()

    log.info("Bridge on http://0.0.0.0:%d", args.port)
    app.run(host="0.0.0.0", port=args.port, debug=False)
