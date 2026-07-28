# Behavioral Client-Flow C-Book Project
## Phase 3 — Client Classification, Selection & Behavioral Clustering Methodology

> English rendering of the owner-supplied Arabic methodology
> (`الآلية الفنية لتصنيف العملاء واختيارهم وبناء المجموعات السلوكية`). The Arabic `.docx` is the
> source of truth; this file is the working English reference. Technical terms kept in English as
> in the original.
>
> ⚠️ **Read `../audit/PHASE3_FEATURE_FEASIBILITY.md` first.** The single most important capability
> here — directional expectancy / MFE-MAE / Reverse Edge — depends on historical price data this
> CRM does not currently store. Phase 3 does not begin production classification until Phase 2
> reconciliation is reliable (§33 of Phase 2) and the price-history gap is resolved.
>
> **Read-only / no client effect:** classification must NEVER change a client's price or execution
> terms. Its use is confined to analysis, risk management, and investment-signal extraction (§1).

---

## 1. Purpose of classification

Turn a heterogeneous account base into analyzable, testable **behavioral units**. The goal is
**not** merely "who wins / who loses" — the final financial result does not necessarily reveal the
quality of a client's *directional* decisions. A client may lose through over-leverage or poor exit
management despite correct direction; another may profit from one exceptional trade despite weak
habitual decisions.

The system must answer: What is the client's real style? Is behavior stable or shifting? Is loss
driven by direction, timing, size, or exit? On which instrument and horizon does it appear? Is the
account independent or part of a signal source / network? Is its flow suitable to **follow**,
**reverse**, or **watch only**? What is the classification confidence? Which behavioral cluster does
it belong to now?

## 2. Overall structure — seven sequential stages

1. Verify account identity & independence
2. Determine client eligibility for analysis
3. Detect patterns requiring exclusion or separation
4. Compute financial, directional & behavioral features
5. Assign primary and sub-classifications
6. Group similar clients into **Behavioral Clusters**
7. Test each cluster's quality — tradable vs. research-only

Do not advance a stage if the prior stage's data is incomplete or unreliable.

## 3. Real client & linked accounts — three identity levels

Separate **account** from **real client**: one client may hold many accounts, and many accounts may
execute from one signal source. Treating each account as independent can fabricate "strong group
agreement" that is really one decision.

- **Account level** — each Account ID separately (its data, performance, positions).
- **Client level** — accounts owned by the same legally-known, authorized person/entity.
- **Linked-behavior-network level** — accounts possibly owned by different people but executing the
  same strategy/signal (copy accounts, networks, a single EA).

Linkage evidence: similar entry/exit times; matching symbols & directions; close execution prices;
stable volume ratios between accounts; shared Device / IP / API source (where lawful to use); one
agent or Copy Provider; the same pattern repeating over a long period. **Never prove linkage from a
single variable** — build a **Linked Account Confidence Score**. When counting signal participants,
treat a linked network as one entity (or reduced weight) so group strength is not artificially
inflated.

## 4. Client eligibility for analysis

Do not classify on few trades or a short window. Proposed initial thresholds: ≥ 90 days of activity;
≥ 100–150 closed trades (day-trading); ≥ 30–60 active days; activity spread over more than one
month; sufficient volume for stable metrics; price/execution/account data available; no high share
of missing/unreconcilable data. Swing traders may pass with fewer trades if history is longer and
spread across different market regimes.

Do not rely on trade count alone — 500 trades in 3 days of automated scalping lacks temporal
diversity. Build a **Data Sufficiency Score** from: trade count, period length, active days/weeks,
market-condition diversity, data completeness, instrument diversity / main-instrument stability,
sample size after removing outlier trades. A client enters production classification only after
passing the minimum Data Sufficiency Score.

## 5. Clients to separate or exclude

Exclusion means *not entering the core strategy* (or moving to a specialized cluster), **not**
deletion. Separate:

