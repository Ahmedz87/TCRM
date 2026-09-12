"""
loss_pattern_analysis.py — Tier-A client loss-pattern analysis on REAL data.

Implements the sections of the "Client Loss Pattern Discovery" spec that are
computable from the data the CRM already stores (see the feasibility audit):

    12. Cost-driven losses            <- the headline section
     9. Overtrading and revenge
    15. Strategy drift and randomness
    16. Linked accounts / copy behavior
  plus the reduced forms of:
     1. Directional accuracy and expectancy
     4. Position-size change after wins/losses
    10. Session / hour / day effects
    17. Deposit / withdrawal behavior

Everything the spec asks for that needs price history, SL/TP, or intraday margin
is NOT here — it is not computable until those streams are captured.

METHODOLOGY GUARDS (audit findings F-1..F-3) are applied throughout:
  F-1  client-level stats are reported per PERSON (phone+platform), not per login,
       with an independent-person count, a person-blocked bootstrap CI, and a
       re-run after dropping the top 1% of accounts by volume.
  F-2  bonus/credit-funded accounts (deals.action IN (3,6)) are identified and
       reported separately — losing bonus money is not an economic client loss.
  F-3  MT4 and MT5 are never pooled. MT4 came from journal parsing and sets no
       `entry` flag; MT5 arrives via the bridge with entry 0=open / 1=close.

READ-ONLY. Opens a read-only, autocommit session (so a failed query can never
poison the rest of the run — see the rollback lesson in CLAUDE.md) and issues no
INSERT/UPDATE/DDL of any kind. Safe to run against the live box.

Run on the CRM box (it is the only host the DB firewall admits):
    cd C:\\broker-crm\\backend
    .\\venv\\Scripts\\Activate.ps1
    python loss_pattern_analysis.py                 # full run, writes JSON + report
    python loss_pattern_analysis.py --probe-only    # just the data-shape preamble
    python loss_pattern_analysis.py --since 2025-01-01
    python loss_pattern_analysis.py --out C:\\temp\\lpa

Expect ~3-6 minutes: several single-pass aggregates over ~4M `deals` rows.
"""
import argparse
import json
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict

import psycopg2
import psycopg2.extras

import db_config

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME,
          user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# Statement ceiling so a bad plan can never sit on the production box.
STATEMENT_TIMEOUT_MS = 600_000

# ── data conventions (verified against models.py + the sync scripts) ──────────
# deals.action        0 buy | 1 sell | 2 balance (deposit/withdrawal) | 3 credit | 6 bonus
# deals.entry         0 open | 1 close | 2 reverse   (MT5 only; MT4 journal rows leave it NULL)
# deals.volume        lots * 10000
# deals.markup_profit broker markup, USD * 10000
# deals.profit/commission/swap   raw USD (abuse_engine compares SUM(profit) <= -300)
LOTS = "(d.volume / 10000.0)"
MARKUP = "(d.markup_profit / 10000.0)"
PLAT = "COALESCE(NULLIF(d.platform, ''), 'MT5')"

# A realized (closed) trade. MT5 marks the close with entry=1; MT4 journal rows are
# close-only and carry no entry flag, so they are counted once via entry IS NULL.
CLOSES = ("d.action IN (0,1) AND ("
          "d.entry = 1 OR (COALESCE(NULLIF(d.platform,''),'MT5') = 'MT4' AND d.entry IS NULL))")
OPENS = "d.action IN (0,1) AND d.entry = 0"


# ══════════════════════════════════════════════════════════════════════════
# plumbing
# ══════════════════════════════════════════════════════════════════════════

def connect():
    conn = psycopg2.connect(**DB)
    # read-only + autocommit: no write is possible, and a failed statement cannot
    # leave an aborted transaction behind to poison later queries.
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (STATEMENT_TIMEOUT_MS,))
    return conn


def q(conn, sql, params=None, label=""):
    """Run one read query. Returns list of dicts, or [] if it fails (and says so)."""
    t0 = time.time()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            rows = [dict(r) for r in cur.fetchall()]
        if label:
            print(f"    {label}: {len(rows)} rows in {time.time()-t0:.1f}s")
        return rows
    except Exception as e:
        print(f"    !! {label or 'query'} FAILED: {type(e).__name__}: {e}")
        return []


def f(x, nd=2):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else round(v, nd)


def date_clause(since, until, alias="d"):
    """deal_date is a STRING 'YYYY-MM-DD'; string ranges are the repo convention."""
    parts, params = [], []
    if since:
        parts.append(f"{alias}.deal_date >= %s")
        params.append(since)
    if until:
        parts.append(f"{alias}.deal_date <= %s")
        params.append(until)
    return ((" AND " + " AND ".join(parts)) if parts else ""), params


# ══════════════════════════════════════════════════════════════════════════
# 0. data shape — always run first; every later number is read against this
# ══════════════════════════════════════════════════════════════════════════

