"""
build_ibs.py — populate the `ibs` table from the live MT data.

An IB is identified by clients.agent (the MT agent/IB account number). The IB is
themselves a trading account, so name/contact/group come from the clients row whose
login = that agent.

  ib_level   : parsed from the IB account group name (IB\\IB-5 / TNFX-IB-5 -> 5). 5..10.
  net_deposits: deposits - withdrawals of referred clients (from the real transactions).
  total_volume: lots traded by referred clients (deals.volume / 10000).
  total_commission: SUM(lots * points), where points = ib_level for FX + gold (XAU*),
                    and 1 point for everything else.

Idempotent (upsert on agent_id). Run:  python build_ibs.py
"""
import psycopg2
import db_config

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# FX = a 6-letter pair of currency codes (after stripping dots/suffixes); gold = XAU*.
_CUR = "USD|EUR|GBP|JPY|AUD|NZD|CAD|CHF|TRY|ZAR|MXN|SGD|HKD|NOK|SEK|DKK|PLN|CNH|CZK|HUF|RUB|INR|THB|CNY"
FX_OR_GOLD = (
    "(d.symbol ILIKE 'XAU%' OR upper(regexp_replace(d.symbol,'[^A-Za-z]','','g')) "
    f"~ '^({_CUR})({_CUR})')"
)

INSERT_SQL = """
INSERT INTO ibs (agent_id, ib_code, name, email, phone, country, city, group_name, status,
                 ib_level, total_clients, active_clients, net_deposits,
                 unpaid_commission, paid_commission, total_commission, total_volume,
                 created_at, updated_at)
SELECT
    a.agent,
    'IB' || a.agent::text,
    COALESCE(NULLIF(trim(ib.name), ''), 'IB #' || a.agent::text),
    ib.email, ib.phone, ib.country, ib.city, ib.group_name,
    'active',
    COALESCE((regexp_match(COALESCE(ib.group_name,''), 'IB[-\\\\]?[A-Za-z]*-?([0-9]+)'))[1]::int, 5),
    a.total_clients, a.active_clients,
    COALESCE(dep.net_dep, 0),
    0, 0, 0, 0,
    NOW(), NOW()
FROM (
    SELECT agent,
           COUNT(*)                                          AS total_clients,
           COUNT(*) FILTER (WHERE COALESCE(is_active,FALSE)) AS active_clients
    FROM clients WHERE COALESCE(agent,0) <> 0 GROUP BY agent
) a
LEFT JOIN clients ib ON ib.login = a.agent
LEFT JOIN (
    SELECT c.agent,
           SUM(CASE WHEN t.tx_type='deposit' THEN t.amount
                    WHEN t.tx_type='withdrawal' THEN -t.amount ELSE 0 END) AS net_dep
    FROM transactions t JOIN clients c ON c.login = t.login
    WHERE COALESCE(c.agent,0) <> 0 GROUP BY c.agent
) dep ON dep.agent = a.agent
ON CONFLICT (agent_id) DO UPDATE SET
    name           = EXCLUDED.name,
    email          = COALESCE(EXCLUDED.email, ibs.email),
    phone          = COALESCE(EXCLUDED.phone, ibs.phone),
    country        = COALESCE(EXCLUDED.country, ibs.country),
    city           = COALESCE(EXCLUDED.city, ibs.city),
    group_name     = EXCLUDED.group_name,
    ib_level       = EXCLUDED.ib_level,
    total_clients  = EXCLUDED.total_clients,
    active_clients = EXCLUDED.active_clients,
    net_deposits   = EXCLUDED.net_deposits,
    updated_at     = NOW()
"""

VOLUME_SQL = f"""
UPDATE ibs SET
    total_volume     = sub.lots,
    total_commission = sub.commission,
    unpaid_commission = sub.commission - COALESCE(ibs.paid_commission,0),
    updated_at = NOW()
FROM (
    SELECT c.agent,
           SUM(CASE WHEN {FX_OR_GOLD} THEN d.volume/10000.0 ELSE 0 END) AS lots,
           SUM((d.volume/10000.0) * CASE WHEN {FX_OR_GOLD} THEN i.ib_level ELSE 1 END) AS commission
    FROM deals d
    JOIN clients c ON c.login = d.login
    JOIN ibs i ON i.agent_id = c.agent
    WHERE d.action IN (0,1) AND d.volume > 0
    GROUP BY c.agent
) sub
WHERE ibs.agent_id = sub.agent
"""


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ibs_agent_id_uq ON ibs(agent_id)")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM ibs"); before = cur.fetchone()[0]
    cur.execute(INSERT_SQL); conn.commit()
    cur.execute("SELECT COUNT(*) FROM ibs"); after = cur.fetchone()[0]
    print(f"IBs upserted:  {before} -> {after}")

    print("Computing volume + commission from deals (this scans the trade history)...")
    cur.execute(VOLUME_SQL); conn.commit()

    cur.execute("""SELECT name, ib_level, total_clients, round(total_volume::numeric,1),
                          round(total_commission::numeric,2)
                   FROM ibs ORDER BY total_clients DESC LIMIT 10""")
    print(f"\n{'IB':<30} {'lvl':>3} {'clients':>7} {'lots':>12} {'commission':>12}")
    for n, lv, tc, vol, comm in cur.fetchall():
        print(f"   {str(n)[:28]:<28} {lv:>3} {tc:>7} {float(vol or 0):>12,.1f} {float(comm or 0):>12,.0f}")
    cur.execute("SELECT ib_level, count(*) FROM ibs GROUP BY ib_level ORDER BY ib_level")
    print("\nIB level distribution:", cur.fetchall())
    conn.close()


if __name__ == "__main__":
    main()
