"""
ib_trades.py — per-closed-trade IB commission with eligibility rules.

FIFO-pairs MT5 open(entry=0)/close(entry=1) deals per (login,symbol) to reconstruct each closed
trade: open/close time+price, hold duration, lots, profit. Applies eligibility:
  • 5-MIN RULE:  hold < 300s  -> NOT eligible (no commission; hidden from IB section)
  • CREDIT RULE: trade funded by credit/bonus -> 'credit' (excluded)
                 NOTE: needs per-trade balance, which the bridge does not yet capture
                 (deals.balance_after is all 0). So historically this flags ~nothing; it is a
                 GOING-FORWARD rule once the bridge records balance. The framework/flag is here.
Commission per eligible trade = lots × comm_per_lot  (commission_rates for the IB level + symbol).

Writes table `ib_trades` (data source for the IB 'Trades' & 'Credit Trades' tabs) and recomputes
per-IB eligible commission. Reports the 5-min-rule savings.
"""
import datetime
import psycopg2
from psycopg2.extras import execute_values
from collections import deque
import ib_commission as IC

PG_DSN = IC.PG_DSN
MIN_HOLD = 300   # 5 minutes


def acct_type(symbol):
    s = symbol.lower()
    if s.endswith(".c"): return "Cent"
    if s.endswith(".x"): return "FIX"
    if s.endswith(".v"): return "VIP"
    if s.endswith("."):  return "Zero"
    return "Standard"