def probe(conn, since, until):
    print("\n[0] DATA SHAPE")
    dc, dp = date_clause(since, until)
    out = {}

    out["by_platform_entry"] = q(conn, f"""
        SELECT {PLAT} AS platform, d.entry, COUNT(*) AS deals,
               COUNT(DISTINCT d.login) AS logins,
               MIN(d.deal_date) AS first_date, MAX(d.deal_date) AS last_date
        FROM deals d
        WHERE d.action IN (0,1) {dc}
        GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "platform x entry")

    out["action_mix"] = q(conn, f"""
        SELECT d.action, COUNT(*) AS deals, COUNT(DISTINCT d.login) AS logins,
               ROUND(SUM(d.profit)::numeric, 2) AS sum_profit
        FROM deals d WHERE TRUE {dc}
        GROUP BY 1 ORDER BY 1
    """, dp, "action mix")

    # F-2: how much of the book is bonus/credit funded.
    out["bonus_credit_accounts"] = q(conn, f"""
        SELECT {PLAT} AS platform,
               COUNT(DISTINCT d.login) AS logins_with_bonus_or_credit,
               ROUND(SUM(GREATEST(d.profit, 0))::numeric, 2) AS bonus_credit_in
        FROM deals d WHERE d.action IN (3,6) {dc}
        GROUP BY 1 ORDER BY 1
    """, dp, "bonus/credit exposure")

    # Sign convention for costs — read this before trusting section 1.
    out["cost_signs"] = q(conn, f"""
        SELECT {PLAT} AS platform,
               ROUND(AVG(d.commission)::numeric, 4) AS avg_commission,
               ROUND(AVG(d.swap)::numeric, 4)       AS avg_swap,
               COUNT(*) FILTER (WHERE d.commission < 0) AS neg_commission_rows,
               COUNT(*) FILTER (WHERE d.commission > 0) AS pos_commission_rows,
               COUNT(*) FILTER (WHERE d.swap <> 0)      AS nonzero_swap_rows,
               COUNT(*) AS closes
        FROM deals d WHERE {CLOSES} {dc}
        GROUP BY 1 ORDER BY 1
    """, dp, "cost sign convention")

    for r in out["by_platform_entry"]:
        print(f"      {r['platform']:4s} entry={str(r['entry']):4s} "
              f"{r['deals']:>9,} deals  {r['logins']:>6,} logins  "
              f"{r['first_date']} -> {r['last_date']}")
    for r in out["cost_signs"]:
        print(f"      {r['platform']:4s} avg commission {r['avg_commission']}  "
              f"avg swap {r['avg_swap']}  ({r['neg_commission_rows']:,} neg / "
              f"{r['pos_commission_rows']:,} pos rows)")
    return out


# ══════════════════════════════════════════════════════════════════════════
# 1. per-account ledger — pulled ONCE, then reused in Python
# ══════════════════════════════════════════════════════════════════════════

def account_ledger(conn, since, until):
    """One row per trading login: realized gross P&L, costs, net, lots, markup,
    bonus/credit flag, and the person key (phone+platform) for F-1."""
    print("\n[1] PER-ACCOUNT LEDGER")
    dc, dp = date_clause(since, until)
    rows = q(conn, f"""
        WITH tr AS (
            SELECT d.login,
                   {PLAT}                          AS platform,
                   COUNT(*)                        AS closes,
                   SUM(d.profit)                   AS gross,
                   SUM(d.commission)               AS commission,
                   SUM(d.swap)                     AS swap,
                   SUM({LOTS})                     AS lots,
                   SUM({MARKUP})                   AS markup,
                   SUM(CASE WHEN d.profit > 0 THEN 1 ELSE 0 END) AS wins,
                   MIN(d.deal_date)                AS first_trade,
                   MAX(d.deal_date)                AS last_trade
            FROM deals d
            WHERE {CLOSES} {dc}
            GROUP BY 1, 2
        ),
        bc AS (
            SELECT d.login, SUM(GREATEST(d.profit, 0)) AS bonus_credit_in
            FROM deals d WHERE d.action IN (3,6) {dc}
            GROUP BY 1
        ),
        mv AS (
            SELECT d.login,
                   SUM(CASE WHEN d.profit > 0 THEN d.profit ELSE 0 END) AS deposits,
                   SUM(CASE WHEN d.profit < 0 THEN -d.profit ELSE 0 END) AS withdrawals
            FROM deals d WHERE d.action = 2 {dc}
            GROUP BY 1
        )
        SELECT tr.*,
               COALESCE(bc.bonus_credit_in, 0) AS bonus_credit_in,
               COALESCE(mv.deposits, 0)        AS deposits,
               COALESCE(mv.withdrawals, 0)     AS withdrawals,
               c.phone,
               COALESCE(NULLIF(c.platform, ''), 'MT5') AS client_platform
        FROM tr
        LEFT JOIN bc ON bc.login = tr.login
        LEFT JOIN mv ON mv.login = tr.login
        LEFT JOIN clients c ON c.login = tr.login
    """, dp + dp + dp, "account ledger")

    for r in rows:
        r["gross"] = float(r["gross"] or 0)
        r["commission"] = float(r["commission"] or 0)
        r["swap"] = float(r["swap"] or 0)
        r["lots"] = float(r["lots"] or 0)
        r["markup"] = float(r["markup"] or 0)
        r["bonus_credit_in"] = float(r["bonus_credit_in"] or 0)
        # commission/swap are stored signed (normally negative); costs are the
        # magnitude, net is gross plus the signed values.
        r["costs"] = abs(r["commission"]) + abs(r["swap"])
        r["net"] = r["gross"] + r["commission"] + r["swap"]
        r["has_bonus"] = r["bonus_credit_in"] > 0
        # F-1: identity is phone+platform, matching the Clients list aggregation.
        ph = (r.get("phone") or "").strip()
        r["person"] = f"{ph}|{r['client_platform']}" if ph else f"login:{r['login']}"
    print(f"    {len(rows):,} trading accounts")
    return rows


# ══════════════════════════════════════════════════════════════════════════
# section 12 — cost-driven losses (the headline)
# ══════════════════════════════════════════════════════════════════════════

def persons_from(ledger, drop_top_pct=0.0):
    """Roll accounts up to persons (F-1). drop_top_pct trims the largest accounts
    by lots before rolling up (the F-1 robustness re-run)."""
    accts = ledger
    if drop_top_pct > 0 and accts:
        cut = sorted((a["lots"] for a in accts), reverse=True)
        k = max(1, int(len(cut) * drop_top_pct / 100.0))
        thresh = cut[k - 1]
        accts = [a for a in accts if a["lots"] < thresh]
    agg = defaultdict(lambda: dict(gross=0.0, costs=0.0, net=0.0, lots=0.0,
                                   markup=0.0, closes=0, wins=0, has_bonus=False,
                                   platforms=set()))
    for a in accts:
        p = agg[a["person"]]
        for k in ("gross", "costs", "net", "lots", "markup"):
            p[k] += a[k]
        p["closes"] += int(a["closes"] or 0)
        p["wins"] += int(a["wins"] or 0)
        p["has_bonus"] = p["has_bonus"] or a["has_bonus"]
        p["platforms"].add(a["platform"])
    for p in agg.values():
        p["platforms"] = sorted(p["platforms"])
    return agg


def cost_burden(persons, label):
    """Cost Burden Ratio + Gross-to-Net Conversion + the number that matters:
    how many people were gross-profitable but net-negative purely on costs."""
    traded = [p for p in persons.values() if p["closes"] > 0]
    if not traded:
        return None
    gross = sum(p["gross"] for p in traded)
    costs = sum(p["costs"] for p in traded)
    net = sum(p["net"] for p in traded)
    churn = sum(abs(p["gross"]) for p in traded)
    flipped = [p for p in traded if p["gross"] > 0 > p["net"]]
    return {
        "label": label,
        "persons": len(traded),
        "gross_pnl": f(gross),
        "total_costs": f(costs),
        "net_pnl": f(net),
        "broker_markup_revenue": f(sum(p["markup"] for p in traded)),
        "total_lots": f(sum(p["lots"] for p in traded)),
        # costs as a share of gross P&L churn
        "cost_burden_ratio": f(costs / churn, 4) if churn else None,
        "gross_to_net_conversion": f(net / gross, 4) if gross else None,
        "persons_gross_positive": sum(1 for p in traded if p["gross"] > 0),
        "persons_net_positive": sum(1 for p in traded if p["net"] > 0),
        "persons_flipped_by_costs": len(flipped),
        "pct_flipped_by_costs": f(100.0 * len(flipped) / len(traded), 2),
        "cost_flipped_value": f(sum(p["gross"] for p in flipped)),
    }


def bootstrap_flip_rate(persons, n=2000, seed=42):
    """F-1: person-blocked bootstrap CI on the flip rate. Resampling PERSONS (not
    trades) is what keeps the interval honest — the same client's trades are not
    independent observations."""
    traded = [p for p in persons.values() if p["closes"] > 0]
    if len(traded) < 30:
        return None
    flags = [1 if (p["gross"] > 0 > p["net"]) else 0 for p in traded]
    rng = random.Random(seed)
    N = len(flags)
    reps = []
    for _ in range(n):
        s = sum(flags[rng.randrange(N)] for _ in range(N))
        reps.append(100.0 * s / N)
    reps.sort()
    return {
        "point": f(100.0 * sum(flags) / N, 2),
        "ci95_low": f(reps[int(0.025 * n)], 2),
        "ci95_high": f(reps[int(0.975 * n)], 2),
        "resamples": n,
        "unit": "persons (block bootstrap)",
    }


def section_costs(conn, ledger, since, until):
    print("\n[12] COST-DRIVEN LOSSES")
    dc, dp = date_clause(since, until)
    res = {}

    # F-3: never pool platforms. F-2: bonus-funded reported apart.
    res["book"] = cost_burden(persons_from(ledger), "all persons")
    for plat in ("MT5", "MT4"):
        sub = [a for a in ledger if a["platform"] == plat]
        if sub:
            res[f"platform_{plat}"] = cost_burden(persons_from(sub), f"{plat} only")
    clean = [a for a in ledger if not a["has_bonus"]]
    if clean:
        res["excl_bonus_credit"] = cost_burden(persons_from(clean),
                                               "no bonus/credit funding")
    bonus = [a for a in ledger if a["has_bonus"]]
    if bonus:
        res["only_bonus_credit"] = cost_burden(persons_from(bonus),
                                               "bonus/credit funded")

    # F-1 robustness: drop the largest 1% of accounts by volume.
    res["excl_top1pct_volume"] = cost_burden(persons_from(ledger, drop_top_pct=1.0),
                                             "excl. top 1% accounts by lots")
    res["flip_rate_bootstrap"] = bootstrap_flip_rate(persons_from(ledger))

    res["by_symbol_category"] = q(conn, f"""
        SELECT {PLAT} AS platform,
               COALESCE(NULLIF(d.symbol_category, ''), 'unknown') AS category,
               COUNT(*) AS closes, COUNT(DISTINCT d.login) AS logins,
               ROUND(SUM(d.profit)::numeric, 2)                      AS gross,
               ROUND(SUM(ABS(d.commission) + ABS(d.swap))::numeric, 2) AS costs,
               ROUND(SUM(d.profit + d.commission + d.swap)::numeric, 2) AS net,
               ROUND(SUM({LOTS})::numeric, 2)                        AS lots,
               ROUND(SUM({MARKUP})::numeric, 2)                      AS markup
        FROM deals d WHERE {CLOSES} {dc}
        GROUP BY 1, 2 HAVING COUNT(*) >= 50
        ORDER BY 1, net
    """, dp, "cost burden by symbol category")

    b = res.get("book")
    if b:
        print(f"      persons traded          {b['persons']:,}")
        print(f"      gross P&L               {b['gross_pnl']:,}")
        print(f"      costs (comm+swap)       {b['total_costs']:,}")
        print(f"      net P&L                 {b['net_pnl']:,}")
        print(f"      cost burden ratio       {b['cost_burden_ratio']}")
        print(f"      gross->net conversion   {b['gross_to_net_conversion']}")
        print(f"      flipped by costs        {b['persons_flipped_by_costs']:,} "
              f"({b['pct_flipped_by_costs']}% of traders)")
    return res


# ══════════════════════════════════════════════════════════════════════════
# section 9 + 4 — overtrading, revenge, size change after win/loss
# ══════════════════════════════════════════════════════════════════════════

def section_overtrading(conn, since, until):
    print("\n[9] OVERTRADING AND REVENGE  /  [4] SIZE AFTER WIN-LOSS")
    dc, dp = date_clause(since, until)
    res = {}

    # Expectancy by trade number within the client's day — the spec's
    # "expectancy by trade number in the day", one window pass.
    res["expectancy_by_trade_number_in_day"] = q(conn, f"""
        WITH c AS (
            SELECT {PLAT} AS platform, d.profit,
                   ROW_NUMBER() OVER (PARTITION BY d.login, d.deal_date
                                      ORDER BY d.deal_time) AS rn
            FROM deals d WHERE {CLOSES} {dc}
        )
        SELECT platform, LEAST(rn, 21) AS trade_no_bucket,
               COUNT(*) AS closes,
               ROUND(AVG(profit)::numeric, 2) AS expectancy,
               ROUND(SUM(profit)::numeric, 2) AS total_pnl,
               ROUND(AVG(CASE WHEN profit > 0 THEN 1.0 ELSE 0 END)::numeric, 4) AS win_rate
        FROM c GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "expectancy by trade # in day")

    # Revenge + sizing in one pass: what the NEXT trade looks like after a
    # loss vs after a win.
    res["after_loss_vs_after_win"] = q(conn, f"""
        WITH c AS (
            SELECT {PLAT} AS platform, d.login, d.deal_time, d.profit, {LOTS} AS lots,
                   LAG(d.profit)   OVER w AS prev_profit,
                   LAG({LOTS})     OVER w AS prev_lots,
                   LAG(d.deal_time) OVER w AS prev_time
            FROM deals d WHERE {CLOSES} {dc}
            WINDOW w AS (PARTITION BY d.login ORDER BY d.deal_time)
        )
        SELECT platform,
               CASE WHEN prev_profit < 0 THEN 'after_loss' ELSE 'after_win' END AS state,
               COUNT(*) AS n,
               ROUND(AVG(deal_time - prev_time)::numeric, 1)             AS avg_gap_seconds,
               ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
                      (ORDER BY (deal_time - prev_time)::float))::numeric, 1) AS median_gap_seconds,
               COUNT(*) FILTER (WHERE deal_time - prev_time <= 60)       AS reentry_under_60s,
               ROUND(AVG(lots / NULLIF(prev_lots, 0))::numeric, 4)       AS avg_size_ratio,
               ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
                      (ORDER BY lots / NULLIF(prev_lots, 0)))::numeric, 4) AS median_size_ratio,
               ROUND(AVG(profit)::numeric, 2)                            AS next_trade_expectancy
        FROM c
        WHERE prev_profit IS NOT NULL AND prev_time IS NOT NULL
          AND deal_time >= prev_time
        GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "after-loss vs after-win")

    # Trades per day, and whether heavy days pay.
    res["intensity_vs_expectancy"] = q(conn, f"""
        WITH pd AS (
            SELECT {PLAT} AS platform, d.login, d.deal_date,
                   COUNT(*) AS trades, SUM(d.profit) AS pnl
            FROM deals d WHERE {CLOSES} {dc}
            GROUP BY 1, 2, 3
        )
        SELECT platform,
               CASE WHEN trades = 1 THEN '01'
                    WHEN trades <= 3 THEN '02-03'
                    WHEN trades <= 7 THEN '04-07'
                    WHEN trades <= 15 THEN '08-15'
                    WHEN trades <= 30 THEN '16-30'
                    WHEN trades <= 60 THEN '31-60'
                    ELSE '61+' END AS trades_per_day,
               COUNT(*) AS client_days, SUM(trades) AS closes,
               ROUND(AVG(pnl)::numeric, 2) AS avg_day_pnl,
               ROUND(SUM(pnl)::numeric, 2) AS total_pnl,
               ROUND(AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END)::numeric, 4) AS pct_green_days
        FROM pd GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "intensity vs expectancy")

    for r in res.get("after_loss_vs_after_win", []):
        print(f"      {r['platform']:4s} {r['state']:11s} n={r['n']:>9,}  "
              f"median gap {r['median_gap_seconds']}s  "
              f"median size x{r['median_size_ratio']}  "
              f"next exp {r['next_trade_expectancy']}")
    return res


