# Behavioral Client-Flow C-Book Project
## Phase 2 — Financial Facts, Accounting Logic and Reconciliation

This phase begins only after the **Data Inventory, Feasibility and Quality Audit** (Phase 1) has
been completed and all critical data-quality blockers have been documented
(see `../audit/DATA_AVAILABILITY_MAP.md`).

The purpose of this phase is to establish a **financially reconciled and auditable foundation**
for all later client analysis, behavioral classification, clustering, C-Book strategy research,
risk calculations and management reporting.

> **Do not perform behavioral interpretation during this phase.** Focus only on financial facts,
> accounting treatment, cash movements, trading results, costs, balances, equity, margin, LP
> accounts and reconciliation.

---

## 1. Mandatory working rules

1. Do not invent any figures, balances, costs, exchange rates, journal entries or account relationships.
2. Use only the validated data sources identified in Phase 1.
3. Clearly distinguish between:
   - Client money
   - Company money
   - Trading capital
   - Restricted or segregated funds
   - Funds held with liquidity providers
   - Receivables
   - Payables
   - Realized profit
   - Unrealized profit
   - Cash flow
4. Do not treat client losses as broker profit without reconciling:
   - A-Book activity
   - B-Book activity
   - Hedge activity
   - C-Book positions
   - LP execution costs
   - Rebates
   - Bonuses
   - Negative balances
   - Payment costs
   - Operational costs
5. All financial calculations must specify: currency, reporting currency, conversion rate,
   conversion timestamp, gross or net basis, realized or unrealized basis, accounting period.
6. Preserve the original transaction currency and separately calculate reporting-currency values.
7. Do not net unrelated categories unless the accounting logic requires it.
8. Every derived financial figure must be traceable to source transactions.
9. Every reconciliation difference must be reported explicitly.
10. Do not force balances to reconcile using unidentified balancing entries.
11. Unexplained differences must remain visible as reconciliation breaks.
12. All reports must be reproducible by account, client, platform, currency, day and month.

---

## 2. Main objectives

Establish reliable financial facts at five levels:

1. Client account level
2. Aggregate client-book level
3. Broker revenue level
4. C-Book or proprietary-trading level
5. Liquidity-provider and company level

The final output must allow management to answer:

- How much money did each client deposit and withdraw?
- How much did each client gain or lose from trading?
- How much of each client's result came from price movement and how much from costs?
- What is the aggregate client liability?
- What portion of exposure was A-Booked, B-Booked, hedged or internally traded?
- What did the broker earn from spread, commissions, swap and client trading losses?
- What did the broker lose through client profits, hedging, execution, bonuses, rebates and negative balances?
- What did the C-Book strategy earn or lose independently?
- How much cash and equity are held with each LP?
- How much margin is used?
- What is the company's actual available trading capital?
- Which amounts do not reconcile?

---

## 3. Required source data

Use the validated sources for:

**Client and account information:** client_id, account_id, account currency, platform, account
status, open date, close date, leverage, regulatory entity, book classification where available.

**Cash transactions:** deposits, withdrawals, internal transfers, wallet transfers, chargebacks,
payment reversals, bonuses, cashback, credits, negative-balance corrections, manual journal
entries, fee adjustments, tax adjustments if applicable.

**Trading transactions:** realized gross P&L, realized net P&L, unrealized P&L, commission, swap,
spread, slippage, other trading costs, position adjustments, stop-out transactions.

**Broker and LP data:** client-book classification, hedge orders, LP executions, LP commission,
LP spread, LP swap, LP balance, LP equity, LP margin, LP deposits and withdrawals, settlement
transactions, counterparty charges.

**Commercial costs:** IB commission, affiliate rebate, cashback, bonus, payment-processing fee,
platform fee, bridge fee, market-data fee, operational allocation where separately available.

> ℹ️ **Availability of every item above is assessed in `../audit/DATA_AVAILABILITY_MAP.md`.**
> Items marked ❌ MISSING there make the dependent calculation UNAVAILABLE.

---

## 4. Currency-conversion framework

Before calculating consolidated values, define a formal currency-conversion framework.
For every monetary amount retain:

```text
original_amount
original_currency
reporting_amount
reporting_currency
conversion_rate
conversion_source
conversion_timestamp
conversion_method
```

