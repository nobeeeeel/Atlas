<p align="center">
  <img src="atlas-logo.png" alt="Atlas — Adaptive Trading Intelligence" width="220">
</p>

# Atlas --- Adaptive Trading Intelligence

**Current release:** Atlas 1.30.21 · Nyao 44.4

**Documentation:** [Architecture](docs/architecture.md) · [Nyao MT5 Execution Layer](external/nyao/README.md)

Atlas is an adaptive trading intelligence and risk-governance platform
built around MetaTrader 5. Atlas performs deterministic market, capital,
execution-economics, portfolio-risk and outcome analysis; Nyao is the
MT5 execution layer that applies Atlas authority using live broker
specifications and terminal state.

The design goal is simple: **evaluate opportunities continuously, act
when the expected trade is justified, and never confuse available
capital with permission to take bad risk.**

## Core capabilities

### Adaptive scalp execution

-   Directional BUY/SELL scoring with runtime thresholds.
-   Market-regime and volatility-aware decision making.
-   Structure-aware entries rather than signal-score-only execution.
-   Dynamic stop/target geometry.
-   Duplicate-entry and execution-safety controls.

### Dynamic execution economics

Atlas does not rely on a single hard spread number. Scalp feasibility
considers spread relative to: - ATR and current volatility; - intended
stop and target; - transaction-cost ratios; - required stop expansion; -
whether the resulting geometry still represents the intended strategy.

A signal can therefore be valid while execution is rejected because the
market is temporarily too expensive or the required structure has become
unreasonable.

### Capital regime and configurable risk appetite

Atlas separates **operator risk appetite** from **per-opportunity
sizing**.

The operator controls the maximum aggregate portfolio hard-risk ceiling
from **1% to 20%**. The default is 1%. This ceiling is not per-trade
risk.

Atlas may reduce the effective operating envelope using drawdown, loss
protection, market risk, volatility, concentration and other
deterministic controls. Atlas and Gemini cannot silently increase the
operator-owned ceiling.

Individual scalp and zone budgets remain independently calculated
beneath the portfolio ceiling.

### Adaptive opportunity risk allocation
Atlas can allocate a bounded share of the current operating envelope to a qualified scalp or zone campaign instead of permanently capping every opportunity at the capital-regime floor. The regime budget remains a conservative floor; per-opportunity hard caps, portfolio capacity and all execution gates remain authoritative.

### Adaptive zone execution economics
Zone campaigns use campaign-aware transaction-cost economics. The legacy direct `ATR × fixed ratio` veto is disabled in the Nyao directive; ATR remains market context while bounded dynamic stop/target cost ratios are derived from zone quality, confirmation progress and campaign reward/risk geometry.

### Zone-aware execution lanes

Atlas separates **zone context** from **zone commitment**. A detected but
uncommitted zone informs scalping instead of automatically freezing it.
Only a fully qualified campaign receives exclusive fresh-entry priority.

This makes the execution engine opportunity-efficient without weakening
the zone campaign's deterministic authority.

### Concurrent portfolio risk allocation

Existing positions no longer create a blanket account-wide exposure
lock.

Atlas reserves deterministic risk for each active risk unit and
evaluates new opportunities against the remaining operating and hard
capacity. This allows independent qualified opportunities to execute
concurrently without double-counting capital.

Recovery chains reserve their frozen chain ceiling. Standalone positions
reserve remaining downside. Same-symbol concurrent exposure receives no
diversification credit.

### Composite risk units

Atlas evaluates strategic outcomes as complete risk units: -
`STANDALONE_TRADE` - `RECOVERY_CHAIN` - `ZONE_CAMPAIGN`

A recovery root and its hedge children are evaluated as one chain.
Individual member exits remain provisional until the complete chain is
flat. Zone layers sharing the same immutable campaign lineage are
likewise evaluated as one campaign.

### Recovery risk governance

Recovery is bounded rather than open-ended.

Each recovery chain receives a frozen deterministic risk envelope
derived from the original unit risk and recovery multiplier, tightened
by explicit chain and portfolio ceilings. Recovery legs cannot borrow
unused portfolio capacity beyond their chain authority.