# ══════════════════════════════════════════════════════════════════════════
# section 1 + 10 — directional accuracy, session / hour effects
# ══════════════════════════════════════════════════════════════════════════

def section_direction_session(conn, since, until):
    print("\n[1] DIRECTIONAL ACCURACY  /  [10] SESSION EFFECTS")
    dc, dp = date_clause(since, until)
    res = {}

    res["by_direction"] = q(conn, f"""
        SELECT {PLAT} AS platform,
               COALESCE(NULLIF(d.direction, ''), 'unknown') AS direction,
               COUNT(*) AS closes,
               ROUND(AVG(CASE WHEN d.profit > 0 THEN 1.0 ELSE 0 END)::numeric, 4) AS win_rate,
               ROUND(AVG(d.profit)::numeric, 2) AS expectancy,
               ROUND(SUM(d.profit)::numeric, 2) AS total_pnl,
               ROUND(AVG(d.profit) FILTER (WHERE d.profit > 0)::numeric, 2) AS avg_win,
               ROUND(AVG(d.profit) FILTER (WHERE d.profit < 0)::numeric, 2) AS avg_loss
        FROM deals d WHERE {CLOSES} {dc}
        GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "by direction")

    res["by_hour_utc"] = q(conn, f"""
        SELECT {PLAT} AS platform,
               EXTRACT(HOUR FROM to_timestamp(d.deal_time))::int AS hour_utc,
               COUNT(*) AS closes,
               ROUND(AVG(CASE WHEN d.profit > 0 THEN 1.0 ELSE 0 END)::numeric, 4) AS win_rate,
               ROUND(AVG(d.profit)::numeric, 2) AS expectancy,
               ROUND(SUM(d.profit)::numeric, 2) AS total_pnl,
               ROUND(SUM({LOTS})::numeric, 2) AS lots
        FROM deals d WHERE {CLOSES} AND d.deal_time > 0 {dc}
        GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "by hour UTC")

    res["by_dow"] = q(conn, f"""
        SELECT {PLAT} AS platform,
               EXTRACT(ISODOW FROM to_timestamp(d.deal_time))::int AS iso_dow,
               COUNT(*) AS closes,
               ROUND(AVG(d.profit)::numeric, 2) AS expectancy,
               ROUND(SUM(d.profit)::numeric, 2) AS total_pnl
        FROM deals d WHERE {CLOSES} AND d.deal_time > 0 {dc}
        GROUP BY 1, 2 ORDER BY 1, 2
    """, dp, "by day of week")

    # Top symbols by client loss — where the money actually goes.
    res["worst_symbols"] = q(conn, f"""
        SELECT {PLAT} AS platform, d.symbol,
               COUNT(*) AS closes, COUNT(DISTINCT d.login) AS logins,
               ROUND(SUM(d.profit)::numeric, 2) AS client_gross_pnl,
               ROUND(SUM(d.profit + d.commission + d.swap)::numeric, 2) AS client_net_pnl,
               ROUND(AVG(CASE WHEN d.profit > 0 THEN 1.0 ELSE 0 END)::numeric, 4) AS win_rate,
               ROUND(SUM({LOTS})::numeric, 2) AS lots
        FROM deals d WHERE {CLOSES} {dc}
        GROUP BY 1, 2 HAVING COUNT(*) >= 200
        ORDER BY client_net_pnl ASC LIMIT 40
    """, dp, "worst symbols for clients")
    return res


