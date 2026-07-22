"""
ib_trades.py — per-closed-trade IB commission with eligibility rules.

FIFO-pairs MT5 open(entry=0)/close(entry=1) deals per (login,symbol) to reconstruct each closed
trade: open/close time+price, hold duration, lots, profit. Applies eligibility:
  • 5-MIN RULE:  DISABLED (MIN_HOLD=0) Jul 22 2026 — Plugit pays <5min scalps, so we match it.
                 (was: hold < 300s -> NOT eligible. Set MIN_HOLD=300 to restore.)
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
MIN_HOLD = 0     # 5-min short-trade rule DISABLED (desk Jul 22 2026): Plugit PAYS <5min scalps, so
                 # excluding them made our live-era commission diverge below Plugit. 0 => no trade is
                 # ever "short" (hold < 0 is impossible). Pre-cutoff stays excel-authoritative regardless.
                 # To restore the rule, set back to 300.
# last trade date covered by the Plugit Commission Report Excels (2023..26). Commission for trades
# AFTER this date is computed live from ib_trades; before it, the Excel is authoritative.
# Bump this when a newer yearly report is imported (keep in sync with commission_years_import.COVER_HI).
EXCEL_CUTOFF = "2026-07-17"


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

    # CLOSE-BY DEDUP: one closing deal that closes several open positions is FIFO-split into
    # multiple rows that all share the same deal_id (the ticket). That shows the SAME ticket
    # 2-4x in the Trades view and double-counts its commission. Collapse to ONE row per
    # (login, deal_id): sum lots/profit/commission (totals unchanged), widen the open/close
    # window. Eligible if ANY leg was eligible.
    cur.execute("CREATE INDEX ix_ibtrb_dedup ON ib_trades_build(login, deal_id)")
    # EXCEL OVERLAY (desk rule Jul 9 2026): for trades closed in the excel era (<= EXCEL_CUTOFF) the
    # per-trade commission is EXACTLY what Plugit paid (excel_trade_commission, keyed login+ticket) —
    # our engine is NOT used for that era. Era trade not in the sheets => $0 / 'not in Plugit report'.
    # After the cutoff the engine values (rates x current level, 5-min rule) apply unchanged.
    cur.execute("SELECT to_regclass('public.excel_trade_commission')")
    has_excel = bool(cur.fetchone()[0])
    if not has_excel:
        print("WARNING: excel_trade_commission missing — era trades keep engine values this run")
    overlay_join = ("LEFT JOIN excel_trade_commission e ON e.login = g.login AND e.deal_id = g.deal_id"
                    if has_excel else
                    "LEFT JOIN (SELECT NULL::bigint login, NULL::bigint deal_id, NULL::float commission) e ON FALSE")
    cur.execute(f"""
        CREATE TABLE ib_trades_final AS
        SELECT g.id, g.deal_id, g.ib_id, g.agent_id, g.ib_level, g.login, g.client_id,
               g.client_name, g.country, g.city, g.platform, g.account_type, g.symbol,
               g.direction, g.open_time, g.close_time, g.hold_sec, g.lots, g.open_price,
               g.close_price, g.profit,
               CASE WHEN g.close_time < TIMESTAMP '{EXCEL_CUTOFF}' + INTERVAL '1 day'
                    THEN COALESCE(e.commission,0) / NULLIF(g.lots,0)
                    ELSE g.comm_per_lot END AS comm_per_lot,
               g.comm_per_lot AS eng_cpl,   -- engine per-lot rate, kept regardless of era so the
                                            -- credit/short "saved" (potential) is valued even pre-cutoff
               CASE WHEN g.close_time < TIMESTAMP '{EXCEL_CUTOFF}' + INTERVAL '1 day'
                    THEN COALESCE(e.commission,0)
                    ELSE g.commission END AS commission,
               CASE WHEN g.close_time < TIMESTAMP '{EXCEL_CUTOFF}' + INTERVAL '1 day'
                    THEN COALESCE(e.commission,0) > 0
                    ELSE g.eligible END AS eligible,
               CASE WHEN g.close_time >= TIMESTAMP '{EXCEL_CUTOFF}' + INTERVAL '1 day' THEN g.reason
                    WHEN e.deal_id IS NULL THEN 'not in Plugit report'
                    WHEN e.commission <= 0 THEN 'Plugit paid $0'
                    ELSE NULL END AS reason
        FROM (
        SELECT MIN(id) AS id, deal_id, MIN(ib_id) AS ib_id, MIN(agent_id) AS agent_id,
               MIN(ib_level) AS ib_level, login, MIN(client_id) AS client_id,
               MIN(client_name) AS client_name, MIN(country) AS country, MIN(city) AS city,
               MIN(platform) AS platform, MIN(account_type) AS account_type, MIN(symbol) AS symbol,
               MIN(direction) AS direction, MIN(open_time) AS open_time, MAX(close_time) AS close_time,
               GREATEST(EXTRACT(EPOCH FROM (MAX(close_time) - MIN(open_time)))::int, 0) AS hold_sec,
               SUM(lots) AS lots, MIN(open_price) AS open_price, MAX(close_price) AS close_price,
               SUM(profit) AS profit, MAX(comm_per_lot) AS comm_per_lot,
               SUM(commission) AS commission, bool_or(eligible) AS eligible, MIN(reason) AS reason
        FROM ib_trades_build
        GROUP BY login, deal_id
        ) g
        {overlay_join}
    """)
    cur.execute("DROP TABLE ib_trades_build")
    cur.execute("CREATE INDEX ix_ibtrf_ib ON ib_trades_final(ib_id)")
    cur.execute("CREATE INDEX ix_ibtrf_login ON ib_trades_final(login)")
    cur.execute("CREATE INDEX ix_ibtrf_close ON ib_trades_final(close_time)")
    # atomic swap (DDL is transactional in Postgres — readers see the old table until COMMIT)
    cur.execute("DROP TABLE IF EXISTS ib_trades")
    cur.execute("ALTER TABLE ib_trades_final RENAME TO ib_trades")
    cur.execute("ALTER INDEX ix_ibtrf_ib RENAME TO ix_ibtr_ib")
    cur.execute("ALTER INDEX ix_ibtrf_login RENAME TO ix_ibtr_login")
    cur.execute("ALTER INDEX ix_ibtrf_close RENAME TO ix_ibtr_close")
    cn.commit()

    # ── CREDIT RULE v2 (ALL-TIME, ledger-based) ─────────────────────────────────────────────
    # deals.balance_after is captured for only ~3-20% of deals, so the old bal<0 check flagged
    # almost nothing. Instead reconstruct each account's CASH ledger from the deals themselves:
    #   cash   = running sum of balance ops (action 2) + realised trade PnL (action 0/1)
    #   credit = running sum of credit/bonus ops (action 3/6)
    # A trade OPENED while cash <= 0 and credit > 0 is riding on bonus money -> 'credit'.
    # Scope is ALL-TIME (desk Jul 15 2026): almost all credit trading is PRE-cutoff, so limiting
    # this to the engine era hid ~97% of it. SAFETY: we only re-flag trades we did NOT already pay
    # (t.commission = 0) or engine-era eligible trades — so PAID commission (excel-authoritative
    # pre-cutoff, total_commission, commission_live) is never reduced. eng_cpl values the saving.
    cur.execute("""
        CREATE TEMP TABLE credit_ledger AS
        SELECT d.login, d.deal_time,
               SUM(CASE WHEN d.action IN (0,1,2) THEN COALESCE(d.profit,0) ELSE 0 END)
                   OVER (PARTITION BY d.login ORDER BY d.deal_time, d.id) AS run_cash,
               SUM(CASE WHEN d.action IN (3,6) THEN COALESCE(d.profit,0) ELSE 0 END)
                   OVER (PARTITION BY d.login ORDER BY d.deal_time, d.id) AS run_credit
        FROM deals d
        WHERE d.login IN (SELECT DISTINCT login FROM deals WHERE action IN (3,6))
          AND d.login IN (SELECT DISTINCT login FROM ib_trades)
    """)
    cur.execute("CREATE INDEX ix_credledg ON credit_ledger(login, deal_time)")
    cur.execute(f"""
        UPDATE ib_trades t
        SET eligible = FALSE, reason = 'credit', commission = 0
        WHERE t.login IN (SELECT DISTINCT login FROM credit_ledger)
          -- never touch a trade Plugit actually paid (respect the excel era); post-cutoff
          -- eligible trades are engine-era and correctly move to unpaid-credit
          AND (t.commission = 0 OR t.close_time > TIMESTAMP '{EXCEL_CUTOFF}' + INTERVAL '1 day')
          AND COALESCE((
              SELECT l.run_cash <= 0 AND l.run_credit > 0
              FROM credit_ledger l
              WHERE l.login = t.login
                AND l.deal_time <= EXTRACT(EPOCH FROM COALESCE(t.open_time, t.close_time))::bigint
              ORDER BY l.deal_time DESC LIMIT 1), FALSE)
    """)
    n_credit = cur.rowcount
    cur.execute("DROP TABLE credit_ledger")
    cn.commit()
    print(f"credit rule v2 (ledger, all-time): {n_credit:,} trades flagged as credit-funded")

    # ── SHORT (<5min) preservation, ALL-TIME ─────────────────────────────────────────────────
    # The build flags every <5-min trade, but the excel overlay wipes the 'short' reason for
    # pre-cutoff trades. Re-label the UNPAID ones (Plugit-paid short trades stay eligible/paid)
    # so the "Short < 5min" view and its engine-valued saving cover all history too.
    cur.execute("""
        UPDATE ib_trades
        SET reason = 'short(<5min)'
        WHERE hold_sec IS NOT NULL AND hold_sec < 300
          AND eligible = FALSE AND commission = 0
          AND reason IS DISTINCT FROM 'credit'
          AND reason IS DISTINCT FROM 'short(<5min)'
    """)
    n_short_relabel = cur.rowcount
    cn.commit()
    print(f"short(<5min) re-labelled (all-time, unpaid): {n_short_relabel:,}")

    # ── SELF / RELATED ACCOUNTS (anti-abuse) — FORWARD-ONLY, LEVEL 5/6 only ──────────────────
    # An IB must not farm commission on their OWN accounts or accounts 100%-related to them
    # (same person, or a decisive 10/10 device/family/wallet link — see ib_self_related.py). While
    # the IB is at level 5 or 6 these earn ZERO; at level 7+ they earn normally (proven IB). The
    # persistent ib_self_related table also drives the "self / related" badge in the IB portal.
    # FORWARD-ONLY (user, Jul 2026): only trades CLOSED on/after SELF_ZERO_START are zeroed —
    # commission already earned before go-live is kept (and L5 can't withdraw it until promoted to 6).
    import ib_self_related as ISR
    sr_total, sr_self, sr_rel = ISR.build(cur)
    cn.commit()
    cur.execute(f"""
        UPDATE ib_trades t
        SET eligible = FALSE, reason = 'self_related', commission = 0
        FROM ib_self_related s
        WHERE s.ib_id = t.ib_id AND s.login = t.login
          AND t.ib_level BETWEEN 5 AND 6
          AND t.eligible
          AND t.close_time >= TIMESTAMP '{ISR.SELF_ZERO_START}'
    """)
    n_self_related = cur.rowcount
    cn.commit()
    print(f"self/related accounts: {sr_total:,} (self {sr_self}, related {sr_rel}); "
          f"forward L5/6 trades zeroed: {n_self_related:,}")

    # recompute IB commission from ELIGIBLE trades only
    cur.execute("UPDATE ibs SET commission_new = 0")
    cur.execute("""UPDATE ibs ib SET commission_new = x.c
                   FROM (SELECT ib_id, SUM(commission) c FROM ib_trades WHERE eligible GROUP BY ib_id) x
                   WHERE ib.id = x.ib_id""")
    # LIVE COMMISSION for Plugit-backed IBs: the Excel is authoritative up to EXCEL_CUTOFF, but
    # commission must keep GROWING as their traders close new trades. Recompute the post-cutoff
    # part from the freshly rebuilt ib_trades every run (eligible trades only, rate model).
    # Aggregated onto the PRIMARY row per person: trades under the MT4 sibling agent land on the
    # hidden MT4 ibs row, so sum across the ext_ib_id group.
    cur.execute("UPDATE ibs SET commission_live = 0 WHERE commission_source IS NOT NULL")
    cur.execute(f"""UPDATE ibs SET commission_live = COALESCE(s.c,0)
                    FROM (SELECT COALESCE(i.ext_ib_id::text, i.id::text) AS grp, SUM(t.commission) AS c
                          FROM ib_trades t JOIN ibs i ON i.id = t.ib_id
                          WHERE t.eligible AND t.close_time > '{EXCEL_CUTOFF} 23:59:59'
                          GROUP BY 1) s
                    WHERE COALESCE(ibs.ext_ib_id::text, ibs.id::text) = s.grp
                      AND ibs.commission_source IS NOT NULL AND ibs.is_primary IS NOT FALSE""")
    # NEVER overwrite the authoritative Plugit commission (commission_source IS NOT NULL): those IBs
    # get excel(2023..cutoff) + computed(pre-2023) + live(post-cutoff). Only IBs with no Plugit data
    # get the full eligible-trade rollup. The enforce_ib_commission DB trigger applies the same rule.
    cur.execute("""UPDATE ibs SET
                   total_commission = CASE WHEN commission_source IS NOT NULL
                        THEN COALESCE(commission_excel,0)+COALESCE(commission_computed,0)+COALESCE(commission_live,0)
                        ELSE COALESCE(commission_new,0) END,
                   unpaid_commission = GREATEST((CASE WHEN commission_source IS NOT NULL
                        THEN COALESCE(commission_excel,0)+COALESCE(commission_computed,0)+COALESCE(commission_live,0)
                        ELSE COALESCE(commission_new,0) END)-COALESCE(paid_commission,0),0)""")
    cn.commit()
    # Floor LAST: wallet is commission-only, so no IB withdrew (total_payoff) more than it earned.
    cur.execute("""UPDATE ibs SET
                   commission_computed = COALESCE(commission_computed,0)+(COALESCE(total_payoff,0)-total_commission),
                   total_commission    = COALESCE(total_payoff,0),
                   commission_source   = COALESCE(commission_source,'computed'),
                   unpaid_commission   = GREATEST(COALESCE(total_payoff,0)-COALESCE(paid_commission,0),0)
                   WHERE COALESCE(total_payoff,0) > total_commission + 0.01""")
    cn.commit()

    print(f"\ntrades built: {n_trades:,}   short(<5min): {n_short:,}")
    print(f"commission WITHOUT 5-min rule: ${comm_all:,.2f}")
    print(f"commission WITH 5-min rule:    ${comm_eligible:,.2f}")
    print(f"SAVINGS from 5-min rule:       ${comm_all - comm_eligible:,.2f}")
    cur.execute("SELECT COUNT(*), ROUND(SUM(profit)::numeric,2) FROM ib_trades WHERE NOT eligible")
    print("short-trade rows:", cur.fetchone())
    # post-Plugit IB payouts made directly on the MT agent accounts (transfers/withdrawals
    # after the last Operation-Log excel) — mirrored into ib_operations so they DEDUCT
    try:
        import ib_mt_payoffs
        n_po = ib_mt_payoffs.capture(cn)
        if n_po:
            print(f"MT payout ops captured: {n_po}")
    except Exception as e:
        print(f"[ib_mt_payoffs] skipped: {e}")
    # auto-withdrawals (IBs who set an Ovadot threshold) — creates Pending payouts to approve
    try:
        from database import SessionLocal
        _db = SessionLocal()
        try:
            import ib_portal_extras
            n_aw = ib_portal_extras.run_auto_withdrawals(_db)
            if n_aw:
                print(f"auto-withdrawals created: {n_aw}")
        finally:
            _db.close()
    except Exception as e:
        print(f"[auto_withdraw] skipped: {e}")
    cn.close()


if __name__ == "__main__":
    main()