- **New accounts** → `INSUFFICIENT_HISTORY` until a sufficient sample exists.
- **Arbitrage / latency exploiters** → results tied to execution structure, not market direction.
- **News traders** → distinct volatility/slippage/gap characteristics → own group.
- **Martingale users** → loss is not automatic proof of weak direction; analyze in a dedicated group.
- **Grid users** → treat the grid as a composite position, not independent directional decisions.
- **High-frequency scalpers** → loss may be cost/slippage, not weak prediction → separate.
- **Non-independent accounts** → grouped into a Linked Group, not counted as independent members.
- **Recently strategy-changed accounts** → `RECLASSIFICATION_HOLD` until enough new-behavior data.
- **One-exceptional-trade results** → lower confidence until behavior persists after outlier removal.

## 6. Client analysis levels

A client should not have a single account-wide label. Analyze at four levels: **overall** (all
instruments); **asset class** (FX, gold, indices, energy, crypto); **symbol** (weak in XAUUSD but
good in EURUSD); **time horizon** (good directionally in the first 15 min, loses when holding 4 h).
Result e.g.: "directionally weak in gold in the first hour, neutral in FX, primarily poor exit in
swing trades" — far more precise than "losing client."

## 7. Required features (six groups)

**7.1 Financial performance** — Net P&L, Profit Factor, Win Rate, Average Win, Average Loss, Payoff
Ratio, Expectancy, Maximum Drawdown, Recovery Factor, % winning days/weeks/months, profit
concentration in largest trades, performance after removing the best trade and best 5 trades.
*(Describes the result, not its cause.)*

**7.2 Directional** *(most important for deciding reverse-suitability)* — Directional Accuracy at
5 min / 15 min / 1 h / 4 h / 1 day; Directional Expectancy per horizon; % of trades that first moved
in the client's direction; average MFE; average MAE; time-to-MFE and time-to-MAE.

**7.3 Timing** — entry location within the price move; % entering after a large extension; time
between move start and entry; % entering near local tops/bottoms; session timing; timing
before/after news; how late the client responds to price movement.

**7.4 Size & leverage** — average size relative to equity; effective leverage; largest leverage
used; size change after loss; size change after win; number of position add-ons; ratio of last
add-on to first trade; approximate distance to stop-out; risk size vs. balance.

**7.5 Position management** — Stop Loss usage %; stop removal/widening %; Take Profit usage %;
Profit Capture Ratio; Giveback Ratio; % of trades that flipped from profit to loss; average holding
time for winners vs. losers; early profit-taking; excessive loss-holding.

**7.6 Stability** — consistency of instruments, timeframe, size, trading hours, add/exit strategy;
performance change across time windows; number of pattern changes; probability of a Strategy Change.

## 8. Variable preprocessing (before clustering)

Never feed raw features into clustering — scale differences and outliers dominate. Apply:
**outlier treatment** (do not auto-delete — an outlier may be meaningful, e.g. martingale; use
Winsorization / Median & MAD / Percentile Capping / robust statistics); **log transform** for
heavily-skewed variables (lot size, deposits, hold time); **standardization** preferring **Robust
Scaling** over Standard Scaling when extreme values exist; **missing-data handling** — do not
replace all missing with zero; distinguish "no Stop Loss used" from "stop data missing," "no swap"
from "swap data unavailable"; store a separate **Missing Indicator** when needed; **per-instrument
normalization** — a $10 move in gold ≠ 10 pips in EURUSD.

## 9. Base (rule-based) classifications

Before clustering, build clear rule-based labels using market knowledge. A client may hold several
at once: **Directional Weakness**, **Late Entry Behavior**, **Poor Exit Discipline**,
**Over-Leveraged Trader**, **Martingale Trader** (via Martingale Score), **Grid Trader** (via Grid
Score), **News Trader**, **Scalper**, **Trend Follower**, **Contrarian Trader**, **Strategy
Unstable**. (Definitions per the original — e.g. Directional Weakness = stable negative forward
return across multiple horizons after removing size & cost effects.)

## 10. Loss attribution

Produce a **Loss Attribution Profile** per client, distributing loss causes over five axes summing
to 100%: **Direction Error**, **Entry Timing Error**, **Position Sizing Error**, **Exit Management
Error**, **Transaction Cost Burden**. A client suitable for the *reverse* strategy must have high
Direction / Late-Entry contribution. If loss is mainly leverage or exit, **do not reverse** the
client — even if the account loses consistently.