# ══════════════════════════════════════════════════════════════════════════
# section 17 — deposit / withdrawal behavior
# ══════════════════════════════════════════════════════════════════════════

def section_money(conn, since, until):
    print("\n[17] DEPOSIT / WITHDRAWAL BEHAVIOR")
    dc, dp = date_clause(since, until)
    res = {}

    # Deposit after loss / withdraw after profit: compare each money event to the
    # client's realized P&L over the 3 days ending on the event date.
    res["reflexes"] = q(conn, f"""
        WITH daily AS (
            SELECT d.login, NULLIF(d.deal_date,'')::date AS dt, SUM(d.profit) AS pnl
            FROM deals d WHERE {CLOSES} {dc}
            GROUP BY 1, 2
        ),
        money AS (
            SELECT d.login, NULLIF(d.deal_date,'')::date AS dt,
                   CASE WHEN d.profit > 0 THEN 'deposit' ELSE 'withdrawal' END AS kind,
                   ABS(d.profit) AS amount
            FROM deals d WHERE d.action = 2 AND d.profit <> 0
              AND LENGTH(COALESCE(d.deal_date,'')) = 10 {dc}
        ),
        joined AS (
            SELECT m.kind, m.amount,
                   COALESCE(SUM(dl.pnl), 0) AS prior_3d_pnl,
                   COUNT(dl.dt)             AS prior_3d_days
            FROM money m
            LEFT JOIN daily dl
                   ON dl.login = m.login
                  AND dl.dt BETWEEN m.dt - INTERVAL '3 day' AND m.dt
            GROUP BY m.login, m.dt, m.kind, m.amount
        )
        SELECT kind, COUNT(*) AS events,
               ROUND(SUM(amount)::numeric, 2) AS total_amount,
               COUNT(*) FILTER (WHERE prior_3d_days > 0) AS with_trading_history,
               COUNT(*) FILTER (WHERE prior_3d_days > 0 AND prior_3d_pnl < 0) AS after_losses,
               COUNT(*) FILTER (WHERE prior_3d_days > 0 AND prior_3d_pnl > 0) AS after_profits,
               ROUND(AVG(amount) FILTER (WHERE prior_3d_pnl < 0)::numeric, 2) AS avg_amt_after_loss,
               ROUND(AVG(amount) FILTER (WHERE prior_3d_pnl > 0)::numeric, 2) AS avg_amt_after_profit
        FROM joined GROUP BY 1 ORDER BY 1
    """, dp + dp, "deposit/withdrawal reflexes")

    # First deposit -> first trade latency (cheap: one row per login).
    res["first_deposit_to_first_trade"] = q(conn, f"""
        WITH fd AS (
            SELECT d.login, MIN(d.deal_time) AS dep_t
            FROM deals d WHERE d.action = 2 AND d.profit > 0 {dc}
            GROUP BY 1
        ),
        ft AS (
            SELECT d.login, MIN(d.deal_time) AS trade_t
            FROM deals d WHERE {CLOSES} {dc}
            GROUP BY 1
        )
        SELECT COUNT(*) AS logins,
               ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
                      (ORDER BY (ft.trade_t - fd.dep_t) / 3600.0))::numeric, 2) AS median_hours,
               COUNT(*) FILTER (WHERE ft.trade_t - fd.dep_t <= 3600)  AS traded_within_1h,
               COUNT(*) FILTER (WHERE ft.trade_t - fd.dep_t <= 86400) AS traded_within_24h
        FROM fd JOIN ft ON ft.login = fd.login
        WHERE ft.trade_t >= fd.dep_t AND fd.dep_t > 0
    """, dp + dp, "first deposit -> first trade")
    return res


