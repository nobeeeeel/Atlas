# Atlas Architecture

**Current release:** Atlas 1.30.19 · Nyao 44.3

This document is the canonical technical architecture for Atlas. It
describes system boundaries, authority, risk accounting, execution flow
and persistent state. Historical development-phase documents are
intentionally excluded from the repository.

## 1. Design principles

Atlas is built around five principles:

1.  **Deterministic risk is authoritative.** AI reasoning may advise but
    cannot bypass hard capital, broker or execution constraints.
2.  **Risk is measured as strategic units, not ticket count.** Recovery
    chains and zone campaigns are composite objects.
3.  **Capital is allocated, not globally locked.** Existing exposure
    reserves capacity; it does not automatically prevent independent
    opportunities.
4.  **Execution economics matter.** A strong signal is insufficient when
    spread, structure or required trade expansion destroys the intended
    edge.
5.  **MT5 is authoritative for broker truth.** Actual volume
    constraints, positions, deals and realised P/L come from the
    execution environment.

## 2. System boundary

### Atlas owns

-   market/regime interpretation;
-   deterministic strategy eligibility;
-   capital regime and risk appetite;
-   concurrent portfolio allocation;
-   zone geometry and campaign authority;
-   recovery-chain risk ceilings;
-   composite outcome accounting;
-   loss protection and drawdown governance;
-   policy evidence and AI review boundaries.

### Nyao owns

-   MT5 connectivity;
-   broker symbol specifications;
-   live bid/ask and spread telemetry;
-   broker-aware lot calculation;
-   final `OrderCalcProfit` feasibility;
-   order placement and modification;
-   position management and exit execution;
-   immutable entry lineage written into MT5 comments;
-   authoritative position/deal telemetry back to Atlas.

### Gemini / Atlas Brain may

-   analyse evidence;
-   compare policy candidates;
-   reason about regimes and performance;
-   propose or apply permitted Nyao policy changes according to the
    configured review mode.

It may not override deterministic Atlas risk authority.

## 3. End-to-end decision flow

``` text
MT5 market state
    │
    ▼
Nyao telemetry
    │
    ▼
Atlas market/regime model
    │
    ├─ signal score
    ├─ structure
    ├─ zone context
    └─ volatility
    │
    ▼
Execution economics
    │
    ├─ spread / ATR
    ├─ spread / stop
    ├─ spread / target
    ├─ stop expansion
    └─ structure feasibility
    │
    ▼
Capital + portfolio allocator
    │
    ├─ operator hard ceiling
    ├─ operating governor
    ├─ active reservations
    ├─ concentration
    └─ candidate risk budget
    │
    ▼
Nyao final broker feasibility
    │
    ▼
Order / management / recovery
    │
    ▼
MT5 deals and positions
    │
    ▼
Atlas outcome + learning ledger
```

## 4. Capital model

### 4.1 Operator risk appetite

The operator owns the absolute aggregate portfolio ceiling:

``` text
1% <= portfolio_hard_risk_pct <= 20%
```

Default: **1%**.

The setting is persistent per Atlas account/symbol context and
represents maximum aggregate strategy risk, not per-trade risk.

Atlas and Gemini may reduce effective risk but cannot increase the
operator-owned value.

### 4.2 Capital regimes

Atlas derives base scalp and zone risk from the current capital regime.
These are per-opportunity starting budgets and remain separate from the
aggregate portfolio ceiling.

The engine then applies deterministic modifiers such as: - drawdown; -
loss streak/protection state; - market risk state; - volatility.

### 4.3 Hard versus operating ceiling

``` text
portfolio hard ceiling
        │
        └─ operator-owned maximum

operating ceiling
        │
        └─ currently deployable envelope after Atlas modifiers
```

A 20% configured hard ceiling does not imply Atlas should seek 20%
exposure. The operating governor may be substantially lower.

### 4.4 Concurrent allocation

Active risk is represented by reservations.

``` text
operating ceiling
- active risk reservations
- working-order reservations
= remaining operating capacity
```

A candidate is clipped or vetoed if its deterministic risk cannot fit
the remaining envelope.

Allocation states include: - `AVAILABLE` - `PARTIALLY_ALLOCATED` -
`FULLY_ALLOCATED` - capital/protection veto states

### 4.5 Concentration

Same-symbol exposure receives no diversification credit. Opposing
positions are not assumed to eliminate risk because unequal volume, stop
geometry and recovery behaviour can still create material downside.

## 5. Composite risk-unit model

### Standalone trade

One independent trade is one risk unit.

### Recovery chain

A root plus every recovery/hedge child sharing immutable lineage is one
risk unit.

Member exits are provisional while any member remains active. The
strategic result is determined only when the entire chain is flat using
authoritative realised P/L where available.

### Zone campaign

All zone layers sharing the same immutable zone-plan token form one risk
unit. Layer exits do not independently alter strategic loss streaks
while the campaign remains active.