## 11. Client score model

Produce **multiple separate scores**, not one: Directional Weakness, Timing Weakness, Exit Weakness,
Over-Leverage, Martingale, Grid, News Trading, Scalping, Strategy Stability, Classification
Confidence, Data Sufficiency, Linked Account Risk. Each 0–100. Never compute one "Loss Score" and
reuse it for all strategies — each strategy needs different information.

## 12. Cluster-building strategy — Hybrid (three layers)

1. **Rule-Based Segmentation** — pre-separate clear patterns (News, Martingale, Grid, HF Scalpers,
   Copy Networks, Long-Term Swing) so the algorithm never merges radically different behaviors.
2. **Unsupervised Clustering** — within each main segment, discover sub-patterns. Test K-Means, GMM,
   Hierarchical, DBSCAN/HDBSCAN, Spectral. Choose by separation quality, stability, interpretability
   — not popularity.
3. **Supervised Assignment** — after clusters are approved, train a classifier to assign new /
   reclassified clients to the nearest stable cluster (no full re-clustering per new trade).

## 13. Why not K-Means alone

K-Means assumes roughly circular, similar-size groups, is outlier-sensitive, and forces every client
into a group. Use as a baseline only. Prefer **HDBSCAN** for irregular groups, outlier clients,
unknown cluster count, and the need to leave some clients unassigned. Use **GMM** when soft
(probabilistic) membership across multiple groups is desired.

## 14. Multi-layer clustering

Do not build one global cluster per client. Build **local** clusters by asset class, symbol, time
horizon, session, trading style (Multi-View / Multi-Layer). A client may belong to "Gold Late
Entrants – Short Horizon", "EURUSD Neutral Direction – Intraday", and "High Leverage – All Symbols"
simultaneously.

## 15. Example target clusters

Gold Late Long Entrants; High-Leverage Directional Losers; Profitable Trend Followers; Poor Exit but
Good Direction *(not reverse-suitable)*; Martingale Breakdown Candidates *(usable for forced-close
timing strategy)*; News Chasers; Random/Unstable Traders *(kept out of strategies)*.

## 16. Cluster quality conditions

A cluster is not valid just because the algorithm made it. Evaluate on four axes: **internal
homogeneity** (Silhouette, Within-Cluster Variance, Davies–Bouldin, Cluster Homogeneity Score);
**separation** from other clusters (merge if no substantive behavior/forward-return difference);
**temporal stability** (a similar cluster reappears on different periods; noise if it vanishes when
the month/year changes); **investment value** (must provide useful information out-of-sample —
statistical homogeneity alone is not an Edge).

## 17. Minimum cluster size

Not raw account count alone. Set: min real clients; min effective count after weighting; min
historical signals; min trades; max largest-client concentration; max top-10 concentration; max
linked copy-networks. Initial research bounds: **≥ 25 independent clients**, **Effective Client
Count ≥ 15**, **largest client ≤ 5%**, **top-10 ≤ 35%** — tuned after testing.

## 18. Cluster validity for the reverse strategy

For **Reverse Behavioral Crowding**, a cluster must prove: directional weakness (not just financial
loss); persistence across multiple time windows; a group effect stronger than individuals'; improved
results when adding price confirmation; positive return after all execution costs; results not
dependent on a few clients; not unjustifiably dependent on one period/instrument; out-of-sample
stability; a clear signal lifetime; a clear cancellation threshold.

Compute the cluster's **Reverse Edge** = average return from reversing the group's direction (after
confirmation conditions) minus all execution costs. If positive only *before* costs, the cluster is
**not** live-tradable.

## 19. Client selection within a cluster

Not equal weight. Client weight from: Data Sufficiency, Classification Confidence, Directional
Weakness, Strategy Stability, Independence Score, Consistency across Windows, Symbol Relevance. Then
apply a cap so no client dominates. Conceptually: `initial weight = confidence × behavior stability ×
symbol relevance`; then apply concentration limits and renormalize to 100% within the group. Do not
weight a client higher merely for losing more money (loss size may reflect account size).

## 20. Cluster entry rules