# ══════════════════════════════════════════════════════════════════════════
# section 15 — strategy drift and randomness
# ══════════════════════════════════════════════════════════════════════════

def section_drift(conn, since, until):
    print("\n[15] STRATEGY DRIFT AND RANDOMNESS")
    dc, dp = date_clause(since, until)
    res = {}

    # Per-client, per-quarter symbol entropy + lot dispersion. Rising entropy with
    # falling expectancy is the spec's "unstable rules / near-zero edge".
    res["quarterly_entropy"] = q(conn, f"""
        WITH ps AS (
            SELECT d.login,
                   SUBSTR(d.deal_date, 1, 4) || 'Q' ||
                     ((CAST(SUBSTR(d.deal_date, 6, 2) AS int) - 1) / 3 + 1)::text AS qtr,
                   d.symbol, COUNT(*) AS n, SUM(d.profit) AS pnl, SUM({LOTS}) AS lots
            FROM deals d WHERE {CLOSES} AND LENGTH(COALESCE(d.deal_date,'')) = 10 {dc}
            GROUP BY 1, 2, 3
        ),
        tot AS (SELECT login, qtr, SUM(n) AS t FROM ps GROUP BY 1, 2),
        ent AS (
            SELECT ps.login, ps.qtr,
                   -SUM((ps.n::float / tot.t) * LN(ps.n::float / tot.t)) AS entropy,
                   COUNT(DISTINCT ps.symbol) AS symbols,
                   SUM(ps.n) AS closes, SUM(ps.pnl) AS pnl, SUM(ps.lots) AS lots
            FROM ps JOIN tot ON tot.login = ps.login AND tot.qtr = ps.qtr
            GROUP BY 1, 2
        )
        SELECT qtr, COUNT(*) AS accounts,
               ROUND(AVG(entropy)::numeric, 4)             AS avg_symbol_entropy,
               ROUND(AVG(symbols)::numeric, 2)             AS avg_symbols_traded,
               ROUND(AVG(pnl / NULLIF(closes, 0))::numeric, 2) AS avg_expectancy,
               SUM(closes) AS closes, ROUND(SUM(pnl)::numeric, 2) AS total_pnl
        FROM ent WHERE closes >= 20
        GROUP BY 1 ORDER BY 1
    """, dp, "quarterly symbol entropy")

    # Does a client's edge persist quarter to quarter? (out-of-sample persistence,
    # the one piece of the spec's output contract that IS computable today)
    res["expectancy_persistence"] = q(conn, f"""
        WITH pq AS (
            SELECT d.login,
                   SUBSTR(d.deal_date, 1, 4) || 'Q' ||
                     ((CAST(SUBSTR(d.deal_date, 6, 2) AS int) - 1) / 3 + 1)::text AS qtr,
                   COUNT(*) AS closes, AVG(d.profit) AS expectancy
            FROM deals d WHERE {CLOSES} AND LENGTH(COALESCE(d.deal_date,'')) = 10 {dc}
            GROUP BY 1, 2 HAVING COUNT(*) >= 30
        ),
        pairs AS (
            SELECT login, qtr, expectancy,
                   LEAD(expectancy) OVER (PARTITION BY login ORDER BY qtr) AS next_expectancy
            FROM pq
        )
        SELECT COUNT(*) AS account_quarter_pairs,
               ROUND(CORR(expectancy, next_expectancy)::numeric, 4) AS corr_q_to_next_q,
               COUNT(*) FILTER (WHERE expectancy > 0 AND next_expectancy > 0) AS stayed_positive,
               COUNT(*) FILTER (WHERE expectancy > 0 AND next_expectancy <= 0) AS flipped_negative,
               COUNT(*) FILTER (WHERE expectancy > 0) AS was_positive
        FROM pairs WHERE next_expectancy IS NOT NULL
    """, dp, "expectancy persistence q->q")
    return res


