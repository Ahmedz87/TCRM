# Data Availability Map — Phase 1 → Phase 2 bridge

Maps every data source the Phase 2 spec (§3) requires against what **actually exists** in the
TNFX CRM database (`backend/models.py`, 42 tables) and known data pipelines (`CLAUDE.md`).

**Legend:** ✅ EXISTS · 🟡 PARTIAL / derivable with caveats · ❌ MISSING (no source)

> This map is authoritative for Rule #2 ("use only validated data sources"). If a required
> input is ❌ MISSING here, the dependent Phase 2 calculation is **UNAVAILABLE** and must be
> listed as such — not fabricated.

---

## Summary verdict

| Domain | Verdict |
|---|---|
| **Client account financials** (balances, deposits, withdrawals, realized/unrealized P&L, commission, swap, net wealth, returns) | ✅ **Largely available** — the buildable core of Phase 2 |
| **Aggregate client book** (daily/monthly totals, breakdowns) | ✅ Available (from the above) |
| **Bonus / credit accounting** | 🟡 Partial — campaigns & client bonuses exist; lifecycle states (expired/reversed/converted) need verification |
| **IB / rebate cost** | 🟡 Partial — accruals exist; paid-vs-accrued split & payment ledger need verification |
| **Spread / slippage / markup revenue** | 🟡 Partial — markup is pre-computed on deals; true spread & slippage **not measurable** (no quote/reference price, single-execution deal rows) |
| **Book classification (A/B/C)** | ❌ **Missing** — no execution-routing data. Any classification is *modeled/hypothetical*, not factual |
| **Hedging** | ❌ Missing — no hedge orders or hedge P&L |
| **C-Book proprietary trading** | ❌ Missing — no allocated capital, no prop account, no C-Book positions |
| **LP accounts & counterparty exposure** | ❌ Missing — no liquidity-provider data of any kind |
| **FX / currency conversion** | ❌ Missing — `currency` labels exist, but no rate table |
| **Payment-processing costs** | ❌ Missing — `psp_reference` exists, but no fee/cost amounts |
| **Chargebacks / reversals (distinct)** | 🟡 Partial — `status` has rejected/failed/cancelled, but no explicit chargeback type |
| **Negative-balance events** | 🟡 Derivable from `deals`/equity, but no dedicated event log |
| **Segregated client money / company funds** | ❌ Missing — no fund-segregation ledger |
| **Operating costs / marketing spend (CAC)** | ❌ Missing — no G&L or ad-spend source |

**Bottom line:** Phase 2's **client-level and aggregate-client-book financial reconciliation is
buildable.** Everything downstream of a *real* book split — B-Book result as fact, hedging,
C-Book P&L, LP reconciliation, counterparty exposure, company revenue bridge, cash-flow,
segregation — is **not supported by current data** and must be reported as unavailable (with the
missing data named per §32 items 19–20).

---

## 1. Client & account information (spec §3)

| Spec field | Status | Real source | Notes |
|---|---|---|---|
| client_id | ✅ | `clients.id` | CRM aggregates the LIST by **phone + platform**; MT4/MT5 separate |
| account_id / login | ✅ | `clients.login`, `trading_accounts.login` | login is the real account key; `client_id` is often NULL on portal/deals links (linked by login) |
| account currency | 🟡 | `transactions.currency` (default USD) | No per-account currency column on `clients`/`trading_accounts`; **assume single reporting ccy = USD pending Phase-1 confirmation** |
| platform | ✅ | derived (MT4 / MT5) | MT4 from journal, MT5 from bridge |
| account status | ✅ | `clients.client_status`, `is_active`, `archived_at` | lead\|registered\|demo\|funded\|active\|inactive\|suspended\|churned |
| open / close date | 🟡 | `clients.reg_date`, `archived_at` | reg_date is a string; close inferred from archive |
| leverage | ✅ | `clients.leverage`, `trading_accounts` | |
| regulatory entity | ❌ | — | No legal-entity field. Single-entity assumption unless Phase 1 says otherwise |
| book classification | ❌ | — | **No book label exists.** Marketing copy only |

## 2. Cash transactions (spec §3)

