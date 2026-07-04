"""
mt5_symbol_specs.py — pull every MT5 symbol's contract spec so we can convert a commission
"pip/point value" into money.  point_value (in profit currency) = ContractSize * Point.

Stores into table mt5_symbol_specs. RUN ONLY WHILE bridge.py IS STOPPED (one mgr conn/login).
Read-only against MT5; writes only to its own spec table.
"""
import MT5Manager as M
import db_config
import psycopg2
from psycopg2.extras import execute_values

SERVER = "192.109.15.62:443"
LOGIN  = 1025
PASS   = "ZjFb!vA0"
PG_DSN = db_config.DSN


def enumerate_symbols(mgr):
    """Return a list of MTConSymbol objects, trying the available API shapes."""
    # SymbolGetArray() returns everything at once
    try:
        arr = mgr.SymbolGetArray()
        if arr:
            return list(arr)
    except Exception as e:
        print("  SymbolGetArray failed:", e)
    # total / next / get
    try:
        total = mgr.SymbolTotal()
        if total and total > 0:
            out = []
            for i in range(total):
                name = mgr.SymbolNext(i)
                if not name:
                    continue
                s = mgr.SymbolGet(name)
                if s:
                    out.append(s)
            if out:
                return out
    except Exception as e:
        print("  total/next path failed:", e)
    return []


def main():
    print("Connecting MT5", SERVER, "...", flush=True)
    mgr = M.ManagerAPI()
    if not mgr.Connect(SERVER, LOGIN, PASS):
        print("CONNECT FAILED"); return
    print("  connected", flush=True)

    syms = enumerate_symbols(mgr)
    print(f"  {len(syms)} symbols", flush=True)
    if not syms:
        mgr.Disconnect(); print("no symbols enumerated"); return

    # discover field names on the first object
    first = syms[0]
    attrs = [a for a in dir(first) if not a.startswith("_")]
    print("\nsymbol object attributes:\n ", attrs, "\n")

    def g(o, *names, default=None):
        for n in names:
            v = getattr(o, n, None)
            if v is not None:
                return v
        return default

    rows = []
    for s in syms:
        name = g(s, "Symbol", "Name", default="")
        if not name:
            continue
        digits   = int(g(s, "Digits", default=0) or 0)
        point    = float(g(s, "Point", default=(10 ** (-digits) if digits else 0)) or 0)
        if not point and digits:
            point = 10 ** (-digits)
        contract = float(g(s, "ContractSize", "ContractSizeStandard", default=0) or 0)
        cprofit  = g(s, "CurrencyProfit", "CurrencyBase", default="")
        cmargin  = g(s, "CurrencyMargin", default="")
        ticksize = float(g(s, "TickSize", default=0) or 0)
        tickval  = float(g(s, "TickValue", default=0) or 0)
        path     = g(s, "Path", "PathJson", default="")
        pv_profit = contract * point  # point value in profit currency, per 1.00 lot
        rows.append((name, digits, point, contract, cprofit, cmargin, ticksize, tickval, pv_profit, str(path)[:200]))

    cn = psycopg2.connect(PG_DSN); cn.autocommit = False; cur = cn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mt5_symbol_specs (
            symbol            TEXT PRIMARY KEY,
            digits            INT,
            point             DOUBLE PRECISION,
            contract_size     DOUBLE PRECISION,
            currency_profit   TEXT,
            currency_margin   TEXT,
            tick_size         DOUBLE PRECISION,
            tick_value        DOUBLE PRECISION,
            point_value_profit DOUBLE PRECISION,   -- contract_size * point (in profit ccy)
            path              TEXT
        )""")
    cur.execute("TRUNCATE mt5_symbol_specs")
    execute_values(cur, """INSERT INTO mt5_symbol_specs
        (symbol,digits,point,contract_size,currency_profit,currency_margin,tick_size,tick_value,point_value_profit,path)
        VALUES %s""", rows)
    cn.commit()
    mgr.Disconnect()

    # quick report
    print(f"\nstored {len(rows)} symbol specs.")
    print("\nsamples:")
    cur.execute("""SELECT symbol,digits,point,contract_size,currency_profit,point_value_profit
                   FROM mt5_symbol_specs
                   WHERE symbol IN ('EURUSD','XAUUSD','XAGUSD','DJ30','USOIL','BTCUSD','DOGUSD','TRPUSD')
                   ORDER BY symbol""")
    for r in cur.fetchall():
        print(f"  {r[0]:10} dig={r[1]} point={r[2]} contract={r[3]} ccy={r[4]} point$={r[5]}")
    cur.execute("SELECT COUNT(*) FROM mt5_symbol_specs WHERE symbol LIKE '%.z'")
    print(f"\nsymbols ending '.z' (Zero): {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(DISTINCT currency_profit) , string_agg(DISTINCT currency_profit, ',') FROM mt5_symbol_specs")
    n, ccys = cur.fetchone()
    print(f"profit currencies ({n}): {ccys}")
    cn.close()
    print("done.")


if __name__ == "__main__":
    main()