A client enters when it: passes min Data Sufficiency; passes min Confidence; is close enough to the
cluster center; keeps matching cluster characteristics across more than one review cycle; is not in
an exclusion class; has not recently changed strategy; does not push concentration over limits.
Prefer a **stability condition** (e.g. eligible for two consecutive cycles before production entry)
to avoid entry on short-lived noise.

## 21. Cluster exit rules

A client exits / is frozen when: confidence drops; strategy changes; directional performance shifts
substantively; the account links to a new network; it moves to a different instrument/timeframe; its
data becomes incomplete; it raises group concentration; it is no longer near the cluster center;
another group's characteristics appear stably. **Exit must be faster than entry** on a substantive
change — a stale member can spoil the signal.

## 22. Reclassification periodicity — three speeds

**Feature updates** — daily or intraday per variable. **Score recomputation** — daily. **Class /
membership change** — weekly or monthly by client activity, except a material event forcing immediate
freeze. Do not change clusters after every trade — that produces unstable membership and
uninterpretable testing.

## 23. Strategy-change detection

Build a **Strategy Change Detector** watching feature-distribution drift: large change in hold time;
instrument change; activity-hours change; size change; stop-usage change; emergence of martingale /
grid; increased similarity to other accounts; order source changing Manual → EA/API. Methods:
Population Stability Index, KL Divergence, Change-Point Detection, Rolling Z-Scores, distance-to-
cluster-center comparison. On breach → client enters `REVIEW` or `FROZEN`.

## 24. Membership-stability measurement

Measure: % of clients remaining group-to-group; average membership duration; inter-group transition
rate; returnees after exit; drift of the cluster center itself. Excessive membership change ⇒ unclear
cluster or unstable variables. Use a **Cluster Stability Score** 0–100.

## 25. Preventing future-data leakage

In backtests, determine a client's classification & membership using **only data available before the
signal**. Never label a client "Directional Loser" using trades executed *after* the signal date.
Store: feature-computation time, classification-approval time, version used, cluster entry time,
cluster exit time. The backtest uses the **last classification actually known at each event**.

## 26. Out-of-sample validation

After building clusters on a development period, test them on a period not used in their formation.
Measure: persistence of behavioral characteristics, membership stability, directional return, Reverse
Edge, signal count, costs, concentration, drawdown. If a cluster loses its value out-of-sample, it is
not adopted regardless of in-sample quality.

## 27. Post-deployment cluster monitoring

Each cluster gets a **Dashboard**: raw client count; real client count; Effective Client Count;
exposure size; net direction; Crowding Ratio; HHI; largest client; top-10; average entry price;
Floating P&L; Directional Accuracy; Directional Expectancy; Reverse Edge; average signal age;
performance over last 30 / 90 / 180 days; cluster state (Active / Watch / Suspended / Retired).

## 28. Cluster lifecycle states

**Research** (discovered, unproven) → **Validated** (passed historical & out-of-sample) → **Shadow**
(generates signals on live data without execution) → **Active** (allowed within a defined strategy) →
**Reduced** (low weight due to decay) → **Suspended** (temporarily halted) → **Retired**
(permanently). A cluster must never jump Research → Active directly.

## 29. Recommended first version

Do not start with complex automated clustering. Sequence: detect linked accounts → separate News /
Martingale / Grid / Scalping → split clients by symbol & horizon → measure Directional Weakness, Late
Entry, Exit Weakness → build clear Rule-Based groups → test each group's investment value → use
statistical clustering only inside large groups → build a Supervised Assignment model after groups
stabilize. This reduces the risk of statistically-pretty but uninterpretable, untradeable groups.

## 30. Top rule of classification & clustering

A client is not chosen because it lost, nor rejected because it won. It is chosen on: behavior type;
cause of result; pattern stability; fit to instrument & horizon; independence from other accounts;
data sufficiency; predictive value added to the group. A cluster becomes investable only if it
provides a clear, stable **Edge after costs**, remaining interpretable and validated out-of-sample.

**Correct pipeline:** raw accounts → remove linkages → data eligibility → financial + directional +
behavioral features → base classifications → hybrid clustering → homogeneity & stability testing →
investment-value testing → Shadow Mode → limited production use.
