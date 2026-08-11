# Atlas Architecture

**Current release:** Atlas 1.30.57 · Nyao 44.6.2

### Recovery lifecycle & hedge profit integrity (1.30.57)

Atlas/Nyao now treats every unresolved rolling-hedge lifecycle as one book-level risk unit until flat. Independent fresh/zone entries are locked during any active recovery composite, not only RECOVERY_PROBE. Active HEDGE_CHILD legs receive broker-side profit protection before ordinary chain logic can allow a large positive MFE to reverse into a loss; if a protected hedge disappears, the surviving leg graduates with no-rehedge authority rather than immediately starting another uncontrolled cycle. Position management now uses MT5 `POSITION_PRICE_CURRENT` as the primary management mark, with the broker still the final SL authority, because live diagnostics exposed large divergence between position marks and raw symbol quotes. Capital reservations are also reconciled from immutable risk-unit lineage so a graduated survivor remains reserved as `recovery:<root>` instead of being misclassified as a standalone trade.


### Gemini directional-context normalization (1.30.56)

Atlas now normalizes common Gemini directional aliases before strict Pydantic validation: `BULLISH`/`LONG` -> `BUY`, `BEARISH`/`SHORT` -> `SELL`, mixed/bidirectional -> `BOTH`, and neutral/unknown -> `NONE`. The canonical stored schema remains `BUY | SELL | BOTH | NONE`; malformed unrelated values still fail validation. Nyao is unchanged at 44.6.1 because this is a backend policy-proposal parser hotfix.

### Recovery chain risk integrity (1.30.54)

The 1.30.54 package also enforces recovery-lifecycle atomicity: any unresolved immutable `RECOVERY_PROBE` lifecycle locally locks independent fresh entries in Nyao, the backend independently vetoes fresh risk while the composite is active, and root/child outcomes are scored only once after the whole composite is flat. A closed RP root is still linked to live historical children through durable root lineage; transient child closures cannot start a new loss-protection stage.

- Recovery-probe admission is re-priced again from the **actual broker fill**, actual broker SL, actual volume, and live equity. An adverse fill that makes the probe exceed the 0.30% cap is immediately emergency-closed.
- `RECOVERY_PROBE` is a deliberately single-leg diagnostic state. It cannot spawn `HEDGE_CHILD` rolling-hedge legs; ordinary non-probe recovery chains are unchanged.
- Debug integrity now exposes `RECOVERY_PROBE_SINGLE_LEG_INVARIANT` in addition to the active probe risk-envelope check.

### Startup risk authority integrity (1.30.52)

Fresh-entry authority is fail-closed during Atlas/Nyao startup and redeployment. Atlas publishes a `STARTUP_RISK_RECONCILIATION` barrier before reconstructing account identity, outcomes, loss protection, capital sizing and operator risk appetite; Nyao refuses pre-start directives and enables new entries only after a post-start reconciled directive arrives. Operator risk appetite is persisted outside the replaceable source tree under the MT5 Atlas bridge.

## Recovery-probe invariant (1.30.51)

A recovery probe is a distinct immutable entry lineage, not an ordinary fresh scalp. Nyao owns the broker-survivable `RP` entry identity and final `OrderCalcProfit` admission check; Atlas restores loss-protection state from that live lineage and scores the completed probe as separate `RECOVERY_PROBE` performance evidence. The maximum permitted loss is frozen at admission and may only contract during management.

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

### 4.4 Adaptive opportunity allocation

Atlas converts the current operating envelope into bounded candidate budgets. Capital-regime scalp/zone values remain conservative floors, while setup quality may authorize a larger share of available operating capacity. Scalp opportunities remain capped at 2% of risk capital and zone campaigns at 3%, independently of the aggregate operator ceiling. Eligibility gates remain separate from sizing authority.

### 4.5 Concurrent allocation

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

### 4.6 Concentration

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

## 7.1 Campaign-aware zone execution economics

Zone spread feasibility is derived from the shared-stop risk distance and the active leg target distance using bounded dynamic ratios informed by zone quality, confirmation progress, campaign reward/risk and volatility context. A direct `ATR × fixed ratio` cap is no longer authoritative because it can collapse during quiet markets even when the campaign geometry is much larger. ATR remains diagnostic context and can tighten the quality multiplier without acting as a standalone hard veto.

## 8. Zone architecture

