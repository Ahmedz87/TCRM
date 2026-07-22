# Giant-table money → NUMERIC migration (P0-2 remainder)

**Status:** PLANNED, not executed. Needs a maintenance window + sign-off on the per-column list
below. The 22 smaller payout/commission tables were already converted (Jul 16, see
`migrate_money_numeric.py`); these 4 giants were deferred because they need a full table rewrite.

## ⚠️ Why this is NOT a blanket conversion
A `float → numeric(18,2)` sweep would **corrupt trading data**. These float columns are NOT
2-decimal money and must be left alone (or given a different precision):

| Column(s) | What it is | Do NOT do |
|-----------|-----------|-----------|
| `deals.price`, `ib_trades.open_price` / `close_price` | forex **price** (~5 dp) | rounding to 2dp destroys the rate |
| `deals.volume`, `ib_trades.lots`, `excel_trade_commission.lots` | lot **quantity** | 0.01-lot precision lost at (18,2) |
| `deals.markup_per_lot`, `ib_trades.comm_per_lot` / `eng_cpl` | per-lot **rates** | not 2-dp money |

## The columns to actually convert → `numeric(18,2)`
Only genuine money amounts:
- `deals`: **profit, commission, swap, balance_after, markup_profit**  (17.0M rows, 6.1 GB, PK=id)
- `transactions`: **amount**  (2.1M rows, PK=id)  ← cleanest, do this one first as the proof
- `ib_trades`: **profit, commission**  (3.1M rows, **NO PK** — batch by `ctid` or add a surrogate key)
- `excel_trade_commission`: **commission**  (4.4M rows, PK=(login, deal_id))

*(If price/quantity precision is also wanted later, do those separately: price → numeric(18,5),
lots → numeric(12,2) — SEPARATE decision, not part of this money pass.)*

## Safe ONLINE procedure (per table, avoids the long ACCESS EXCLUSIVE lock that caused the Jul 17 stall)
Do NOT use `ALTER COLUMN ... TYPE numeric USING ...` on these — it rewrites the whole table under an
exclusive lock for minutes (blocks the bridge/workers writing + every read; that lock-pileup pattern
already took the site down once). Instead, per money column:

1. `ALTER TABLE t ADD COLUMN col_num numeric(18,2)` — instant (metadata only, nullable).
2. Add a keep-in-sync trigger so rows written during the backfill stay correct:
   `BEFORE INSERT OR UPDATE ... SET NEW.col_num = round(NEW.col::numeric, 2)`.
3. Backfill in PK batches with a throttle (sleep between batches) so live traffic isn't starved:
   `UPDATE t SET col_num = round(col::numeric,2) WHERE id BETWEEN :lo AND :hi AND col_num IS NULL`.
   (ib_trades: batch by `ctid` ranges since it has no PK.)
4. Verify: `SELECT count(*) FROM t WHERE col IS DISTINCT FROM col_num` = 0.
5. Swap in ONE fast transaction: drop the trigger, `ALTER TABLE t DROP COLUMN col;
   ALTER TABLE t RENAME COLUMN col_num TO col;` (fast metadata ops). Check for dependent VIEWS /
   generated columns / indexes on the column FIRST — recreate any after.

## Before running
- Confirm the day's verified backup exists (restore-drill proven Jul 17 — 92s).
- Low-traffic window (CRM staff = Iraq business hours; early UTC morning is quietest).
- Do `transactions.amount` first (single clean column, PK) to validate the whole procedure, verify,
  then proceed table by table, monitoring `pg_stat_activity` + locks between each.
- The money AGGREGATIONS already round in-query, so displayed money is correct TODAY — this is
  defensive storage-correctness, not an active bug. No rush; do it right.