### Loss streaks

Only completed eligible risk units affect the strategic completed-loss
streak. Active composite units are unscored.

## 6. Recovery architecture

A recovery chain has its own sandboxed authority.

``` text
original unit risk
× recovery expansion multiplier
= candidate chain ceiling

candidate ceiling
clipped by explicit chain/portfolio constraints
= frozen chain ceiling
```

Every additional recovery leg must fit inside that same frozen ceiling.
A chain cannot consume unrelated unallocated portfolio capacity simply
because it is available.

### Durable recovery ledger

Recovery sizing events are persisted with: - chain ID; - event
sequence; - original unit risk; - anchor loss; - budget basis; - chain
ceiling; - remaining capacity; - requested/capped/final lot; - estimated
adverse risk; - evaluation timestamp and reason.

### Active-chain adoption

If Atlas/Nyao restarts while a recovery chain already exists and no
durable budget is available, Atlas reconstructs a conservative finite
authority before further expansion is allowed. Original stop risk is
preferred when recoverable; otherwise a conservative observed-loss basis
is used. If no safe budget can be established, additional recovery
expansion is blocked.

## 7. Dynamic execution economics

Atlas treats transaction cost as a structural input rather than a single
fixed spread cap.

Scalp feasibility evaluates: - current spread; - ATR and average ATR; -
intended base stop and target; - spread-to-stop ratio; -
spread-to-target ratio; - required stop/target expansion; - planned stop
relative to ATR; - whether the adapted geometry still represents the
intended scalp.

This prevents a pathological solution where Atlas makes the stop
arbitrarily large merely to make the spread ratio appear acceptable.

Typical structural rejection reasons include cost/structure mismatch and
excessive required expansion. Capital availability does not override
this gate.

## 8. Zone architecture

Atlas builds deterministic zone context from market structure and candle
history. Zone execution considers: - side and timeframe; - zone
quality/freshness; - confirmation; - layer geometry; - capital budget; -
broker feasibility; - existing campaign identity.

A valid existing unrelated risk unit does not automatically block a new
zone campaign when sufficient portfolio capacity remains. A continuing
zone campaign retains its immutable plan identity.

## 9. Outcome authority and lineage

Atlas prefers authoritative MT5 exit deals for realised P/L. The outcome
pipeline supports: - exact realised profit, swap, commission and fee
aggregation; - reconstruction of trades that open and close between
Atlas polls; - policy-epoch attribution at entry; - immutable
recovery-chain lineage; - immutable zone-plan lineage; - conservative
legacy inference when historical metadata predates current telemetry.

Inferred legacy outcomes remain distinguishable from exact authoritative
outcomes.

## 10. Policy and AI authority

Atlas Brain receives deterministic context including market
intelligence, capital sizing, zone state and performance evidence.

AI output is subordinate to the following authorities: - operator
portfolio risk appetite; - capital regime engine; - concurrent portfolio
allocator; - zone policy and geometry; - broker feasibility; -
recovery-chain ceiling; - loss/drawdown protection; - final MT5
execution constraints.

AI can improve policy within the allowed control surface; it cannot
redefine the safety envelope.

## 11. Persistent state

Important persistent state includes account/symbol-scoped files for: -
commands and policy epochs; - trade outcomes; - composite risk units; -
recovery risk ledger; - capital/loss-protection recovery state; -
operator risk appetite; - market/candle context where applicable.

Persistent state must preserve authority across process restarts and
prevent a restart from silently resetting risk ownership.

## 12. API surfaces

Key runtime surfaces include:

``` text
/api/v1/nyao/status
/api/v1/atlas/capital-sizing
/api/v1/atlas/recovery-risk
/api/v1/atlas/risk-appetite
```

Additional Atlas endpoints expose intelligence, zones, outcomes, policy
review and operational state. API responses should distinguish current
active authority from historical/last-event telemetry.

## 13. Safety invariants

1.  Aggregate deterministic risk must never exceed the operator hard
    ceiling.
2.  Atlas may reduce operator risk appetite but may not autonomously
    raise it.
3.  Recovery expansion must remain within the chain's frozen ceiling.
4.  Minimum broker volume must never be reached by rounding an unsafe
    calculated lot upward.
5.  Composite members must not independently contaminate strategic loss
    streaks.
6.  Active risk must reserve capital before another opportunity is
    admitted.
7.  Same-symbol concurrency must not receive false diversification
    credit.
8.  Strong signal score does not override poor execution economics.
9.  High leverage affects margin availability, not permitted monetary
    loss.
10. MT5 broker truth remains final at execution.

## 14. Documentation policy

This file is the single canonical architecture document. New
architectural capabilities should update this document rather than
create phase-specific architecture files. Temporary implementation
phases, migration scripts and test packages should not become permanent
repository documentation.