Atlas builds deterministic zone context from market structure and candle
history. Zone execution considers: - side and timeframe; - zone
quality/freshness; - confirmation; - layer geometry; - capital budget; -
broker feasibility; - existing campaign identity.

A valid existing unrelated risk unit does not automatically block a new
zone campaign when sufficient portfolio capacity remains. A continuing
zone campaign retains its immutable plan identity.


## Zone execution ownership lifecycle

Atlas separates zone **context ownership** from zone **execution ownership**.

```text
NORMAL_SCALP
    ↓ qualified zone detected
ZONE_AWARE_SCALP (WATCHING)
    ↓ confirmation + directional + spread economics + broker + capital pass
ZONE_ENTRY_CONFIRMED / COMMIT BOUNDARY
    ↓ Nyao acknowledgement / exposure
ZONE_CAMPAIGN (COMMITTED)
    ↓ all campaign exposure released
NORMAL_SCALP or next zone-aware state
```

While WATCHING, the zone-aligned scalp direction remains available under the ordinary scalp score, execution-economics, duplicate, broker and capital gates. Counter-zone scalps remain possible only through the explicit context-aware path: they must clear the base signal gate, an additional evidence premium, reduced risk authority and the campaign-proximity veto. Atlas also preserves prospective zone headroom by clipping the zone-aware scalp budget when necessary so that the higher-priority campaign can still commit if its gates qualify on the next refresh.

A zone campaign receives exclusive fresh-entry authority only at the deterministic commit boundary. Existing positions continue to be managed; new conflicting scalps stop. This avoids wasting opportunities while a non-executable zone waits without allowing a scalp to steal the campaign's required risk capacity.

### Gemini policy behavior across the zone lifecycle

Gemini receives zone side, timeframe, quality, structure, feasibility and execution-lane state as read-only scalp-policy context. During `ZONE_AWARE_SCALP`, autonomous Nyao policy updates may continue and should optimize the scalp runtime for the aligned zone context without altering Atlas zone policy or weakening cost/risk gates. Once the zone crosses the commit boundary and Nyao acknowledges an executable campaign, new policy activation is deferred; candidate policies may still be evaluated/queued and are activated only after a clean campaign boundary. This prevents mid-campaign policy drift while preserving continuous learning.

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

## Performance intelligence and observability

Performance Intelligence is a read-only operator layer over Atlas authoritative outcome ledgers. Its primary scorecard consumes completed composite risk units and therefore preserves recovery-chain and zone-campaign semantics. Ticket-level MFE/MAE and entry-context breakdowns are diagnostic evidence only and cannot independently alter strategic loss streaks or policy performance. Policy-epoch comparisons remain descriptive until adequate sample maturity exists.

The Command Center and Market Analysis share the same live entry-analysis component. UI ownership moves that component only when the operator changes workspaces; it does not duplicate or alter execution state.

## 14. Documentation policy

This file is the single canonical architecture document. New
architectural capabilities should update this document rather than
create phase-specific architecture files. Temporary implementation
phases, migration scripts and test packages should not become permanent
repository documentation.


## Notification event layer

The dashboard derives human-facing notifications from authoritative Atlas/Nyao state transitions rather than from raw polling ticks. The first observed snapshot establishes a baseline; later material transitions are deduplicated and surfaced through the in-app drawer, optional browser notifications, and configurable severity-aware audio. Notification state/preferences are browser-local and are not trading authority or audit evidence. Trading ledgers and policy/outcome stores remain authoritative.


## Operator observability

Atlas maintains a non-authoritative human-facing observability layer above the deterministic trading engines. The Opportunity Queue projects current scalp, zone and recovery candidates from authoritative runtime state and states the next gate required for execution. The Decision Timeline records only material transitions (not every poll), including signal eligibility, blocker changes, transaction-cost feasibility, zone execution-lane transitions, capital/protection changes, policy epochs, order lifecycle and recovery activation/resolution.

The observability layer never creates execution authority and never substitutes for MT5 outcome, policy, capital, recovery or risk-unit ledgers. Its purpose is to make Atlas's current decision state and recent decision path understandable to the operator.


## Policy lineage model

Atlas Brain distinguishes four policy states: the runtime-active Nyao policy, current consensus candidates, applied historical policy epochs, and individual accepted Gemini observations. Runtime-active identity requires an exact current policy-epoch match; the latest autonomous application is never used as an implicit fallback. Policy history is reconciled against the policy epoch registry and live Nyao runtime. Accepted observations are associated with the baseline epoch they evaluated, allowing a resulting policy epoch to expose its supporting consensus window. Full historical Gemini prose is shown only when it was durably stored; Atlas does not fabricate missing historical reasoning.