| Spec field | Status | Real source | Notes |
|---|---|---|---|
| deposits / withdrawals | ✅ | `transactions` (tx_type), `deals` (action 2 balance) | transactions built from MT5 deals + MT4 journal |
| internal transfers | 🟡 | `deals.deal_type='internal_transfer'`, `transactions.method='internal'` | Must be eliminated at consolidated client level (§5.4) |
| wallet transfers | 🟡 | portal simulation | Portal deposits/withdraws are **SIMULATION** (per CLAUDE.md) — must be excluded/flagged |
| chargebacks | ❌ | — | No distinct chargeback record; only status=rejected/failed/cancelled |
| payment reversals | 🟡 | `transactions.status` | reversal = status transition, not a separate row |
| bonuses / credits / cashback | 🟡 | `client_bonuses`, `bonus_campaigns`, `deals` (action 3 credit, 6 bonus) | lifecycle states need verification |
| negative-balance corrections | 🟡 | derivable from `deals` balance ops | no dedicated flag |
| manual journal / fee / tax adjustments | ❌ | — | No manual-journal table |

## 3. Trading transactions (spec §3)

| Spec field | Status | Real source | Notes |
|---|---|---|---|
| realized gross P&L | ✅ | `deals.profit` (trades, action 0/1) | |
| realized net P&L | ✅ | `deals.profit − commission − swap` | commission & swap on `deals` |
| unrealized P&L | 🟡 | `clients.equity − clients.balance` | snapshot only (live); open-position-level UPL needs bridge `/positions` (live, not stored) |
| commission | ✅ | `deals.commission` | |
| swap | 🟡 | `deals.swap` | **`deals.swap` is ~empty** (per CLAUDE.md) → overnight derived via FIFO pairing |
| spread cost | ❌ | — | **Not directly measurable** — deals are single-execution rows at one `price`, no quote/reference price |
| slippage | ❌ | — | No requested-vs-filled price |
| position adjustments / stop-out | 🟡 | `deals.comment`, `balance_after` | inferable from comments, not typed |

## 4. Broker & LP data (spec §3)

| Spec field | Status | Notes |
|---|---|---|
| client-book classification | ❌ | No routing data |
| hedge orders | ❌ | None |
| LP executions / commission / spread / swap | ❌ | None |
| LP balance / equity / margin | ❌ | **No LP account exists in the system** |
| LP deposits / withdrawals / settlement | ❌ | None |
| counterparty charges | ❌ | None |

→ **All of §16 (hedging), §17 (C-Book), §18–19 (LP) is UNAVAILABLE.**

## 5. Commercial costs (spec §3)

| Spec field | Status | Real source | Notes |
|---|---|---|---|
| IB commission | 🟡 | `ib_commissions`, `commission_plans`, `sales_commissions` | accrued vs paid split needs verification (§12) |
| affiliate rebate / cashback | 🟡 | `loyalty_transactions`, bonus tables | mapping to §12/§13 categories TBD |
| bonus | ✅ | `client_bonuses`, `bonus_campaigns` | |
| payment-processing / platform / bridge / market-data fee | ❌ | — | **No cost/fee amounts stored anywhere** |
| operational allocation | ❌ | — | No G&L / opex source |

---

## FX framework (spec §4) — status

❌ **No exchange-rate table exists.** `transactions.currency` and any account currency are
labels only. Until a validated rate source is supplied, **all multi-currency conversion (§4),
balance-sheet/cash-flow conversion, and any reporting-currency figure other than the native
currency is UNAVAILABLE.** Working assumption pending Phase 1: the book is effectively
**single-currency USD**; this must be confirmed, not assumed, before consolidated figures are
published.

---

## Missing-data register (feeds §32 items 19–20)

Exact data needed to unlock currently-unavailable Phase 2 calculations:

1. **Book routing / execution log** — per-trade A/B/C classification with point-in-time history.
2. **LP account statements** — balance, equity, margin, deposits, withdrawals, executions, commission, swap, per LP per day.
3. **Hedge order log** — hedge fills with entry/exit price, volume, costs, and link to the client exposure hedged.
4. **FX rate table** — dated conversion rates (transaction-date, daily-close, month-end) per currency pair with source & timestamp.
5. **Payment-cost data** — per-method deposit/withdrawal fees, FX cost, chargeback cost, acquiring fees.
6. **Chargeback / reversal ledger** — distinct records, not just status transitions.
7. **Negative-balance event log** — equity-before, gap, write-off, recovery per event.
8. **Company G&L / opex + marketing spend** — for the revenue bridge (§22), cash-flow (§23) and CAC (§21).
9. **Fund-segregation ledger** — segregated client cash vs company/trading/restricted cash (§24).
10. **Quote/tick history** — reference & executable prices, to make spread and slippage measurable (§3, §11).

Anything not on a validated source above stays **UNAVAILABLE** and is never fabricated.