**Conversion rules** — define separately: transaction-date conversion, daily closing-rate
conversion, month-end conversion, historical account-currency conversion, realized P&L
conversion, unrealized P&L conversion, balance-sheet conversion, cash-flow conversion.

Do not use the current exchange rate for historical transactions unless this is explicitly
required for a separate analytical view.

**Required tests:** missing exchange rates, duplicate rates, outlier rates, inconsistent inverse
rates, rate timestamps outside transaction windows, reporting-currency differences between
systems. Produce an **FX conversion exception table**.

---

## 5. Client account financial reconstruction

For every account and accounting period, calculate the following.

**5.1 Opening balance** — the account balance at the beginning of the period. If no direct
snapshot exists, reconstruct it from the latest validated transaction before the period start.

**5.2 Deposits** — gross deposits initiated, completed, failed, reversed, chargeback-adjusted,
net completed.

```text
Net Completed Deposits = Completed Deposits − Deposit Reversals − Chargebacks
```

Do not count internal transfers as external deposits.

**5.3 Withdrawals** — requested, approved, completed, rejected, reversed, net completed. Do not
count internal transfers as external withdrawals.

**5.4 Internal transfers** — separate account-to-account, wallet-to-account, account-to-wallet,
inter-entity, bonus-wallet. Must net to zero at the consolidated client level unless they cross
legally separate entities or currencies with real costs.

**5.5 Bonuses and credits** — separate tradable bonus, non-withdrawable credit, cashback,
promotional adjustment, negative-balance correction, manual goodwill credit, reversed bonus,
expired bonus. Do not classify all credits as revenue or client capital without understanding
their accounting treatment.

**5.6 Realized gross trading P&L** — result from closed positions before commission, swap and
other trading costs.

**5.7 Trading costs** — commission, swap, spread cost where directly measurable, slippage,
financing, administrative fee, currency-conversion fee, other.

**5.8 Realized net trading P&L**

```text
Realized Net Trading P&L
= Realized Gross Trading P&L
− Commission − Swap Cost − Spread Cost − Slippage Cost − Other Trading Costs
+ Positive Swap or Trading Credits
```

**5.9 Closing balance**

```text
Closing Balance
= Opening Balance
+ Net Completed Deposits − Net Completed Withdrawals + Net Internal Transfers
+ Realized Gross Trading P&L
− Commission − Swap and Financing Costs − Other Trading Costs
+ Bonus and Credit Adjustments + Manual Journal Adjustments
```

The exact sign convention must match the source system and be documented.

**5.10 Unrealized P&L** — from open positions using valid executable market prices. Long → closing
Bid; short → closing Ask. Do not use mid-price unless the platform itself marks at mid-price and
this is documented.

**5.11 Closing equity**

```text
Closing Equity = Closing Balance + Unrealized P&L
```

Include other equity adjustments only if part of the platform's official equity definition.

---

## 6. Client financial statistics

For every account and client calculate:

**Funding:** total deposits, total withdrawals, net funding, number of deposits/withdrawals,
average deposit, median deposit, largest deposit/withdrawal, deposit/withdrawal frequency,
deposit-after-loss amount & ratio, withdrawal-after-profit amount & ratio, funding dependency ratio.

**Account values:** opening/closing/average/minimum/maximum balance; opening/closing/average/
minimum/maximum equity.

**Trading results:** realized gross P&L, realized net P&L, unrealized P&L, total trading result,
commission, swap, spread cost, slippage cost, other costs, total client trading costs,
gross-to-net P&L difference.

**Economic result:**

```text
Net Wealth Created = Current Equity + Completed Withdrawals − Completed Deposits
Client Net Profit  = max(0,  Net Wealth Created)
Client Net Loss    = max(0, −Net Wealth Created)
```

If applicable, adjust separately for external non-trading transfers and chargebacks.

**Returns:** return on net funding, return on average equity, money-weighted return (where
cash-flow timing supports it), time-weighted return (where daily valuation supports it), monthly
client return, cumulative client return. Do not calculate return on net funding where the
denominator is zero, negative or economically meaningless — flag such cases.

**Risk:** maximum floating loss, maximum drawdown in currency, maximum drawdown percentage,
largest daily loss, largest monthly loss, stop-out loss, negative-balance amount, amount
recovered after negative-balance correction.

---