# ══════════════════════════════════════════════════════════════════════════
# section 16 — linked accounts
# ══════════════════════════════════════════════════════════════════════════

def section_linked(conn, ledger, since, until):
    print("\n[16] LINKED ACCOUNTS")
    res = {}

    # Accounts sharing a device identifier (cid/mqid) with at least one other
    # account. This is the cheap 1-hop version of abuse_engine.build_clusters().
    linked = q(conn, """
        WITH shared AS (
            SELECT identifier_value
            FROM account_identifiers
            WHERE identifier_type IN ('cid', 'mqid')
              AND identifier_value IS NOT NULL AND identifier_value <> ''
              AND identifier_value NOT IN ('0', 'None')
            GROUP BY 1 HAVING COUNT(DISTINCT login) > 1
        )
        SELECT DISTINCT ai.login
        FROM account_identifiers ai
        JOIN shared s ON s.identifier_value = ai.identifier_value
        WHERE ai.identifier_type IN ('cid', 'mqid')
    """, None, "device-linked logins")
    linked_set = {int(r["login"]) for r in linked}
    res["linked_logins"] = len(linked_set)

    # Do device-linked accounts lose differently from solo accounts?
    for name, subset in (("device_linked", [a for a in ledger if int(a["login"]) in linked_set]),
                         ("solo", [a for a in ledger if int(a["login"]) not in linked_set])):
        if subset:
            res[name] = cost_burden(persons_from(subset), name)
            res[name]["accounts"] = len(subset)

    res["shared_identifier_sizes"] = q(conn, """
        SELECT identifier_type,
               CASE WHEN c = 2 THEN '2' WHEN c <= 4 THEN '3-4'
                    WHEN c <= 9 THEN '5-9' ELSE '10+' END AS accounts_sharing,
               COUNT(*) AS identifier_values, SUM(c) AS account_links
        FROM (
            SELECT identifier_type, identifier_value, COUNT(DISTINCT login) AS c
            FROM account_identifiers
            WHERE identifier_value IS NOT NULL AND identifier_value <> ''
              AND identifier_value NOT IN ('0', 'None')
            GROUP BY 1, 2 HAVING COUNT(DISTINCT login) > 1
        ) x GROUP BY 1, 2 ORDER BY 1, 2
    """, None, "shared identifier fan-out")
    return res


