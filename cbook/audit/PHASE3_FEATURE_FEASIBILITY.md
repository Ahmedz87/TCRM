# Phase 3 — Feature Feasibility vs. Real Data

Maps the Phase 3 behavioral features (§7), classifications (§9) and cluster tests (§18) against
what the CRM actually stores. Same discipline as Phase 2: anything ❌ MISSING is **not fabricated**
— the dependent feature is UNAVAILABLE until its data source is added.

**Legend:** ✅ computable now · 🟡 partial / needs work or verification · ❌ MISSING (no source)

---

## Headline finding

`deals` supports **round-trip trade reconstruction** (`entry` = in/out/reverse, `direction`,
`price`, `volume`, `deal_time`, `symbol`, `profit`, `commission`, `swap`). That unlocks *behavioral*
features — hold time, sizing patterns, martingale/grid, sessions, exit-giveback, stability, linked
networks.

But there is **no historical price series** (no tick / quote / OHLC / candle table anywhere), and
**no SL/TP fields** on deals. Therefore the **directional group (§7.2) — MFE/MAE, directional
expectancy at horizons, "moved in client's direction first" — and the Reverse Edge (§18) cannot be
computed.** That group is, by the methodology's own words, "the most important for deciding whether a
client is suitable for reversing." **The reverse-crowding investment thesis is blocked on price data.**

| Capability | Verdict |
|---|---|
| Identity & linked-account detection (§3) | ✅ computable |
| Data-sufficiency gating (§4) | ✅ computable |
| Exclusion detection: martingale / grid / scalper / session-based news (§5) | 🟡 mostly computable |
| Financial-performance features (§7.1) | ✅ computable (from paired trades) |
| **Directional features (§7.2)** | ❌ **MISSING — needs price history** |
| Timing features (§7.3) | 🟡 sessions/news-window ✅; "location within move" ❌ (price history) |
| Size & leverage features (§7.4) | ✅/🟡 sizing ✅; distance-to-stop-out 🟡 |
| Position-management features (§7.5) | 🟡 hold-time & giveback ✅; SL/TP usage ❌ (or from raw_json) |
| Stability features (§7.6) | ✅ computable |
| Loss Attribution (§10) | 🟡 Sizing/Exit/Cost axes computable; **Direction/Timing axes blocked** |
| Rule-based classifications (§9) | 🟡 behavior labels ✅; Directional Weakness / Late Entry / Trend / Contrarian ❌ |
| Clustering machinery (§12–§24) | ✅ buildable (on whatever features are available) |
| Point-in-time / no-leakage (§25), OOS (§26) | ✅ buildable |
| **Reverse Edge & reverse-validity (§18)** | ❌ **MISSING — needs forward returns = price history** |

---

## Detail by feature group

### §3 Identity & linked accounts — ✅
- Round-trips, times, symbols, directions, volume ratios → from `deals`.
- Shared IP / CID / MQID → `account_identifiers`. Copy relationships → `copy_trade_relations`,
  `copy_trade_masters`, `network_edges`, `clients.agent` (IB). Enough to build a **Linked Account
  Confidence Score**.

### §4 Data sufficiency — ✅
- Trade count, active days/weeks, history span, instrument diversity → all from `deals` timestamps.

### §5 Exclusion classes — 🟡
- Martingale/Grid → from size-after-loss and repeated entry spacing (paired trades). ✅
- Scalper → hold time + trade frequency + target behavior. ✅
- News trader → **session/time-window** proxy only (we have `deal_time`); a real economic-calendar
  feed is not in the CRM → 🟡 (time-window heuristic, not true news alignment).
- Arbitrage/latency → hard to prove without tick-level execution vs. quote → 🟡/❌.

### §7.1 Financial performance — ✅
- Net P&L, Profit Factor, Win Rate, Avg Win/Loss, Payoff, Expectancy, Max Drawdown (from equity
  curve via `balance_after` / paired P&L), Recovery Factor, win-rate by day/week/month, profit
  concentration, performance-minus-best-N. All from paired closed trades + §5 reconstruction.

### §7.2 Directional — ❌ (the critical gap)
- Directional Accuracy / Expectancy at 5m/15m/1h/4h/1d, %-moved-in-direction-first, MFE, MAE,
  time-to-MFE/MAE **all require the price path during and after each trade.** No tick/bar history
  exists → **UNAVAILABLE.**

### §7.3 Timing — 🟡
- Session timing, before/after-news *window*, entry hour → ✅ (`deal_time`).
- Entry location within the move, % after large extension, delay after move start, near local
  tops/bottoms → ❌ (price history).

### §7.4 Size & leverage — ✅ / 🟡
- Size vs. equity, effective leverage (`clients.leverage` + volume × contract size), size-after-
  win/loss, add-on count, last/first add-on ratio → ✅.
- Approx distance to stop-out → 🟡 (needs margin snapshot at trade time; only live margin stored).

### §7.5 Position management — 🟡
- Hold time (winners vs. losers), Profit Capture / Giveback, %flip profit→loss, early profit-taking,
  loss-holding → ✅ from paired trades + `balance_after`.
- Stop Loss / Take Profit usage & stop removal/widening → ❌ no SL/TP columns. **Possible** from
  `mt5_raw_data.raw_json` (data_type='position') if SL/TP were captured — **needs verification**.

### §7.6 Stability — ✅
- Instrument/timeframe/size/hours/strategy consistency, performance across windows, pattern-change
  count → from rolling windows over `deals`.

### §10 Loss attribution — 🟡
- Position Sizing, Exit Management, Transaction Cost axes → computable.
- **Direction Error, Entry Timing Error axes → blocked** (need §7.2). So the profile cannot be
  completed, and **reverse-suitability cannot be judged**, until price history exists.

### §18 Reverse Edge — ❌
- "Average return from reversing the group's direction after confirmation, minus costs" is a
  **forward-return** measurement → requires price history at and after each signal. UNAVAILABLE.

---

## Missing-data register (Phase 3)

To unlock the blocked capabilities, source the following:

1. **Historical price series** — tick or 1-minute OHLC for every traded symbol, spanning the trade
   history, timestamp-aligned to `deals.deal_time`. *(Unlocks §7.2 directional, §7.3 location,
   §10 direction/timing axes, §18 Reverse Edge — i.e. the entire investment thesis.)*
2. **Per-trade SL/TP** — stop-loss / take-profit levels and modifications (from MT position records
   / `mt5_raw_data.raw_json`, or a broker export). *(Unlocks §7.5 stop discipline.)*
3. **Economic calendar** — timestamped high-impact events. *(Turns the news-window heuristic (§5,
   §7.3) into true news alignment.)*
4. **Margin-at-trade snapshots** — for accurate distance-to-stop-out (§7.4).

> **Sequencing:** Phase 3 also inherits the Phase 2 gate — do not begin production classification
> until Phase 2 core reconciliation is reliable (Phase 2 §33). Behavioral/stability features (§7.1,
> 7.4–7.6, §9 behavior labels, clustering machinery) can be prototyped now; directional/reverse
> capabilities wait on item 1 above.