## 7. Money-weighted and time-weighted returns

**Money-Weighted Return** — XIRR / IRR on dated cash flows and final account value. Deposits =
negative investor cash flows, withdrawals = positive, ending equity = final positive value.
Document the sign convention.

**Time-Weighted Return** — subperiod returns between external cash flows, geometrically linked.
Measures trading performance independently of deposit/withdrawal timing.

**Required comparison per client:** Net P&L, net wealth created, money-weighted return,
time-weighted return, return on average equity. Explain differences among these measures.

---

## 8. Aggregate client-book financial statistics

Daily and monthly: total client balance, total client equity, total deposits, total withdrawals,
net client cash flow, aggregate realized gross P&L, aggregate realized net P&L, aggregate
unrealized profit, aggregate unrealized loss, total commission, total swap, total spread cost,
total slippage cost, total bonus, total cashback, total negative-balance correction, total
trading volume, total open notional exposure.

**Break down by:** platform, legal entity, country, client segment, IB, campaign, source, symbol,
asset class, account type, currency, book type.

---

## 9. A-Book, B-Book, hedge and C-Book separation

Create a **point-in-time** classification of every client exposure and execution. For every trade
or position determine whether it was: fully A-Booked, fully B-Booked, partially hedged,
dynamically hedged, netted internally, used as input to C-Book but not directly mirrored, or
unclassified.

Do not assume current book labels applied historically unless point-in-time history exists.

**Required exposure fields:**

```text
client_trade_id
book_classification
classification_timestamp
a_book_volume
b_book_volume
hedged_volume
unhedged_volume
c_book_related_flag
lp_id
hedge_order_id
```

**Required reconciliation:**

```text
Client Volume = A-Booked Volume + B-Booked Volume
B-Book Risk Retained = B-Booked Volume − Hedge Volume    (where hedging is partial)
```

Document whether hedge volume is directly linked or allocated by a netting method.

---

## 10. B-Book financial calculations

**10.1 Gross B-Book trading result** (for exposure retained internally):

```text
Gross B-Book Trading Result = − Client Gross P&L on Retained B-Book Exposure
```

Use exact retained volumes and correct timing.

**10.2 Net B-Book trading result:**

```text
Net B-Book Trading Result
= Gross B-Book Trading Result
+ Related Client Commission Revenue + Related Spread Revenue + Related Swap Revenue
− Hedge Costs − Hedge Losses − IB Rebates − Bonus and Cashback Expense
− Negative-Balance Cost − Payment Costs allocated to the client segment − Other Direct Costs
```

Do not include unrelated operating expenses at this stage unless calculating full contribution or
operating profit.

**10.3 B-Book liabilities** — client realized profits, client unrealized profits, withdrawable
client equity, pending withdrawals, negative-balance obligations where applicable.

**Required outputs:** B-Book result by day / month / client / symbol / cluster (where later
applicable); gross and net; realized and unrealized; direct-cost bridge.

---

## 11. Spread, commission and markup revenue

**Commission revenue** — gross commission charged, discounts, rebates, IB share, net retained.

```text
Net Commission Revenue = Gross Client Commission − Commission Rebates − IB Commission Share
```

**Spread revenue** (where exact quote and execution data exist):

```text
Client Spread Revenue = Client Execution Price − Reference Price
```

converted to monetary value with correct direction and volume. Separate base market spread,
broker markup, LP spread, effective client spread, net spread retained.

**Swap revenue:**

```text
Net Swap Revenue = Swap Charged to Clients − Swap Paid to LPs − Swap Rebates
```

Separate positive and negative swap effects.

**Markup revenue** — by symbol, account type, client, IB, region, platform.

---

## 12. IB, affiliate and rebate costs

Per client/period: CPA, revenue share, lot rebate, spread rebate, commission rebate, hybrid
compensation, manual adjustments, reversed commissions, unpaid accruals, paid amounts.

```text
Opening IB Payable + Current-Period Accrual − Payments − Reversals = Closing IB Payable
```

Calculate IB cost per client, per lot, per million, as % of revenue, and contribution after IB
expense. Do not treat accrued and paid IB commission as the same figure.

---

## 13. Bonus, cashback and promotional costs

Bonus granted, used, expired, reversed, converted to withdrawable balance; cashback accrued,
paid; negative-balance absorption; promotional credit cost. Reconcile promotional journals to
account balances.

