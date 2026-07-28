# Behavioral Client-Flow C-Book Project

A **read-only, analysis-and-classification-only** research project layered on top of the
TNFX CRM. Its purpose is to build a financially reconciled, auditable foundation for
understanding client trading flow, classifying it (A-Book / B-Book / hedge / C-Book), and
researching a C-Book strategy.

> ⚠️ **SAFETY — this section NEVER acts on clients or real money.**
> Nothing in `cbook/` opens, closes, modifies, freezes, or routes any real position, order,
> account, balance, bonus, or transaction. It only **reads** validated data, **computes**
> financial facts, and **produces** reports, tables and classifications. Any future execution
> would be a separate, explicitly-gated project — out of scope here.

---

## What a C-Book is (working definition for this project)

- **A-Book** — client flow is passed to the market / liquidity provider. Broker holds no
  market risk; earns spread + commission.
- **B-Book** — broker is the counterparty. Client loss = broker revenue, client profit =
  broker cost. Full market risk retained.
- **C-Book** — the hybrid: the broker **nets client exposure per symbol and takes its own
  market position to match it**, at a configurable hedge ratio, to control how much B-Book
  risk it warehouses vs. hedges.

This project does not run a C-Book. It builds the **financial and behavioral foundation**
needed to research one.

---

## Phases

| Phase | Name | Status |
|------|------|--------|
| **1** | Data Inventory, Feasibility & Quality Audit | ⏳ Partially done — see `audit/DATA_AVAILABILITY_MAP.md` |
| **2** | Financial Facts, Accounting Logic & Reconciliation | 🔨 In progress — spec in `docs/PHASE2_FINANCIAL_RECONCILIATION.md`; §5 built |
| **3** | Client Classification, Selection & Behavioral Clustering | 📋 Spec loaded — `docs/PHASE3_BEHAVIORAL_CLASSIFICATION.md`; feasibility in `audit/PHASE3_FEATURE_FEASIBILITY.md`; gated on Phase 2 + price-history gap |
| 4+ | C-Book strategy research & backtesting | 🔒 Not started |

**Phase 2 begins only after Phase 1 blockers are documented.** The most important Phase-1
finding so far: large parts of Phase 2 (LP accounts, hedging, real book classification, FX
conversion, payment costs, company operating/cash-flow) have **no data source** in this CRM.
See the data availability map before building any calculation.

---

## Working rules (from the Phase 2 spec — always apply)

1. **Do not invent** any figures, balances, costs, FX rates, journal entries or account
   relationships.
2. Use **only validated data sources** (see `audit/DATA_AVAILABILITY_MAP.md`).
3. Every derived figure must be **traceable to source transactions**.
4. Every reconciliation difference must be **reported explicitly** — never forced to balance.
5. Unavailable calculations are listed as **unavailable**, with the exact missing data named.
6. Any table/field name that does not exist in the real schema is marked **`[PLACEHOLDER]`**.

---

## Section layout

```
cbook/
├── README.md                                  ← this file (charter + safety + status)
├── STATUS.md                                  ← step-by-step work tracker (33 areas / 21 tables / 20 deliverables)
├── docs/
│   ├── PHASE2_FINANCIAL_RECONCILIATION.md     ← Phase-2 methodology spec
│   └── PHASE3_BEHAVIORAL_CLASSIFICATION.md    ← Phase-3 classification & clustering methodology
├── audit/
│   ├── DATA_AVAILABILITY_MAP.md               ← Phase-1↔2 bridge: financial sources vs. schema
│   └── PHASE3_FEATURE_FEASIBILITY.md          ← Phase-3 features vs. schema (price-history gap)
├── lib/                                       ← read-only calculation library (§5 built)
├── sql/                                       ← read-only SQL (views + reports)
└── tests/                                     ← unit & reconciliation tests
```

Code, SQL and reports are added **incrementally, one work area at a time**, only for
calculations whose data actually exists. See `STATUS.md` for what's next.