Atlas persists recovery sizing events and can conservatively adopt an
already-active chain after a restart or upgrade so that unresolved
historical state never grants unlimited recovery authority.

### Authoritative MT5 outcomes

Atlas uses MT5 deal history as the authoritative source for realised
exits when available. It tracks exact realised P/L, reconstructs trades
that occur between polls, preserves policy attribution and maintains
immutable lineage for recovery and zone campaigns.

### Zone campaigns

Atlas maintains deterministic higher-timeframe zone context and can
execute layered zone campaigns when geometry, confirmation, capital,
execution economics and broker feasibility agree.

Zone ownership is now stateful rather than binary:

- **Normal scalp** — no priority zone owns context.
- **Zone-aware scalp / watching** — a qualified zone exists, but the
  campaign is not yet ready to commit. Aligned scalps may continue through
  their normal signal, structure, cost and capital gates while the zone
  remains deterministic context.
- **Zone campaign committed** — confirmation, directional evidence,
  spread economics, broker feasibility and capital authority all pass.
  Atlas atomically gives the campaign execution priority and suspends
  conflicting fresh scalps.

For a SELL zone in the watching state, SELL-aligned scalps may continue
while counter-direction BUY scalps are deterministically blocked. The
inverse applies to a BUY zone.

Atlas also protects **prospective zone headroom** while a campaign is
watching. A scalp may be clipped when necessary so it cannot consume the
capital a higher-priority zone would need if it becomes executable on the
next decision cycle.

This allows Atlas to avoid wasting valid scalp opportunities while still
preserving the higher-timeframe zone thesis and campaign priority.
### Atlas Brain / Gemini

Gemini can reason about market context, performance evidence and Nyao
policy parameters, but deterministic safety remains Atlas-owned.

Zone information is part of Gemini's scalp-policy context. While Atlas is
in **zone-aware scalp / watching** mode, Gemini continues scheduled or
autonomous policy analysis with the active zone side, timeframe, quality,
higher-timeframe structure, price location and campaign feasibility
available as read-only context.

When Atlas crosses the deterministic **zone commit boundary**, new policy
activation is deferred until the campaign reaches a clean boundary.
Gemini may continue analysing evidence and producing candidates, but an
active committed campaign is not allowed to experience mid-campaign
runtime-policy drift.

Gemini cannot override:

- operator portfolio risk appetite;
- Atlas capital sizing and prospective zone headroom;
- broker feasibility;
- recovery-chain ceilings;
- deterministic zone geometry or commit authority;
- hard execution and risk governors.
## Runtime architecture

``` text
Market + MT5 broker state
          │
          ▼
        Nyao
 telemetry / candles / positions / deals
          │
          ▼
        Atlas
 ├─ market & regime intelligence
 ├─ signal / structure analysis
 ├─ execution economics
 ├─ capital regime
 ├─ portfolio risk allocator
 ├─ recovery & zone governance
 ├─ outcome ledger
 └─ Atlas Brain / policy analysis
          │
          ▼
 deterministic command authority
          │
          ▼
        Nyao
 broker-aware sizing + OrderSend + management
          │
          ▼
         MT5
```

## Repository documentation

The repository intentionally keeps documentation small and canonical:

-   `README.md` --- product overview, capabilities and operating model.
-   `docs/architecture.md` --- technical architecture and authority
    model.
-   `external/nyao/README.md` --- Nyao/MT5 execution-layer
    documentation.

Development phase notes and one-off migration scripts are intentionally
not part of the canonical documentation set.

## Primary trading use

Atlas is designed to be instrument-adaptive. XAUUSD is the primary
intended trading market for the current deployment. BTC has also been
useful as a live-market stress environment when gold is closed,
particularly for validating transaction-cost, spread, recovery and
portfolio-risk behaviour.

No symbol is made tradable merely because capital is available. Atlas
must still establish valid signal, structure, execution economics,
broker feasibility and risk authority.

## Risk principle

**Available capital creates capacity, not an obligation to trade.**

Atlas is designed to avoid unnecessary opportunity loss while preserving
deterministic aggregate-risk control. It may run multiple justified risk
units concurrently, but every unit must fit within its own authority and
the current portfolio envelope.