def main():
    cn = psycopg2.connect(PG_DSN); cn.autocommit = False; cur = cn.cursor()

    # account info for every login under an IB (level 5-10)
    cur.execute("""
        SELECT c.login, ib.id, ib.agent_id, ib.ib_level, c.id, c.name, c.country, c.city,
               COALESCE(NULLIF(c.platform,''),'MT5')
        FROM clients c JOIN ibs ib ON ib.agent_id = c.agent AND ib.ib_level BETWEEN 5 AND 10
    """)
    info = {r[0]: dict(ib_id=r[1], agent=r[2], level=r[3], cid=r[4], name=r[5],
                       country=r[6], city=r[7], platform=r[8]) for r in cur.fetchall()}
    logins = list(info.keys())
    print(f"{len(logins):,} accounts under IBs", flush=True)

    cur.execute("SELECT ib_level, symbol, comm_per_lot FROM commission_rates")
    rate = {(r[0], r[1]): r[2] for r in cur.fetchall()}
    cur.execute("SELECT symbol, point_value_profit, currency_profit FROM mt5_symbol_specs")
    point_usd = {s: float(pv or 0) * IC.CCY_USD.get(c or "USD", 1.0) for s, pv, c in cur.fetchall()}
    cn.commit()   # release read locks (clients/ibs/specs) so the long build can't block other writers

    # build into a staging table, then atomically swap -> no empty window for live readers
    cur.execute("DROP TABLE IF EXISTS ib_trades_build")
    cur.execute("""CREATE TABLE ib_trades_build (
        id BIGSERIAL PRIMARY KEY,
        deal_id BIGINT,
        ib_id INT, agent_id BIGINT, ib_level INT,
        login BIGINT, client_id INT, client_name TEXT, country TEXT, city TEXT,
        platform TEXT, account_type TEXT, symbol TEXT, direction TEXT,
        open_time TIMESTAMP, close_time TIMESTAMP, hold_sec INT,
        lots DOUBLE PRECISION, open_price DOUBLE PRECISION, close_price DOUBLE PRECISION,
        profit DOUBLE PRECISION, comm_per_lot DOUBLE PRECISION,
        commission DOUBLE PRECISION, eligible BOOLEAN, reason TEXT
    )""")
    cn.commit()

    INSERT = """INSERT INTO ib_trades_build
        (deal_id,ib_id,agent_id,ib_level,login,client_id,client_name,country,city,platform,account_type,
         symbol,direction,open_time,close_time,hold_sec,lots,open_price,close_price,profit,
         comm_per_lot,commission,eligible,reason) VALUES %s"""

    rd = cn.cursor(name="deals_stream")
    rd.itersize = 50000
    rd.execute("""
        SELECT login, symbol, entry, action, volume, price, profit, deal_time, COALESCE(balance_after,0), deal_id
        FROM deals WHERE platform='MT5' AND action IN (0,1) AND login = ANY(%s)
        ORDER BY login, symbol, deal_time, entry
    """, (logins,))

    ts = datetime.datetime.utcfromtimestamp
    cur_key = None
    q = deque()                 # open lots: [open_time, remaining_vol, open_price]
    batch = []
    n_trades = n_short = 0
    comm_all = comm_eligible = 0.0

    def emit(inf, symbol, action, otime, ctime, vol, oprice, cprice, prof, cpl=None, platform="MT5", bal=None, did=None):
        nonlocal n_trades, n_short, comm_all, comm_eligible
        if cpl is None:
            cpl = rate.get((inf["level"], symbol), 0.0)
        # MT4 volume is already in lots (0.01, 0.1…); MT5 uses 1 lot = 10000
        lots = vol if platform == "MT4" else (vol / 10000.0)
        hold = (ctime - otime) if (otime is not None) else None
        # eligibility: credit (balance<0, trading on bonus) and <5-min trades are NOT paid
        credit = (bal is not None) and (bal < 0)
        short = (hold is not None) and (hold < MIN_HOLD)
        eligible = (not credit) and (not short)
        reason = "credit" if credit else ("short(<5min)" if short else ("no_open_pair" if hold is None else "ok"))
        gross = lots * cpl
        comm = gross if eligible else 0.0
        comm_all += gross
        comm_eligible += comm
        n_trades += 1
        if not eligible:
            n_short += 1
        batch.append((did, inf["ib_id"], inf["agent"], inf["level"], inf["login_id"], inf["cid"],
                      inf["name"], inf["country"], inf["city"], platform, acct_type(symbol),
                      symbol, ("buy" if action == 1 else "sell"),
                      ts(otime) if otime else None, ts(ctime), (int(hold) if hold is not None else None),
                      lots, oprice, cprice, prof, cpl, comm, eligible, reason))

    for login, symbol, entry, action, volume, price, profit, dtime, bal, deal_id in rd:
        key = (login, symbol)
        if key != cur_key:
            cur_key = key; q.clear()
        inf = info.get(login)
        if inf is None:
            continue
        inf["login_id"] = login
        if entry == 0:                      # open
            q.append([dtime, volume, price])
        else:                               # close (entry=1) — deal_id of the close = the trade ID
            remaining = volume
            while remaining > 0 and q:
                o = q[0]
                chunk = min(remaining, o[1])
                o[1] -= chunk; remaining -= chunk
                if o[1] <= 0: q.popleft()
                emit(inf, symbol, action, o[0], dtime, chunk, o[2], price,
                     profit * (chunk / volume) if volume else 0.0, bal=bal, did=deal_id)
            if remaining > 0:               # close with no matching open in data
                emit(inf, symbol, action, None, dtime, remaining, None, price,
                     profit * (remaining / volume) if volume else 0.0, bal=bal, did=deal_id)
        if len(batch) >= 5000:
            execute_values(cur, INSERT, batch); batch.clear()
    if batch:
        execute_values(cur, INSERT, batch)
    rd.close()
    cn.commit()
    print(f"MT5 done: {n_trades:,} trades")

    # ── MT4 pass ── journal deals have no 'entry'; pair by direction per (login,symbol).
    # commission via the live rule engine; point value mapped from MT5 specs (exact, else base symbol).
    rules_by_level = {lvl: IC.load_profile_rules(cur, lvl) for lvl in range(5, 11)}
    def mt4_cpl(level, symbol):
        rule = IC.match_rule(rules_by_level.get(level) or [], symbol)
        if not rule:
            return 0.0
        if rule["distribution"] == "usd_per_lot":
            return rule["value"]
        pu = point_usd.get(symbol)
        if pu is None:
            pu = point_usd.get(symbol.split(".")[0])     # strip suffix -> base symbol
        return rule["value"] * pu if pu is not None else 0.0

    rd4 = cn.cursor(name="deals_mt4")
    rd4.itersize = 20000
    rd4.execute("""SELECT login, symbol, action, volume, price, profit, deal_time, COALESCE(balance_after,0), deal_id
                   FROM deals WHERE platform='MT4' AND action IN (0,1) AND login = ANY(%s)
                   ORDER BY login, symbol, deal_time""", (logins,))
    cur_key = None; q = deque(); n4 = 0
    for login, symbol, action, volume, price, profit, dtime, bal, deal_id in rd4:
        key = (login, symbol)
        if key != cur_key:
            cur_key = key; q.clear()
        inf = info.get(login)
        if inf is None:
            continue
        inf["login_id"] = login
        cpl = mt4_cpl(inf["level"], symbol)
        # a deal of the opposite direction to the queued opens CLOSES them (round trip)
        if q and q[0][3] != action:
            remaining = volume
            while remaining > 0 and q and q[0][3] != action:
                o = q[0]
                chunk = min(remaining, o[1]); o[1] -= chunk; remaining -= chunk
                if o[1] <= 0: q.popleft()
                emit(inf, symbol, action, o[0], dtime, chunk, o[2], price,
                     profit * (chunk / volume) if volume else 0.0, cpl=cpl, platform="MT4", bal=bal, did=deal_id)
                n4 += 1
            if remaining > 0:
                q.append([dtime, remaining, price, action])
        else:
            q.append([dtime, volume, price, action])
        if len(batch) >= 5000:
            execute_values(cur, INSERT, batch); batch.clear()
    if batch:
        execute_values(cur, INSERT, batch)
    rd4.close(); cn.commit()
    print(f"MT4 done: {n4:,} trades")

    cur.execute("CREATE INDEX ix_ibtrb_ib ON ib_trades_build(ib_id)")
    cur.execute("CREATE INDEX ix_ibtrb_login ON ib_trades_build(login)")
    cur.execute("CREATE INDEX ix_ibtrb_close ON ib_trades_build(close_time)")
    # atomic swap (DDL is transactional in Postgres — readers see the old table until COMMIT)
    cur.execute("DROP TABLE IF EXISTS ib_trades")
    cur.execute("ALTER TABLE ib_trades_build RENAME TO ib_trades")
    cur.execute("ALTER INDEX ix_ibtrb_ib RENAME TO ix_ibtr_ib")
    cur.execute("ALTER INDEX ix_ibtrb_login RENAME TO ix_ibtr_login")
    cur.execute("ALTER INDEX ix_ibtrb_close RENAME TO ix_ibtr_close")
    cn.commit()

    # recompute IB commission from ELIGIBLE trades only
    cur.execute("UPDATE ibs SET commission_new = 0")
    cur.execute("""UPDATE ibs ib SET commission_new = x.c
                   FROM (SELECT ib_id, SUM(commission) c FROM ib_trades WHERE eligible GROUP BY ib_id) x
                   WHERE ib.id = x.ib_id""")
    cur.execute("""UPDATE ibs SET total_commission = COALESCE(commission_new,0),
                   unpaid_commission = GREATEST(COALESCE(commission_new,0)-COALESCE(paid_commission,0),0)""")
    cn.commit()

    print(f"\ntrades built: {n_trades:,}   short(<5min): {n_short:,}")
    print(f"commission WITHOUT 5-min rule: ${comm_all:,.2f}")
    print(f"commission WITH 5-min rule:    ${comm_eligible:,.2f}")
    print(f"SAVINGS from 5-min rule:       ${comm_all - comm_eligible:,.2f}")
    cur.execute("SELECT COUNT(*), ROUND(SUM(profit)::numeric,2) FROM ib_trades WHERE NOT eligible")
    print("short-trade rows:", cur.fetchone())
    cn.close()


if __name__ == "__main__":
    main()
