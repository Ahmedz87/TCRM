"""
calc_ib_commission.py — compute every IB's commission under the NEW model.

For each IB (level 5-10) and each of their accounts' CLOSED trades:
    commission = lots × value × point-value(symbol)
where the (level, symbol) rule is resolved by the commission engine (lowest-priority match).

Strategy (fast over millions of deals):
  1. precompute a (ib_level, symbol) -> commission-per-lot rate table in Python
  2. aggregate over deals in ONE SQL pass joining deals -> account -> IB -> rate
  3. write per-IB totals to ib_commission_calc and ibs.commission_new

Re-runnable / idempotent.
"""
import psycopg2
from psycopg2.extras import execute_values
import ib_commission as IC

PG_DSN = IC.PG_DSN


def main():
    cn = psycopg2.connect(PG_DSN); cn.autocommit = False; cur = cn.cursor()

    # ── 1. point value (USD per point per lot) for every symbol, once ──
    cur.execute("SELECT symbol, point_value_profit, currency_profit FROM mt5_symbol_specs")
    point_usd = {sym: float(pvp or 0) * IC.CCY_USD.get(ccy or "USD", 1.0)
                 for sym, pvp, ccy in cur.fetchall()}
    print(f"{len(point_usd):,} symbol point-values loaded")

    # ── 2. build (level, symbol) -> commission-per-lot ──
    rate_rows = []
    for level in range(5, 11):                       # IB levels 5..10
        rules = IC.load_profile_rules(cur, level)
        if not rules:
            continue
        for sym, pu in point_usd.items():
            rule = IC.match_rule(rules, sym)
            if not rule:
                continue
            per_lot = rule["value"] if rule["distribution"] == "usd_per_lot" else rule["value"] * pu
            rate_rows.append((level, sym, per_lot, rule["name"]))

    cur.execute("DROP TABLE IF EXISTS commission_rates")
    cur.execute("""CREATE TABLE commission_rates (
        ib_level INT, symbol TEXT, comm_per_lot DOUBLE PRECISION, rule_name TEXT,
        PRIMARY KEY (ib_level, symbol))""")
    execute_values(cur, "INSERT INTO commission_rates (ib_level,symbol,comm_per_lot,rule_name) VALUES %s", rate_rows)
    cn.commit()
    print(f"{len(rate_rows):,} (level,symbol) rates built")

    # ── 3. aggregate per IB over all closed trades ──
    print("Aggregating commission over closed trades (this scans deals)...", flush=True)
    cur.execute("DROP TABLE IF EXISTS ib_commission_calc")
    cur.execute("""
        CREATE TABLE ib_commission_calc AS
        SELECT ib.id AS ib_id, ib.agent_id, ib.ib_level,
               COUNT(*) AS trades,
               SUM(d.volume/10000.0) AS lots,
               SUM((d.volume/10000.0) * r.comm_per_lot) AS commission_usd
        FROM deals d
        JOIN clients c ON c.login = d.login
        JOIN ibs ib   ON ib.agent_id = c.agent AND ib.ib_level BETWEEN 5 AND 10
        JOIN commission_rates r ON r.ib_level = ib.ib_level AND r.symbol = d.symbol
        WHERE d.entry = 1 AND d.action IN (0,1)
        GROUP BY ib.id, ib.agent_id, ib.ib_level
    """)
    cur.execute("CREATE INDEX ix_ibcomm_calc ON ib_commission_calc(ib_id)")
    cn.commit()

    # ── 4. write back onto ibs ──
    cur.execute("ALTER TABLE ibs ADD COLUMN IF NOT EXISTS commission_new DOUBLE PRECISION")
    cur.execute("UPDATE ibs SET commission_new = 0")
    cur.execute("UPDATE ibs ib SET commission_new = x.commission_usd FROM ib_commission_calc x WHERE x.ib_id = ib.id")
    cn.commit()

    # ── 5. report ──
    cur.execute("SELECT COUNT(*), ROUND(SUM(commission_usd)::numeric,2), SUM(trades) FROM ib_commission_calc")
    n, total, trades = cur.fetchone()
    print(f"\nIBs with commission: {n}   trades priced: {trades:,}   TOTAL new-model commission: ${total:,.2f}\n")
    cur.execute("SELECT ib_level, COUNT(*), ROUND(SUM(commission_usd)::numeric,2) FROM ib_commission_calc GROUP BY ib_level ORDER BY ib_level")
    print("By level:")
    for lvl, c, s in cur.fetchall():
        print(f"  L{lvl}: {c:>4} IBs   ${s:,.2f}")
    cur.execute("""SELECT x.agent_id, COALESCE(NULLIF(ib.name,''),'(no name)'), x.ib_level, x.trades, ROUND(x.commission_usd::numeric,2)
                   FROM ib_commission_calc x JOIN ibs ib ON ib.id=x.ib_id ORDER BY x.commission_usd DESC LIMIT 10""")
    print("\nTop 10 IBs by new commission:")
    for a, nm, lvl, t, s in cur.fetchall():
        print(f"  #{a:<10} {nm[:26]:26} L{lvl}  {t:>7,} trades   ${s:,.2f}")

    # coverage: closed trades under an IB whose symbol had no rate (e.g. MT4/delisted)
    cur.execute("""
        SELECT COUNT(*) FROM deals d
        JOIN clients c ON c.login=d.login
        JOIN ibs ib ON ib.agent_id=c.agent AND ib.ib_level BETWEEN 5 AND 10
        LEFT JOIN commission_rates r ON r.ib_level=ib.ib_level AND r.symbol=d.symbol
        WHERE d.entry=1 AND d.action IN (0,1) AND r.symbol IS NULL
    """)
    print(f"\nUnpriced closed trades (symbol not in MT5 specs, e.g. MT4): {cur.fetchone()[0]:,}")
    cn.close()


if __name__ == "__main__":
    main()
