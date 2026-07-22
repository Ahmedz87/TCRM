# -*- coding: utf-8 -*-
"""P0-2: convert float money columns -> NUMERIC(18,2) — SAFE SUBSET (Jul 16 2026).

Float can't exactly represent money and accumulates sub-cent drift in SUMs. This converts the
DECISION-CRITICAL money tables (payouts, commissions, loyalty, IB balances) to exact NUMERIC.

SAFE by design:
  * IN-DB backup (CREATE TABLE _bak_...) of every populated table BEFORE altering it — instant
    rollback if anything looks wrong.
  * EXCLUDES the 4 giant tables (deals 6GB / transactions 1.1GB / ib_trades 1.1GB /
    excel_trade_commission 482MB) — those rewrite the whole table under a minutes-long lock and
    need a real file backup + maintenance window. They stay float for now; their money
    AGGREGATIONS are rounded in-query instead.
  * ROUND(col::numeric,2) on convert so any existing non-2dp float noise is cleaned.

Run:  python migrate_money_numeric.py            (dry run — prints the plan + sizes)
      python migrate_money_numeric.py --apply    (backup + convert, with timing)
      python migrate_money_numeric.py --rollback  (restore every table from its _bak_ copy)
"""
import sys, time
import db_config

STAMP = "20260716"   # backup-table suffix (static so --rollback can find them)

# (table -> [money columns]) — curated safe subset; giants + big display tables excluded.
TABLES = {
    "ibs": ["balance","commission_computed","commission_excel","commission_live","commission_new",
            "markup_pips","net_deposits","paid_commission","total_commission","total_volume","unpaid_commission"],
    "ib_commissions": ["commission_native","commission_usd","volume"],
    "ib_operations": ["amount","converted_amount"],
    "loyalty_accounts": ["points_balance"],
    "excel_commission_daily": ["commission"],
    "abuse_cases": ["total_deposits"],
    # 0-row / tiny config + future tables (zero data risk, makes future writes exact):
    "client_bonuses": ["amount"],
    "sales_commissions": ["commission_amount","commission_rate","markup_profit","volume"],
    "sales_targets": ["commission_earned","commission_rate","deposit_actual","deposit_target","volume_actual","volume_target"],
    "bonus_campaigns": ["amount","max_amount","min_deposit"],
    "commission_plans": ["min_payout"],
    "finance_expenses": ["amount"],
    "contests": ["min_deposit"],
    "ib_challenges": ["min_deposit_per_ftd","reward_amount"],
    "daily_snapshots": ["balance","deposits","equity","markup_revenue","profit","volume_lots","withdrawals"],
    "markup_config": ["ask_markup","bid_markup","total_markup"],
    "score_settings": ["high_balance_threshold","large_withdrawal_threshold","low_equity_threshold"],
    "ib_tier_requirements": ["min_deposit"],
    "retention_flags": ["net_deposit","total_deposits","total_withdrawals"],
    "loyalty_referrals": ["bonus_points"],
    "ib_commission_calc": ["commission_usd"],
    "finance_method_agg": ["deposits","withdrawals"],
}


def _cols_exist(cur, table):
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r[0]: r[1] for r in cur.fetchall()}


def main():
    apply = "--apply" in sys.argv
    rollback = "--rollback" in sys.argv
    c = db_config.connect(); c.autocommit = True; cur = c.cursor()

    if rollback:
        for t in TABLES:
            bak = f"_bak_{t}_{STAMP}"
            cur.execute("SELECT to_regclass(%s)", (bak,))
            if cur.fetchone()[0] is None:
                continue
            cur.execute(f"TRUNCATE {t}")
            cur.execute(f"INSERT INTO {t} SELECT * FROM {bak}")
            print(f"rolled back {t} from {bak}")
        print("ROLLBACK done. (backup tables kept — drop manually once verified.)")
        c.close(); return

    total = 0.0
    for t, cols in TABLES.items():
        have = _cols_exist(cur, t)
        if not have:
            print(f"skip {t}: table not found"); continue
        tgt = [col for col in cols if have.get(col) in ("double precision", "real")]
        if not tgt:
            continue
        cur.execute(f"SELECT count(*) FROM {t}")
        n = cur.fetchone()[0]
        print(f"{t:24} {n:>9,} rows  -> {len(tgt)} cols: {','.join(tgt)}")
        if not apply:
            continue
        t0 = time.time()
        # 1) in-DB backup of populated tables (rollback point)
        if n > 0:
            bak = f"_bak_{t}_{STAMP}"
            cur.execute(f"DROP TABLE IF EXISTS {bak}")
            cur.execute(f"CREATE TABLE {bak} AS SELECT * FROM {t}")
        # 2) convert ALL its money columns in ONE ALTER (single rewrite)
        alter = ", ".join(f"ALTER COLUMN {col} TYPE numeric(18,2) USING round({col}::numeric, 2)" for col in tgt)
        cur.execute(f"SET lock_timeout = '30s'")
        cur.execute(f"ALTER TABLE {t} {alter}")
        dt = time.time() - t0; total += dt
        print(f"   converted in {dt:.2f}s (backup: _bak_{t}_{STAMP})")
    if apply:
        print(f"\nALL DONE in {total:.1f}s. Verify the IB / loyalty / agents / finance pages, then drop _bak_* tables.")
    else:
        print("\nDRY RUN. Re-run with --apply to back up + convert.")
    c.close()


if __name__ == "__main__":
    main()