## Zone campaign commitment vs exposure

Zone execution has two distinct phases. `ZONE_ENTRY_CONFIRMED` may suspend fresh scalps while a campaign has deterministic entry priority, but the campaign is not persisted as immutable merely because Nyao acknowledged the directive. Immutable `ZONE_CAMPAIGN_ACTIVE` persistence requires actual live `ATLAS_ZONE` exposure whose `zone_plan_id` matches the persisted campaign. Existing `FRESH_MARKET`, `FRESH_LIMIT`, recovery, or hedge-chain exposure does not qualify. This prevents unrelated exposure from pinning stale zone authority.


## Zone invalidation lifecycle

Atlas zone detection uses closed candles as the deterministic invalidation authority. A demand zone becomes invalid only when a later closed candle closes below its lower boundary; a supply zone becomes invalid only when a later closed candle closes above its upper boundary. Wick-only penetration can mark a zone mitigated but cannot invalidate it. Invalidated zones are excluded from priority selection, scalp context, confluence, scenarios and new campaign admission, while remaining in `invalidated_zones` for audit.

If no Atlas zone exposure exists, invalidation naturally releases zone-aware context and prospective zone-priority risk. If exposure already exists for the exact immutable zone plan, the campaign transitions to `ZONE_CAMPAIGN_INVALIDATED_MANAGEMENT`: ordinary scalping remains suspended during the live campaign, existing positions continue under their locked management/recovery lineage, and Nyao disables all unfilled/future zone layers.


## Operator Help workspace

The dashboard contains a first-class `Help & Guide` view. This is documentation-only and has no trading authority. It explains the current UI vocabulary and the separation between Atlas deterministic authority, Nyao execution, and Gemini policy learning. The guide version is kept aligned with the Atlas dashboard release.


## P3.54 — Event-driven Atlas Brain and loss-streak review

Atlas Brain is no longer fundamentally a short-interval optimizer. Material events wake the Brain; the periodic scheduler is retained only as a low-frequency health heartbeat (minimum 60 minutes).

Consecutive completed losses no longer create 15/30/60-minute HARD_VETO windows or automatic 0.05% recovery-probe sizing. At the configured loss-review threshold, Atlas persists `BRAIN_REVIEW_PENDING`, pauses only fresh independent risk while Gemini/critic reasoning is in flight, and immediately runs a `LOSS_STREAK_REVIEW` cycle. A successful Brain response releases the state to `REVIEW_COMPLETE` whether the outcome is HOLD, consensus accumulation, dwell deferral, or a validated autonomous policy application. Normal deterministic drawdown, exposure, broker, market-risk and unresolved-recovery-chain gates remain authoritative.

Loss streaks also no longer apply a one-way automatic lot-size decay. After Brain review, the loss-streak sizing modifier is neutral (`1.0`); Atlas may still contract risk for actual drawdown, volatility or deterministic risk state. If another completed loss occurs after the reviewed streak, a new Brain event is armed immediately. If a newer loss lands while an older review is running, the stale review cannot release it; Atlas re-arms review for the newer streak.

Legacy live `RECOVERY_PROBE` lifecycles remain restorable and atomic so upgrades cannot orphan broker exposure. Legacy persisted `HARD_VETO` files migrate to `BRAIN_REVIEW_PENDING` on first read.

## P3.55 — Drawdown Risk Efficiency + Event-Driven Brain UI

Atlas no longer treats ordinary drawdown as a mechanical lot-size punishment. Drawdown bands are reasoning events:

- `<3%` NORMAL
- `3–<5%` REVIEW — Gemini event, trading continues
- `5–<8%` ELEVATED — Gemini event, trading continues
- `>=8%` EMERGENCY — deterministic Risk Governor veto remains authoritative

The previous 0.75/0.50/0.25 drawdown size ladder is removed. MODERATE/ELEVATED risk labels also no longer create a second size penalty by themselves; only a genuine deterministic veto can stop risk, while volatility, broker feasibility, active exposure/capacity and recovery-chain constraints remain independent authorities.

Atlas Brain is now a single event-driven validated-autonomous runtime. The dashboard no longer presents Supervised vs Autonomous modes or the Human Review workflow. A configurable >=60 minute health heartbeat remains only as a liveness/fallback mechanism; material events are the primary reasoning trigger.
