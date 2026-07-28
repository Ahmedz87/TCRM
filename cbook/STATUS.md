# Phase 2 — Work Tracker

Step-by-step status of every Phase 2 work area, table and deliverable. We develop **one area at
a time**, only where data exists (see `audit/DATA_AVAILABILITY_MAP.md`).

**Status key:** ⬜ not started · 🔨 in progress · ✅ done · 🔒 BLOCKED (no data source) · 🟡 partial

---

## Spec sections (§ = section in `docs/PHASE2_FINANCIAL_RECONCILIATION.md`)

| § | Work area | Status | Note |
|---|---|---|---|
| 4  | Currency-conversion framework | 🔒 | No FX rate table → single-USD assumption pending Phase-1 confirm |
| 5  | Client account financial reconstruction (opening/closing balance, deposits, withdrawals, transfers, bonuses, realized/unrealized P&L, equity) | ✅ | Done — `lib/reconstruction.py` + `lib/classification.py` + `sql/reports/s05_*.sql` + view `cbook_cash_movements`; 10/10 tests pass. All-time per login; monthly periodization pending in §6/§8 |
| 6  | Client financial statistics (funding, account values, trading results, net wealth, returns, risk) | ⬜ | Depends on §5 |
| 7  | Money-weighted (XIRR) & time-weighted returns | ⬜ | TWR aided by `daily_snapshots` |
| 8  | Aggregate client-book statistics (daily/monthly + breakdowns) | ⬜ | Depends on §5/§6 |
| 9  | A/B/hedge/C-Book separation & classification | 🔒 | No routing data — only a *modeled* split is possible, clearly labeled hypothetical |
| 10 | B-Book financial calculations | 🟡🔒 | Gross B-Book = −client P&L is computable *as a model*; net B-Book needs hedge/LP/payment costs (missing) |
| 11 | Spread, commission, swap, markup revenue | 🟡 | Commission ✅, markup ✅ (pre-computed), swap 🟡 (FIFO), **spread ❌ not measurable** |
| 12 | IB / affiliate / rebate costs | 🟡 | Accrual vs paid split needs verification |
| 13 | Bonus / cashback / promotional costs | 🟡 | Lifecycle states need verification |
| 14 | Payment-processing & cash-movement costs | 🔒 | No fee/cost amounts stored |
| 15 | Negative-balance & credit-loss analysis | 🟡 | Derivable from deals/equity; no event log or write-off/recovery data |
| 16 | Hedging financial analysis | 🔒 | No hedge data |
| 17 | C-Book / proprietary-trading financials | 🔒 | No prop account / allocated capital |
| 18 | LP account financial reconstruction | 🔒 | No LP data |
| 19 | LP counterparty exposure | 🔒 | No LP data |
| 20 | Client profitability & contribution margin | 🟡 | Revenue side partial; cost side partial (missing payment/opex) |
| 21 | Customer acquisition economics (CAC / CLV) | 🔒 | No marketing spend source |
| 22 | Company revenue bridge | 🟡🔒 | Trading-revenue levels partial; opex/net-profit levels blocked |
| 23 | Cash-flow analysis | 🟡🔒 | Client cash flows ✅; LP/operating cash flows blocked |
| 24 | Segregated client money vs company funds | 🔒 | No segregation ledger |
| 25 | Daily & monthly financial dashboards | ⬜ | Build for available metrics only; blocked panels shown as "no data source" |
| 26 | Required reconciliations | ⬜ | Client balance/equity/aggregate reconciliations buildable; book/hedge/LP/C-Book blocked |
| 27 | Reconciliation-break classification | ⬜ | Register buildable for available reconciliations |
| 28 | Materiality framework | ⬜ | Configurable, no hard-coded thresholds |
| 29 | Required financial tables (21) | ⬜ | See table list below |
| 30 | Required code (SQL/Python library) | ⬜ | Build per area; placeholders marked `[PLACEHOLDER]` |
| 31 | Unit & reconciliation tests (20 scenarios) | ⬜ | Build alongside code |
| 32 | Final deliverables (20) | ⬜ | Accumulate |
| 33 | Final phase decision | ⬜ | Expected: **FINANCIALS_RECONCILED_WITH_LIMITATIONS** or **MATERIAL_REMEDIATION_REQUIRED** given missing LP/book/FX/cost data |

## Required tables (§29)

| # | Table | Buildable now? |
|---|---|---|
| 1 | Client account financial summary | ✅ **built** (§5) |
| 2 | Client consolidated financial summary | ✅ yes |
| 3 | Client funding & cash-flow history | ✅ yes |
| 4 | Client trading P&L & cost summary | ✅ yes (spread cost = N/A) |
| 5 | Client wealth-creation table | ✅ yes |
| 6 | Aggregate client-book summary | ✅ yes |
| 7 | A-Book/B-Book allocation table | 🔒 modeled only |
| 8 | B-Book revenue table | 🟡 gross only (model) |
| 9 | Spread/commission/swap revenue table | 🟡 (no spread) |
| 10 | IB & rebate expense table | 🟡 |
| 11 | Bonus & cashback table | 🟡 |
| 12 | Payment-processing cost table | 🔒 |
| 13 | Negative-balance cost table | 🟡 (no write-off/recovery) |
| 14 | Hedge P&L table | 🔒 |
| 15 | C-Book performance table | 🔒 |
| 16 | LP account financial table | 🔒 |
| 17 | Counterparty-exposure table | 🔒 |
| 18 | Contribution-margin table | 🟡 |
| 19 | Company revenue bridge | 🟡🔒 |
| 20 | Cash-flow & liquidity table | 🟡🔒 |
| 21 | Reconciliation-break table | ✅ (for available reconciliations) |

---

## Recommended build order

1. **§5 Client account financial reconstruction** — opening/closing balance, deposit/withdrawal
   classification, internal-transfer elimination, realized gross/net P&L, unrealized P&L, closing
   equity. Delivers Tables 1–5. All data exists.
2. **§6 + §7 Client statistics & returns** — funding stats, net wealth created, MWR/TWR, risk.
3. **§8 Aggregate client book** — daily/monthly + breakdowns. Table 6.
4. **§26–§27 Reconciliations & break register** — prove Tables 1–6 tie out; Table 21.
5. Then partial areas (§11 commission/markup/swap, §12 IB, §13 bonus, §15 neg-balance, §20 contribution).
6. Blocked areas (§9,10-net,14,16,17,18,19,21,22-opex,23-LP,24) wait on the missing-data register.

Each step ships: SQL/Python (read-only), the table(s), a reconciliation, and tests — before
moving on. **No step touches client accounts or real actions.**

---

## Changelog

- **2026-07-28** — Section created. Phase-2 spec loaded; Phase-1 data-availability audit done;
  work tracker established.
- **2026-07-28** — §5 Client Account Financial Reconstruction built (single-currency USD, FX
  deferred by owner). Reuses build_transactions.py classification (ported to Python + SQL view).
  Delivers Table 1 + client balance/equity reconciliation with explicit `balance_break`.
  10/10 §31 unit tests pass in-sandbox. Next: §6 client statistics + §7 MWR/TWR returns, then §8
  aggregate book — building on Table 1.