```text
Net Promotional Cost = Bonus and Cashback Paid or Economically Consumed − Reversed or Expired Amounts
```

Distinguish: accounting credit, cash cost, trading credit, withdrawable liability.

---

## 14. Payment-processing and cash-movement costs

By payment method: deposit-processing cost, withdrawal-processing cost, FX-conversion cost,
chargeback cost, refund cost, bank fee, wallet fee, card-acquiring fee, fraud-loss cost.

Calculate payment cost per funded client, per deposit, per withdrawal, as % of deposit value, as
% of net trading revenue.

---

## 15. Negative-balance and credit-loss analysis

Per event: account equity before event, market event, symbol, position exposure, gap or slippage,
equity after close-out, negative amount, client recovery, company write-off, insurance/compensation
recovery, final net cost.

Aggregate: total negative-balance cost; cost by symbol / event / account type / leverage / region /
book type. Do not classify all negative balances as client trading loss revenue.

---

## 16. Hedging financial analysis

Per hedge/allocation: hedge entry price, exit price, volume, realized/unrealized hedge P&L,
commission, spread, swap, slippage, market impact, net hedge result.

```text
Net Hedge Result = Gross Hedge P&L − Hedge Commission − Hedge Spread − Hedge Swap − Hedge Slippage − Other Execution Costs
```

**Hedge-effectiveness:** client exposure before/after hedge, risk reduction, hedge ratio, basis
risk, residual exposure, hedge cost, P&L offset ratio.

```text
P&L Offset Ratio = − Hedge P&L / Client P&L on Hedged Exposure
```

Interpret carefully when denominators are small.

---

## 17. C-Book and proprietary-trading financial calculations

The C-Book must be accounted for as an **independent strategy**. Do not mix C-Book result with
B-Book revenue.

**Capital:** allocated capital, opening/closing trading balance, opening/closing trading equity,
average trading equity, capital additions/withdrawals, restricted capital, available capital.

**Trading result:** gross/net realized P&L, unrealized P&L, total net P&L, spread cost, commission,
swap, slippage, execution fees, market impact, technology/operational costs where allocated.

**Returns:**

```text
Return on Allocated Capital     = Net C-Book P&L / Average Allocated Capital
Return on Average Trading Equity = Net C-Book P&L / Average Trading Equity
Return on Risk Capital          = Net C-Book P&L / Average Capital at Risk
```

**Efficiency:** net P&L per trade / per independent signal / per lot / per million; capital
turnover; margin turnover; cost-to-gross-profit ratio.

**Risk:** current drawdown, maximum drawdown, maximum floating loss, worst day, worst month,
capital at risk, gross exposure, net exposure, effective leverage, margin utilization.

---

## 18. LP account financial reconstruction

Per LP account and period: opening cash balance, deposits to LP, withdrawals from LP, realized
trading P&L, unrealized P&L, commission, spread cost, swap, other fees, closing cash balance,
closing equity, used margin, free margin, margin level, withdrawable cash.

```text
Closing LP Balance = Opening LP Balance + Deposits − Withdrawals + Realized Gross P&L − Commission − Swap − Other LP Costs
Closing LP Equity  = Closing LP Balance + Unrealized P&L
```

Report reconciliation differences by LP and day.

---

## 19. LP counterparty exposure

```text
Counterparty Exposure = Cash Held with LP + Positive Unrealized P&L + Receivables − Payables
```

Also a conservative **stressed** exposure including delayed withdrawal, disputed trades, haircut
on unrealized P&L, settlement delay, LP failure scenario.

Calculate: largest LP concentration, top-three LP concentration, exposure by legal entity, by
currency, unsecured exposure, excess above counterparty limit.

---

## 20. Client profitability and contribution margin

**Revenue components:** B-Book result attributable to client, spread revenue, commission revenue,
swap revenue, markup revenue, other direct revenue.

**Direct costs:** A-Book/hedge execution cost, IB commission, rebate, bonus, cashback, payment
cost, negative-balance cost, direct platform cost, direct support/servicing cost where available.

```text
Client Contribution Margin = Total Direct Client Revenue − Total Direct Client Cost
```

Calculate: contribution margin amount & percentage, revenue per lot, revenue per million,
contribution per active month, contribution per deposit, contribution after acquisition cost.