# ══════════════════════════════════════════════════════════════════════════
# report
# ══════════════════════════════════════════════════════════════════════════

def write_report(out_dir, results):
    os.makedirs(out_dir, exist_ok=True)
    jp = os.path.join(out_dir, "loss_patterns.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)

    tp = os.path.join(out_dir, "loss_patterns_report.txt")
    L = []
    L.append("CLIENT LOSS PATTERN ANALYSIS — Tier A (computable without new capture)")
    L.append(f"generated {time.strftime('%Y-%m-%d %H:%M:%S')}   window: "
             f"{results['meta']['since'] or 'all'} .. {results['meta']['until'] or 'all'}")
    L.append("=" * 78)

    c = results.get("costs", {})
    L.append("\n[12] COST-DRIVEN LOSSES")
    for key in ("book", "platform_MT5", "platform_MT4", "excl_bonus_credit",
                "only_bonus_credit", "excl_top1pct_volume"):
        b = c.get(key)
        if not b:
            continue
        L.append(f"  {b['label']:<34} persons={b['persons']:>7,}  "
                 f"gross={b['gross_pnl']:>14,}  costs={b['total_costs']:>13,}  "
                 f"net={b['net_pnl']:>14,}")
        L.append(f"  {'':34} CBR={b['cost_burden_ratio']}  "
                 f"g2n={b['gross_to_net_conversion']}  "
                 f"flipped_by_costs={b['persons_flipped_by_costs']:,} "
                 f"({b['pct_flipped_by_costs']}%)")
    bs = c.get("flip_rate_bootstrap")
    if bs:
        L.append(f"  flip rate {bs['point']}%  95% CI [{bs['ci95_low']}, {bs['ci95_high']}]"
                 f"  ({bs['unit']}, {bs['resamples']} resamples)")

    o = results.get("overtrading", {})
    L.append("\n[9/4] REVENGE AND SIZING")
    for r in o.get("after_loss_vs_after_win", []):
        L.append(f"  {r['platform']:4s} {r['state']:<11} n={r['n']:>9,}  "
                 f"median_gap={r['median_gap_seconds']}s  "
                 f"reentry<60s={r['reentry_under_60s']:,}  "
                 f"median_size_x={r['median_size_ratio']}  "
                 f"next_exp={r['next_trade_expectancy']}")
    L.append("  expectancy by trade # in day (platform / bucket / closes / expectancy):")
    for r in o.get("expectancy_by_trade_number_in_day", [])[:44]:
        L.append(f"    {r['platform']:4s} #{str(r['trade_no_bucket']):>3}  "
                 f"{r['closes']:>9,}  {r['expectancy']:>10}  wr={r['win_rate']}")

    d = results.get("drift", {})
    L.append("\n[15] DRIFT / PERSISTENCE")
    for r in d.get("expectancy_persistence", []):
        L.append(f"  account-quarter pairs={r['account_quarter_pairs']:,}  "
                 f"corr(q, q+1)={r['corr_q_to_next_q']}  "
                 f"positive->positive={r['stayed_positive']:,} of {r['was_positive']:,}")

    lk = results.get("linked", {})
    L.append("\n[16] LINKED ACCOUNTS")
    L.append(f"  device-linked logins: {lk.get('linked_logins', 0):,}")
    for k in ("device_linked", "solo"):
        b = lk.get(k)
        if b:
            L.append(f"  {k:<14} accounts={b['accounts']:>7,}  net={b['net_pnl']:>14,}  "
                     f"CBR={b['cost_burden_ratio']}  "
                     f"flipped={b['pct_flipped_by_costs']}%")

    L.append("\nNOT COMPUTED — requires data capture that does not exist yet:")
    L.append("  MFE/MAE, forward returns, ATR/range/trend context, regime labels,")
    L.append("  stop-loss misuse, poor-exit giveback, effective leverage, margin")
    L.append("  escalation, pre-stop-out exposure, flow-price divergence.")
    L.append("  See the feasibility audit: price bars, intraday margin, SL/TP history.")

    with open(tp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return jp, tp


def main():
    ap = argparse.ArgumentParser(description="Tier-A client loss-pattern analysis (read-only)")
    ap.add_argument("--since", help="deal_date >= YYYY-MM-DD")
    ap.add_argument("--until", help="deal_date <= YYYY-MM-DD")
    ap.add_argument("--out", default="analysis_out", help="output directory")
    ap.add_argument("--probe-only", action="store_true", help="stop after the data-shape probe")
    args = ap.parse_args()

    t0 = time.time()
    print("connecting (read-only) ...")
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), inet_server_addr(), version()")
        db, host, ver = cur.fetchone()
    print(f"  {db} @ {host}  {str(ver).split(',')[0]}")

    results = {"meta": {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "since": args.since, "until": args.until,
                        "database": db, "host": str(host), "read_only": True}}

    results["shape"] = probe(conn, args.since, args.until)
    if args.probe_only:
        print("\n--probe-only: stopping before the heavy aggregates.")
        conn.close()
        return

    ledger = account_ledger(conn, args.since, args.until)
    results["accounts_analyzed"] = len(ledger)
    results["persons_analyzed"] = len({a["person"] for a in ledger})

    results["costs"] = section_costs(conn, ledger, args.since, args.until)
    results["overtrading"] = section_overtrading(conn, args.since, args.until)
    results["direction_session"] = section_direction_session(conn, args.since, args.until)
    results["money"] = section_money(conn, args.since, args.until)
    results["drift"] = section_drift(conn, args.since, args.until)
    results["linked"] = section_linked(conn, ledger, args.since, args.until)

    conn.close()
    jp, tp = write_report(args.out, results)
    print(f"\ndone in {time.time()-t0:.0f}s")
    print(f"  JSON   {jp}")
    print(f"  report {tp}")
    print(f"  {results['accounts_analyzed']:,} accounts -> "
          f"{results['persons_analyzed']:,} independent persons")


if __name__ == "__main__":
    sys.exit(main())
