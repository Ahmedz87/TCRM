# -*- coding: utf-8 -*-
"""Precomputed per-symbol deals rollup for the Markup page.

The /markups/others + /markups/crosscheck endpoints each did a FULL GROUP-BY over the
16.8M-row deals table on every page open (~5s + ~1.5s, uncached) — the single worst page
in the CRM. These all-time totals move slowly, so we roll them up once into a tiny table
(a few hundred rows, one per raw symbol) and refresh it every ~15 min in the background.
Both endpoints then read this table instantly.

Refreshed by: enrich_loop (15-min cadence) + on first use if the table is empty/stale.
Rebuild standalone: python markup_agg.py
"""
import db_config

DDL = """
CREATE TABLE IF NOT EXISTS deals_symbol_agg (
  symbol      TEXT PRIMARY KEY,
  lots        DOUBLE PRECISION,
  markup_usd  DOUBLE PRECISION,
  trades      BIGINT,
  refreshed_at TIMESTAMP DEFAULT NOW()
)"""

REBUILD = """
WITH agg AS (
  SELECT d.symbol AS symbol,
         COALESCE(SUM(d.volume),0)/10000.0        AS lots,
         COALESCE(SUM(d.markup_profit),0)/10000.0 AS markup_usd,
         COUNT(*)                                  AS trades
  FROM deals d
  WHERE d.action IN (0,1) AND d.volume > 0 AND COALESCE(d.symbol,'') <> ''
  GROUP BY d.symbol
)
INSERT INTO deals_symbol_agg (symbol, lots, markup_usd, trades, refreshed_at)
SELECT symbol, lots, markup_usd, trades, NOW() FROM agg
ON CONFLICT (symbol) DO UPDATE
  SET lots=EXCLUDED.lots, markup_usd=EXCLUDED.markup_usd,
      trades=EXCLUDED.trades, refreshed_at=NOW()
"""


# Per-(login, day) markup rollup — powers the Sales Agents page. The /agents commission
# CTE joined clients->deals (16.8M rows) grouped by agent = ~39s cold. This pre-aggregates
# to ~483k rows (login,day); the agent query then sums a date-indexed rollup = sub-second.
DDL_LOGIN = """
CREATE TABLE IF NOT EXISTS deals_login_daily (
  login        BIGINT,
  day          TEXT,
  markup_usd   DOUBLE PRECISION,   -- all trades (company view)
  markup_nc    DOUBLE PRECISION,   -- credit-adjustment deals excluded (commission basis)
  lots         DOUBLE PRECISION,
  trades       BIGINT,
  PRIMARY KEY (login, day)
)"""
IDX_LOGIN = "CREATE INDEX IF NOT EXISTS ix_dld_day ON deals_login_daily(day)"
# markup_nc excludes 'credit' adjustment deals (ib_trades.reason='credit') to match the
# commission engine's CREDIT_EXCLUDE; markup_usd keeps them for the company-markup column.
REBUILD_LOGIN = """
INSERT INTO deals_login_daily (login, day, markup_usd, markup_nc, lots, trades)
SELECT d.login, substr(d.deal_date,1,10) AS day,
       COALESCE(SUM(d.markup_profit),0)/10000.0,
       COALESCE(SUM(d.markup_profit) FILTER (WHERE cr.deal_id IS NULL),0)/10000.0,
       COALESCE(SUM(d.volume),0)/10000.0,
       COUNT(*)
FROM deals d
LEFT JOIN ib_trades cr ON cr.deal_id = d.deal_id AND cr.reason = 'credit'
WHERE d.action IN (0,1) AND COALESCE(d.deal_date,'') <> '' AND d.login IS NOT NULL
GROUP BY d.login, substr(d.deal_date,1,10)
ON CONFLICT (login, day) DO UPDATE
  SET markup_usd=EXCLUDED.markup_usd, markup_nc=EXCLUDED.markup_nc,
      lots=EXCLUDED.lots, trades=EXCLUDED.trades
"""


def refresh(conn=None):
    """Recompute both deals rollups (symbol + login/day). Full deals scan (~5-10s), run in
    the background every ~15 min. Idempotent upsert. Accepts a conn or opens its own."""
    own = conn is None
    c = conn or db_config.connect()
    try:
        c.autocommit = True
        cur = c.cursor()
        cur.execute(DDL)
        cur.execute(REBUILD)
        n = cur.rowcount
        cur.execute("DELETE FROM deals_symbol_agg WHERE refreshed_at < NOW() - INTERVAL '1 hour'")
        cur.execute(DDL_LOGIN)
        cur.execute("ALTER TABLE deals_login_daily ADD COLUMN IF NOT EXISTS markup_nc DOUBLE PRECISION")
        cur.execute(IDX_LOGIN)
        cur.execute(REBUILD_LOGIN)
        return n
    finally:
        if own:
            c.close()


def is_stale(db, minutes=20):
    """True if the table is missing/empty or older than `minutes` (SQLAlchemy session)."""
    from sqlalchemy import text
    try:
        r = db.execute(text("SELECT max(refreshed_at) FROM deals_symbol_agg")).scalar()
        if r is None:
            return True
        age = db.execute(text("SELECT extract(epoch FROM now()-:t)/60"), {"t": r}).scalar()
        return (age or 999) > minutes
    except Exception:
        return True


if __name__ == "__main__":
    import time
    t0 = time.time()
    n = refresh()
    print(f"deals_symbol_agg refreshed: {n} symbols in {time.time()-t0:.1f}s")