Do not confuse a profitable trader for the client with an unprofitable client for the broker —
report both separately.

---

## 21. Customer acquisition economics

Where marketing/sales data exist:

```text
CAC = Eligible Sales and Marketing Acquisition Cost / Number of Newly Funded Clients
```

Define included costs. **CLV:** historical realized, cohort-based, contribution-margin,
discounted expected (if a model is available). **CLV/CAC** only where definitions are consistent.

```text
CAC Payback Period = CAC / Average Monthly Client Contribution Margin
```

Report clients/cohorts with negative contribution separately.

---

## 22. Company revenue bridge

Daily and monthly:

```text
Gross Trading and Fee Revenue
= Gross B-Book Result + Spread Revenue + Commission Revenue + Swap Revenue + Markup Revenue + Other Trading Revenue

Net Trading Revenue
= Gross Trading and Fee Revenue + Net Hedge Result
− IB and Rebate Expense − Bonus and Cashback Expense − Payment Costs − Negative-Balance Cost − Direct LP and Execution Costs

Operating Profit = Net Trading Revenue + Other Operating Revenue − Operating Expenses
Net Profit       = Operating Profit − Finance Costs − Taxes ± Other Non-Operating Items
```

Do not substitute one level for another.

---

## 23. Cash-flow analysis

**Client cash flows:** deposits received, withdrawals paid, refunds, chargebacks, net client cash flow.

**LP cash flows:** deposits to LPs, withdrawals from LPs, settlement transfers, net LP cash flow.

**Operating cash flows:** salaries, marketing, technology, IB payments, bonuses, payment-provider
settlements, legal/audit/compliance, tax payments.

```text
Free Cash Flow  = Operating Cash Flow − Capital Expenditure
Liquidity Gap   = Available Unrestricted Liquidity − Expected Short-Term Cash Outflows
```

Report liquidity by: today, 7 days, 30 days, 90 days.

---

## 24. Segregated client money and company funds

Where applicable, separately report: segregated client cash, client-equity liability, company
operating cash, company trading cash, restricted cash, LP collateral, unrestricted liquidity.

```text
Client Money Coverage = Eligible Segregated Client-Money Assets / Client-Money Requirement
```

Do not make regulatory conclusions unless the applicable legal framework and definitions are supplied.

---

## 25. Daily and monthly financial dashboards

**Client funds:** deposits, withdrawals, net funding, client balances, client equity, pending
withdrawals, client unrealized profit/loss.

**Revenue:** gross/net B-Book result, spread revenue, commission revenue, swap revenue, markup
revenue, net hedge result, net trading revenue.

**Costs:** LP execution costs, IB expense, bonus cost, cashback cost, payment cost,
negative-balance cost, other direct trading costs.

**C-Book:** allocated capital, trading equity, realized/unrealized/net P&L, effective leverage,
used margin, free margin, current drawdown, capital at risk.

**LPs:** balance / equity / margin / free margin by LP, counterparty exposure, withdrawable cash,
reconciliation differences.

**Company:** gross profit, operating expenses, EBITDA where applicable, operating profit, net
profit, operating cash flow, free cash flow, liquidity gap.

---

## 26. Required reconciliations (mandatory)

```text
# Client balance
Opening Balance + Deposits − Withdrawals + Net Transfers + Realized Trading Result + Credits and Adjustments = Closing Balance

# Client equity
Closing Balance + Unrealized P&L = Closing Equity

# Aggregate
Σ Account Balances = Aggregate Client Balance
Σ Account Equities = Aggregate Client Equity

# Client-book
A-Book Volume + B-Book Volume = Total Classified Client Volume

# B-Book
Gross B-Book Result = Negative of Client Gross P&L on Retained Exposure   (subject to correct allocation and timing)

# Hedge
Internal Hedge Position = LP Confirmed Position   (within documented tolerance)

# LP cash
Internal LP Cash Ledger = LP Statement Cash Balance

# C-Book
Internal C-Book Position = LP Executed and Open Position
```

**Revenue reconciliation** — sum of client-level revenue and cost allocations must reconcile to
the corresponding general-ledger / management-accounting totals where those records are supplied.

---

## 27. Reconciliation-break classification

Every break must have:

```text
break_id
break_type
account_or_lp_id
period
currency
internal_amount
external_amount
difference
materiality
probable_cause
confirmed_cause
status
owner
opened_at
resolved_at
resolution_entry
```

**Causes:** timing difference, missing transaction, duplicate transaction, currency-conversion
difference, symbol-specification error, commission difference, swap difference, unrecorded
journal, incorrect account mapping, LP statement mismatch, unresolved. **Do not eliminate
unresolved items from reports.**

---

## 28. Materiality framework

Configurable at: individual transaction, account, LP, daily, monthly, company level. Do not
hard-code final thresholds unless management/accounting policy provides them. Flag both absolute
and percentage differences. Small differences repeated frequently must also be visible.

---

## 29. Required financial tables

1. Client account financial summary — one row per account per period
2. Client consolidated financial summary — one row per client per period
3. Client funding & cash-flow history — one row per cash transaction
4. Client trading P&L & cost summary — one row per account, symbol and period
5. Client wealth-creation table — deposits, withdrawals, equity, net wealth created
6. Aggregate client-book summary — one row per entity, platform, currency, period
7. A-Book/B-Book allocation table — one row per trade/allocation unit
8. B-Book revenue table — one row per client, symbol, period
9. Spread, commission and swap revenue table
10. IB and rebate expense table
11. Bonus and cashback table
12. Payment-processing cost table
13. Negative-balance cost table
14. Hedge P&L table
15. C-Book financial performance table
16. LP account financial table
17. Counterparty-exposure table
18. Contribution-margin table
19. Company revenue bridge
20. Cash-flow and liquidity table
21. Reconciliation-break table

---

## 30. Required code

Provide reproducible SQL or Python for: client balance reconstruction, equity reconstruction,
deposit/withdrawal classification, internal-transfer elimination, currency conversion, gross/net
P&L, client net wealth created, money-weighted returns, time-weighted returns, B-Book allocation,
B-Book result, hedge P&L, C-Book result, LP cash reconciliation, LP equity reconciliation, margin
calculations, contribution margin, revenue bridge, cash-flow report, reconciliation-break detection.

**Do not use invented production table or field names without marking them clearly as
placeholders (`[PLACEHOLDER]`).**

---

## 31. Unit and reconciliation tests

Create tests for:

1. Account with one deposit and no trades
2. Account with deposit, trade profit and withdrawal
3. Account with trade loss and additional deposit
4. Account with internal transfer
5. Account with bonus and bonus reversal
6. Account with negative-balance adjustment
7. Multi-currency account
8. Partial A-Book and B-Book allocation
9. Partial hedge
10. Client profit offset by hedge profit or loss
11. LP commission and swap
12. Open position with unrealized P&L
13. Month-end open position
14. Chargeback
15. Duplicate cash transaction
16. Missing journal
17. Currency-rate mismatch
18. LP statement mismatch
19. C-Book position mismatch
20. Unresolved reconciliation break

For every test define expected financial outputs.

---

## 32. Required final deliverables

1. Financial methodology document
2. Client account-reconstruction logic
3. Currency-conversion policy
4. Client financial-summary tables
5. Aggregate client-book report
6. A-Book/B-Book allocation report
7. B-Book revenue report
8. Hedging financial report
9. C-Book financial report
10. LP financial and margin report
11. Counterparty-exposure report
12. Client contribution-margin report
13. Company revenue bridge
14. Cash-flow and liquidity report
15. Full reconciliation report
16. Reconciliation-break register
17. SQL or Python calculation library
18. Unit and reconciliation tests
19. List of financial calculations that remain unavailable
20. Exact missing data needed to complete unavailable calculations

---

## 33. Final phase decision

Conclude with one of:

- **FINANCIALS_RECONCILED** — all material financial balances and results reconcile within approved tolerances.
- **FINANCIALS_RECONCILED_WITH_LIMITATIONS** — core balances reconcile, but specific costs, allocations or historical periods remain incomplete.
- **MATERIAL_REMEDIATION_REQUIRED** — material differences or missing data prevent reliable client or C-Book analysis.
- **FINANCIAL_DATA_NOT_RELIABLE** — the financial records cannot currently support the quantitative model.

Do not recommend proceeding to client loss attribution, behavioral classification or C-Book
backtesting unless the core account, client-book, C-Book and LP financial reconciliations are
reliable.
